from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from threading import Event, Lock
from uuid import UUID

import pytest
from pydantic import BaseModel

from thinc_v5.decision.service import (
    AssessmentInput,
    AssessmentReservation,
    AssessmentService,
    EngineRegistration,
    EngineRegistry,
    InMemoryAssessmentRepository,
    SqlAlchemyAssessmentRepository,
    StoredEngineOutput,
)
from thinc_v5.domain.common import Provenance
from thinc_v5.domain.economics import EconomicsAssessment, EconomicsInput
from thinc_v5.engines.economics import EconomicsEngine


class EmptyResult:
    def scalar_one_or_none(self) -> None:
        return None


class RecordingConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[object, object | None]] = []

    def in_transaction(self) -> bool:
        return True

    def execute(
        self,
        statement: object,
        parameters: object | None = None,
    ) -> EmptyResult:
        self.calls.append((statement, parameters))
        return EmptyResult()


class RecordingEngine:
    def __init__(self) -> None:
        self.connection = RecordingConnection()

    @contextmanager
    def begin(self):
        yield self.connection


class MarkerOutput(BaseModel):
    marker: str


class OutputRecordingRepository(InMemoryAssessmentRepository):
    def __init__(self) -> None:
        super().__init__()
        self.saved_outputs: list[tuple[str, str]] = []

    def save_engine_output(
        self,
        tenant_id: UUID,
        assessment_id: str,
        stored: StoredEngineOutput,
    ) -> None:
        self.saved_outputs.append((assessment_id, stored.engine_name))
        super().save_engine_output(tenant_id, assessment_id, stored)


class ReservationObservingRepository(OutputRecordingRepository):
    def __init__(self) -> None:
        super().__init__()
        self._reservation_lock = Lock()
        self.reservation_calls = 0
        self.second_reservation_started = Event()

    def reserve_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        provenance: dict[str, object],
    ) -> AssessmentReservation:
        with self._reservation_lock:
            self.reservation_calls += 1
            if self.reservation_calls == 2:
                self.second_reservation_started.set()
        return super().reserve_assessment(
            tenant_id,
            idempotency_key,
            request_hash,
            provenance,
        )


def build_assessment_input() -> AssessmentInput:
    return AssessmentInput(
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
    )


def economics_registration() -> EngineRegistration:
    engine = EconomicsEngine()
    return EngineRegistration(
        name="economics",
        run=lambda request: engine.assess(request.economics, request.provenance),
        output_model=EconomicsAssessment,
    )


def test_sql_repository_sets_transaction_local_tenant_context_before_read() -> None:
    engine = RecordingEngine()
    repository = SqlAlchemyAssessmentRepository(engine)  # type: ignore[arg-type]
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")

    result = repository.get_assessment(tenant_id, "assessment-1")

    assert result is None
    assert len(engine.connection.calls) == 2
    context_statement, context_parameters = engine.connection.calls[0]
    select_statement, select_parameters = engine.connection.calls[1]
    assert "set_config('app.tenant_id'" in str(context_statement)
    assert context_parameters == {"tenant_id": str(tenant_id)}
    assert "assessment_records" in str(select_statement)
    assert select_parameters is None


def test_service_runs_and_persists_every_registered_engine_before_gates() -> None:
    repository = OutputRecordingRepository()
    registry = EngineRegistry(
        (
            economics_registration(),
            EngineRegistration(
                name="test-marker",
                run=lambda request: MarkerOutput(marker=request.provenance.market),
                output_model=MarkerOutput,
            ),
        )
    )
    service = AssessmentService(repository, engine_registry=registry)

    response = service.create_assessment(
        tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
        actor_id="researcher-1",
        idempotency_key="registry-success",
        request=build_assessment_input(),
    )

    assert repository.saved_outputs == [
        (response.assessment_id, "economics"),
        (response.assessment_id, "test-marker"),
    ]


def test_later_engine_failure_does_not_erase_prior_durable_output() -> None:
    repository = OutputRecordingRepository()

    def fail_after_economics(request: AssessmentInput) -> BaseModel:
        del request
        raise RuntimeError("later engine failed")

    service = AssessmentService(
        repository,
        engine_registry=EngineRegistry(
            (
                economics_registration(),
                EngineRegistration(
                    name="test-failure",
                    run=fail_after_economics,
                    output_model=MarkerOutput,
                ),
            )
        ),
    )

    with pytest.raises(RuntimeError, match="later engine failed"):
        service.create_assessment(
            tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
            actor_id="researcher-1",
            idempotency_key="registry-failure",
            request=build_assessment_input(),
        )

    assert len(repository.saved_outputs) == 1
    assessment_id, engine_name = repository.saved_outputs[0]
    assert assessment_id
    assert engine_name == "economics"


def test_concurrent_duplicate_reserves_one_id_and_executes_engine_once() -> None:
    repository = ReservationObservingRepository()
    engine_started = Event()
    release_engine = Event()
    execution_lock = Lock()
    executions = 0
    economics_engine = EconomicsEngine()

    def blocking_economics(request: AssessmentInput):
        nonlocal executions
        with execution_lock:
            executions += 1
        engine_started.set()
        assert release_engine.wait(timeout=5)
        return economics_engine.assess(request.economics, request.provenance)

    service = AssessmentService(
        repository,
        engine_registry=EngineRegistry(
            (
                EngineRegistration(
                    name="economics",
                    run=blocking_economics,
                    output_model=EconomicsAssessment,
                ),
            )
        ),
    )

    def create():
        return service.create_assessment(
            tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
            actor_id="researcher-1",
            idempotency_key="concurrent-key",
            request=build_assessment_input(),
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(create)
        assert engine_started.wait(timeout=5)
        second = executor.submit(create)
        try:
            assert repository.second_reservation_started.wait(timeout=5)
        finally:
            release_engine.set()
        responses = [first.result(timeout=5), second.result(timeout=5)]

    assert responses[0].assessment_id == responses[1].assessment_id
    assert executions == 1
    assert repository.saved_outputs == [
        (responses[0].assessment_id, "economics"),
    ]


def test_failed_executor_retry_reuses_reserved_assessment_id() -> None:
    repository = OutputRecordingRepository()
    attempts = 0
    economics_attempts = 0
    economics_engine = EconomicsEngine()

    def counting_economics(request: AssessmentInput):
        nonlocal economics_attempts
        economics_attempts += 1
        return economics_engine.assess(request.economics, request.provenance)

    def fail_once(request: AssessmentInput) -> MarkerOutput:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("transient engine failure")
        return MarkerOutput(marker=request.provenance.market)

    service = AssessmentService(
        repository,
        engine_registry=EngineRegistry(
            (
                EngineRegistration(
                    name="economics",
                    run=counting_economics,
                    output_model=EconomicsAssessment,
                ),
                EngineRegistration(
                    name="test-retry",
                    run=fail_once,
                    output_model=MarkerOutput,
                ),
            )
        ),
    )
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")

    with pytest.raises(RuntimeError, match="transient engine failure"):
        service.create_assessment(
            tenant_id=tenant_id,
            actor_id="researcher-1",
            idempotency_key="retry-key",
            request=build_assessment_input(),
        )
    failed_assessment_id = repository.saved_outputs[0][0]

    response = service.create_assessment(
        tenant_id=tenant_id,
        actor_id="researcher-1",
        idempotency_key="retry-key",
        request=build_assessment_input(),
    )

    assert response.assessment_id == failed_assessment_id
    assert attempts == 2
    assert economics_attempts == 1
    assert {assessment_id for assessment_id, _ in repository.saved_outputs} == {
        failed_assessment_id
    }
