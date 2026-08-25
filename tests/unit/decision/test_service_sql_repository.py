from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID

from thinc_v5.decision.service import (
    AssessmentInput,
    AssessmentResponse,
    SqlAlchemyAssessmentRepository,
)
from thinc_v5.domain.common import Provenance
from thinc_v5.domain.economics import EconomicsInput


class EmptyResult:
    def __init__(
        self,
        *,
        row: object | None = None,
        scalar: object | None = None,
    ) -> None:
        self._row = row
        self._scalar = scalar

    def one_or_none(self) -> object | None:
        return self._row

    def scalar_one_or_none(self) -> object | None:
        return self._scalar


class QueueConnection:
    def __init__(self, results: list[EmptyResult]) -> None:
        self.calls: list[tuple[object, object | None]] = []
        self._results = results

    def in_transaction(self) -> bool:
        return True

    def execute(
        self,
        statement: object,
        parameters: object | None = None,
    ) -> EmptyResult:
        self.calls.append((statement, parameters))
        if self._results:
            return self._results.pop(0)
        return EmptyResult()


class QueueEngine:
    def __init__(self, results: list[EmptyResult]) -> None:
        self.connection = QueueConnection(results)

    @contextmanager
    def begin(self):
        yield self.connection


def build_completed_response() -> AssessmentResponse:
    from thinc_v5.decision.service import (
        AssessmentService,
        InMemoryAssessmentRepository,
    )

    return AssessmentService(InMemoryAssessmentRepository()).create_assessment(
        tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
        actor_id="researcher-1",
        idempotency_key="sql-completed-response",
        request=AssessmentInput(
            economics=EconomicsInput(
                collected_revenue=Decimal("1000"),
                product_cost=Decimal("300"),
                ad_spend=Decimal("200"),
                shipping=Decimal("80"),
                collection_fees=Decimal("20"),
                return_cost=Decimal("40"),
                variable_operations_cost=Decimal("60"),
                delivered_orders=10,
            ),
            requested_decision="RESEARCH",
            compliance_passed=True,
            liquidity_passed=True,
            data_quality_passed=True,
            sample_size_passed=True,
            operational_recency_passed=True,
            provenance=Provenance(
                schema_version="1.0.0",
                model_version="economics-engine.1",
                engine_commit="abc1234",
                generated_at=datetime(2026, 8, 25, tzinfo=UTC),
                evidence_as_of=datetime(2026, 8, 24, tzinfo=UTC),
                market="EG",
                source_ids=["source-1"],
            ),
        ),
    )


def test_sql_repository_returns_completed_reservation_response_without_execution() -> (
    None
):
    completed = build_completed_response()
    engine = QueueEngine(
        [
            EmptyResult(),
            EmptyResult(),
            EmptyResult(
                row=SimpleNamespace(
                    domain_assessment_id=completed.assessment_id,
                    assessment={
                        "state": "COMPLETED",
                        "request_hash": "sha256:request",
                        "fencing_epoch": 4,
                        "response": completed.model_dump(mode="json"),
                    },
                    lease_active=True,
                )
            ),
        ]
    )
    repository = SqlAlchemyAssessmentRepository(engine)  # type: ignore[arg-type]

    reservation = repository.reserve_assessment(
        UUID("11111111-1111-4111-8111-111111111111"),
        "sql-completed",
        "sha256:request",
        {"source_ids": ["source-1"]},
    )

    assert reservation.execute is False
    assert reservation.response == completed
    assert reservation.assessment_id == completed.assessment_id


def test_sql_repository_reuses_failed_or_expired_assessment_id_for_retry() -> None:
    assessment_id = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
    engine = QueueEngine(
        [
            EmptyResult(),
            EmptyResult(),
            EmptyResult(
                row=SimpleNamespace(
                    domain_assessment_id=assessment_id,
                    assessment={
                        "state": "FAILED",
                        "request_hash": "sha256:request",
                        "fencing_epoch": 4,
                    },
                    lease_active=False,
                )
            ),
            EmptyResult(),
        ]
    )
    repository = SqlAlchemyAssessmentRepository(engine)  # type: ignore[arg-type]

    reservation = repository.reserve_assessment(
        UUID("11111111-1111-4111-8111-111111111111"),
        "sql-retry",
        "sha256:request",
        {"source_ids": ["source-1"]},
    )

    assert reservation.execute is True
    assert reservation.assessment_id == assessment_id
    assert reservation.fencing_epoch == 5
    assert reservation.owner_token
    assert any(
        getattr(statement, "is_update", False)
        for statement, _ in engine.connection.calls
    )


def test_sql_repository_get_assessment_returns_completed_payload() -> None:
    completed = build_completed_response()
    engine = QueueEngine(
        [
            EmptyResult(),
            EmptyResult(
                scalar={
                    "state": "COMPLETED",
                    "response": completed.model_dump(mode="json"),
                }
            ),
        ]
    )
    repository = SqlAlchemyAssessmentRepository(engine)  # type: ignore[arg-type]

    loaded = repository.get_assessment(
        UUID("11111111-1111-4111-8111-111111111111"),
        completed.assessment_id,
    )

    assert loaded == completed
