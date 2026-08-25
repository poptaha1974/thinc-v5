from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from pydantic import BaseModel

import thinc_v5.decision.service as service_module
from thinc_v5.decision.service import (
    AssessmentInput,
    AssessmentNotFound,
    AssessmentReservation,
    AssessmentResponse,
    AssessmentService,
    EngineContractError,
    EngineRegistration,
    EngineRegistry,
    IdempotencyConflict,
    InMemoryAssessmentRepository,
    ReservationStateError,
    SqlAlchemyAssessmentRepository,
    StoredApproval,
    StoredEngineOutput,
)
from thinc_v5.domain.common import Provenance
from thinc_v5.domain.decisions import HumanApproval
from thinc_v5.domain.economics import EconomicsAssessment, EconomicsInput
from thinc_v5.engines.economics import EconomicsEngine


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


def build_response() -> AssessmentResponse:
    return AssessmentService(InMemoryAssessmentRepository()).create_assessment(
        tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
        actor_id="researcher-1",
        idempotency_key="seed-response",
        request=build_assessment_input(),
    )


class CompletedReservationRepository:
    def __init__(self, response: AssessmentResponse | None) -> None:
        self._response = response

    @property
    def heartbeat_interval_seconds(self) -> float:
        return 1.0

    def reserve_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        provenance: dict[str, object],
    ) -> AssessmentReservation:
        del tenant_id, idempotency_key, request_hash, provenance
        return AssessmentReservation(
            assessment_id="assess-cached",
            owner_token="",
            fencing_epoch=1,
            execute=False,
            response=self._response,
        )

    def complete_assessment(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("cached reservations must not be completed again")

    def renew_assessment(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("cached reservations must not renew a lease")

    def fail_assessment(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("cached reservations must not be failed")

    def save_engine_output(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("cached reservations must not write engine output")

    def get_engine_output(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("cached reservations must not read engine output")

    def get_assessment(self, tenant_id: UUID, assessment_id: str) -> None:
        del tenant_id, assessment_id
        return None

    def save_approval(self, *args: object, **kwargs: object) -> StoredApproval:
        raise AssertionError("approval writes are out of scope for this helper")

    def get_approval_by_idempotency_key(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> None:
        del tenant_id, idempotency_key
        return None


class RecordingBeginEngine:
    @contextmanager
    def begin(self):
        yield object()


class MismatchedStoredApprovalRepository(InMemoryAssessmentRepository):
    def save_approval(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        stored: StoredApproval,
        audit_event: service_module.StoredAuditEvent,
    ) -> StoredApproval:
        saved = super().save_approval(
            tenant_id,
            idempotency_key,
            stored,
            audit_event,
        )
        return StoredApproval(
            request_hash="sha256:different",
            approval=saved.approval,
        )


class MarkerOutput(BaseModel):
    marker: str


def test_engine_registration_rejects_blank_and_overlong_names() -> None:
    with pytest.raises(ValueError, match="engine name must not be blank"):
        EngineRegistration(
            name="   ",
            run=lambda request: request,
            output_model=EconomicsAssessment,
        )

    with pytest.raises(ValueError, match="engine name must not exceed 100 characters"):
        EngineRegistration(
            name="x" * 101,
            run=lambda request: request,
            output_model=EconomicsAssessment,
        )


def test_engine_registry_requires_unique_names() -> None:
    registration = EngineRegistration(
        name="economics",
        run=lambda request: EconomicsEngine().assess(
            request.economics,
            request.provenance,
        ),
        output_model=EconomicsAssessment,
    )

    with pytest.raises(ValueError, match="engine names must be unique"):
        EngineRegistry((registration, registration))


def test_repositories_reject_invalid_lease_and_heartbeat_settings() -> None:
    with pytest.raises(ValueError, match="reservation lease must be positive"):
        InMemoryAssessmentRepository(reservation_lease=timedelta(0))
    with pytest.raises(
        ValueError,
        match="heartbeat interval must be positive and below lease",
    ):
        InMemoryAssessmentRepository(
            reservation_lease=timedelta(seconds=3),
            heartbeat_interval_seconds=3.0,
        )
    with pytest.raises(ValueError, match="reservation lease must be positive"):
        SqlAlchemyAssessmentRepository(
            RecordingBeginEngine(),  # type: ignore[arg-type]
            reservation_lease=timedelta(0),
        )
    with pytest.raises(
        ValueError,
        match="heartbeat interval must be positive and below lease",
    ):
        SqlAlchemyAssessmentRepository(
            RecordingBeginEngine(),  # type: ignore[arg-type]
            reservation_lease=timedelta(seconds=3),
            heartbeat_interval_seconds=3.0,
        )


def test_service_returns_cached_completed_response_without_reexecution() -> None:
    cached = build_response()
    service = AssessmentService(CompletedReservationRepository(cached))

    response = service.create_assessment(
        tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
        actor_id="researcher-1",
        idempotency_key="cached-response",
        request=build_assessment_input(),
    )

    assert response == cached


def test_service_rejects_completed_reservation_without_cached_response() -> None:
    service = AssessmentService(CompletedReservationRepository(None))

    with pytest.raises(
        ReservationStateError,
        match="completed reservation has no response",
    ):
        service.create_assessment(
            tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
            actor_id="researcher-1",
            idempotency_key="missing-response",
            request=build_assessment_input(),
        )


def test_service_requires_registered_economics_output() -> None:
    service = AssessmentService(
        InMemoryAssessmentRepository(),
        engine_registry=EngineRegistry(
            (
                EngineRegistration(
                    name="marker",
                    run=lambda request: MarkerOutput(marker=request.provenance.market),
                    output_model=MarkerOutput,
                ),
            )
        ),
    )

    with pytest.raises(
        EngineContractError,
        match="registry must provide an EconomicsAssessment named 'economics'",
    ):
        service.create_assessment(
            tenant_id=UUID("11111111-1111-4111-8111-111111111111"),
            actor_id="researcher-1",
            idempotency_key="missing-economics",
            request=build_assessment_input(),
        )


def test_service_get_assessment_raises_for_unknown_assessment() -> None:
    service = AssessmentService(InMemoryAssessmentRepository())

    with pytest.raises(AssessmentNotFound, match="does-not-exist"):
        service.get_assessment(
            UUID("11111111-1111-4111-8111-111111111111"),
            "does-not-exist",
        )


def test_approve_assessment_replays_same_request_and_rejects_conflict() -> None:
    repository = InMemoryAssessmentRepository()
    service = AssessmentService(repository)
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    created = service.create_assessment(
        tenant_id=tenant_id,
        actor_id="researcher-1",
        idempotency_key="approval-seed",
        request=build_assessment_input(),
    )
    approved_at = datetime(2026, 8, 25, 11, 0, tzinfo=UTC)

    first = service.approve_assessment(
        tenant_id=tenant_id,
        assessment_id=created.assessment_id,
        approver_id="researcher-1",
        idempotency_key="approval-key",
        approved_at=approved_at,
    )
    replay = service.approve_assessment(
        tenant_id=tenant_id,
        assessment_id=created.assessment_id,
        approver_id="researcher-1",
        idempotency_key="approval-key",
        approved_at=approved_at,
    )

    assert replay == first
    with pytest.raises(IdempotencyConflict):
        service.approve_assessment(
            tenant_id=tenant_id,
            assessment_id=created.assessment_id,
            approver_id="researcher-1",
            idempotency_key="approval-key",
            approved_at=datetime(2026, 8, 25, 12, 0, tzinfo=UTC),
        )


def test_approve_assessment_rejects_mismatched_saved_request_hash() -> None:
    repository = MismatchedStoredApprovalRepository()
    service = AssessmentService(repository)
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    created = service.create_assessment(
        tenant_id=tenant_id,
        actor_id="researcher-1",
        idempotency_key="mismatch-seed",
        request=build_assessment_input(),
    )

    with pytest.raises(IdempotencyConflict):
        service.approve_assessment(
            tenant_id=tenant_id,
            assessment_id=created.assessment_id,
            approver_id="researcher-1",
            idempotency_key="mismatch-approval",
            approved_at=datetime(2026, 8, 25, 13, 0, tzinfo=UTC),
        )


def test_inmemory_repository_blocks_conflicting_engine_output_hash() -> None:
    repository = InMemoryAssessmentRepository()
    tenant_id = UUID("11111111-1111-4111-8111-111111111111")
    reservation = repository.reserve_assessment(
        tenant_id,
        "output-hash",
        "sha256:request",
        {"source_ids": ["source-1"]},
    )
    original = StoredEngineOutput(
        engine_name="economics",
        output={"value": "first"},
        output_hash=service_module._json_hash({"value": "first"}),
        provenance={"source_ids": ["source-1"]},
    )
    conflict = StoredEngineOutput(
        engine_name="economics",
        output={"value": "second"},
        output_hash=service_module._json_hash({"value": "second"}),
        provenance={"source_ids": ["source-1"]},
    )

    repository.save_engine_output(
        tenant_id,
        reservation.assessment_id,
        reservation,
        original,
    )
    with pytest.raises(IdempotencyConflict):
        repository.save_engine_output(
            tenant_id,
            reservation.assessment_id,
            reservation,
            conflict,
        )


def test_memory_repository_save_approval_requires_existing_assessment() -> None:
    repository = InMemoryAssessmentRepository()
    stored = StoredApproval(
        request_hash="sha256:approval",
        approval=HumanApproval(
            approver_id="researcher-1",
            approved_at=datetime(2026, 8, 25, 14, 0, tzinfo=UTC),
            assessment_id="missing-assessment",
        ),
    )

    with pytest.raises(AssessmentNotFound):
        repository.save_approval(
            UUID("11111111-1111-4111-8111-111111111111"),
            "missing-approval",
            stored,
            service_module._approval_audit_event(stored),
        )
