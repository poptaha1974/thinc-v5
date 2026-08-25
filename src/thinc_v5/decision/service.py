from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import Condition, Event, RLock, Thread
from typing import Any, Literal, Protocol, cast
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import DateTime, func, insert, select, text, update
from sqlalchemy.engine import Connection, Engine, Row
from sqlalchemy.sql import Select

from thinc_v5.db.models import (
    AssessmentRecord,
    AuditEvent,
    DecisionRecord,
    EngineOutputRecord,
    EvidenceRecord,
    HumanApprovalRecord,
)
from thinc_v5.db.session import set_tenant_context
from thinc_v5.decision.gates import evaluate_gates
from thinc_v5.domain.common import (
    DataQualityStatus,
    Provenance,
    ResearchPreviewResult,
    ReviewStatus,
)
from thinc_v5.domain.decisions import (
    Decision,
    GateContext,
    GateResult,
    HumanApproval,
)
from thinc_v5.domain.economics import EconomicsAssessment, EconomicsInput
from thinc_v5.engines.economics import EconomicsEngine


class AssessmentInput(BaseModel):
    economics: EconomicsInput
    requested_decision: Decision
    compliance_passed: bool
    liquidity_passed: bool
    data_quality_passed: bool
    sample_size_passed: bool
    operational_recency_passed: bool
    stop_loss_registered: bool = False
    provenance: Provenance


class AssessmentData(BaseModel):
    economics: EconomicsAssessment
    gate_results: tuple[GateResult, ...]


class AssessmentResponse(ResearchPreviewResult[AssessmentData]):
    assessment_id: str
    status: Literal["Research Preview"] = "Research Preview"


EngineRunner = Callable[[AssessmentInput], BaseModel]


@dataclass(frozen=True)
class EngineRegistration:
    name: str
    run: EngineRunner
    output_model: type[BaseModel]

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("engine name must not be blank")
        if len(self.name) > 100:
            raise ValueError("engine name must not exceed 100 characters")


class EngineRegistry:
    def __init__(self, registrations: Sequence[EngineRegistration]) -> None:
        names = [registration.name for registration in registrations]
        if len(names) != len(set(names)):
            raise ValueError("engine names must be unique")
        self._registrations = tuple(registrations)

    @property
    def registrations(self) -> tuple[EngineRegistration, ...]:
        return self._registrations


@dataclass(frozen=True)
class StoredEngineOutput:
    engine_name: str
    output: dict[str, Any]
    output_hash: str
    provenance: dict[str, Any]


@dataclass(frozen=True)
class StoredEvidenceRecord:
    record_id: UUID
    source_id: str
    raw_payload: dict[str, Any]
    normalized_payload: dict[str, Any]
    raw_payload_hash: str
    normalized_payload_hash: str
    provenance: dict[str, Any]


@dataclass(frozen=True)
class StoredDecisionRecord:
    record_id: UUID
    requested_decision: str
    recommended_decision: str
    gate_reasons: tuple[dict[str, Any], ...]
    decision_hash: str
    provenance: dict[str, Any]


@dataclass(frozen=True)
class StoredAuditEvent:
    record_id: UUID
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    payload: dict[str, Any]
    integrity_hash: str


@dataclass(frozen=True)
class AssessmentCompletion:
    response: AssessmentResponse
    evidence: StoredEvidenceRecord
    decision: StoredDecisionRecord
    audit_event: StoredAuditEvent


@dataclass(frozen=True)
class GovernanceRecords:
    evidence_records: tuple[StoredEvidenceRecord, ...]
    decision_records: tuple[StoredDecisionRecord, ...]
    audit_events: tuple[StoredAuditEvent, ...]


@dataclass(frozen=True)
class AssessmentReservation:
    assessment_id: str
    owner_token: str
    fencing_epoch: int
    execute: bool
    response: AssessmentResponse | None = None


@dataclass
class _MemoryReservation:
    assessment_id: str
    owner_token: str
    fencing_epoch: int
    lease_expires_at: datetime
    request_hash: str
    state: Literal["PENDING", "FAILED", "COMPLETED"]
    response: AssessmentResponse | None = None


@dataclass(frozen=True)
class StoredApproval:
    request_hash: str
    approval: HumanApproval
    record_id: UUID = field(default_factory=uuid4)


class AssessmentRepository(Protocol):
    @property
    def heartbeat_interval_seconds(self) -> float: ...

    def reserve_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        provenance: dict[str, object],
    ) -> AssessmentReservation: ...

    def complete_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        reservation: AssessmentReservation,
        completion: AssessmentCompletion,
    ) -> None: ...

    def renew_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        reservation: AssessmentReservation,
    ) -> None: ...

    def fail_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        reservation: AssessmentReservation,
    ) -> None: ...

    def save_engine_output(
        self,
        tenant_id: UUID,
        assessment_id: str,
        reservation: AssessmentReservation,
        stored: StoredEngineOutput,
    ) -> None: ...

    def get_engine_output(
        self,
        tenant_id: UUID,
        assessment_id: str,
        reservation: AssessmentReservation,
        engine_name: str,
    ) -> StoredEngineOutput | None: ...

    def get_assessment(
        self,
        tenant_id: UUID,
        assessment_id: str,
    ) -> AssessmentResponse | None: ...

    def save_approval(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        stored: StoredApproval,
        audit_event: StoredAuditEvent,
    ) -> StoredApproval: ...

    def get_approval_by_idempotency_key(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> StoredApproval | None: ...

    def get_governance_records(self, tenant_id: UUID) -> GovernanceRecords: ...


class InMemoryAssessmentRepository:
    """Tenant-isolated test repository; it is not production persistence."""

    def __init__(
        self,
        *,
        reservation_lease: timedelta = timedelta(minutes=5),
        heartbeat_interval_seconds: float | None = None,
    ) -> None:
        if reservation_lease <= timedelta(0):
            raise ValueError("reservation lease must be positive")
        self._reservation_lease = reservation_lease
        interval = heartbeat_interval_seconds
        if interval is None:
            interval = min(60.0, reservation_lease.total_seconds() / 3)
        if interval <= 0 or interval >= reservation_lease.total_seconds():
            raise ValueError("heartbeat interval must be positive and below lease")
        self._heartbeat_interval_seconds = interval
        self._lock = RLock()
        self._condition = Condition(self._lock)
        self._reservations: dict[tuple[UUID, str], _MemoryReservation] = {}
        self._by_id: dict[tuple[UUID, str], AssessmentResponse] = {}
        self._approvals: dict[tuple[UUID, str], StoredApproval] = {}
        self._approval_idempotency: dict[tuple[UUID, str], StoredApproval] = {}
        self._engine_outputs: dict[tuple[UUID, str, str], StoredEngineOutput] = {}
        self._assessment_hashes: dict[tuple[UUID, str], str] = {}
        self._evidence_records: dict[tuple[UUID, UUID], StoredEvidenceRecord] = {}
        self._decision_records: dict[tuple[UUID, UUID], StoredDecisionRecord] = {}
        self._audit_events: dict[tuple[UUID, UUID], StoredAuditEvent] = {}

    @property
    def heartbeat_interval_seconds(self) -> float:
        return self._heartbeat_interval_seconds

    def _on_pending_wait(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> None:
        """Test seam invoked only after a follower observes live PENDING state."""
        del tenant_id, idempotency_key

    def reserve_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        provenance: dict[str, object],
    ) -> AssessmentReservation:
        del provenance
        key = (tenant_id, idempotency_key)
        with self._condition:
            while True:
                stored = self._reservations.get(key)
                if stored is None:
                    stored = _MemoryReservation(
                        assessment_id=str(uuid4()),
                        owner_token=str(uuid4()),
                        fencing_epoch=1,
                        lease_expires_at=(datetime.now(UTC) + self._reservation_lease),
                        request_hash=request_hash,
                        state="PENDING",
                    )
                    self._reservations[key] = stored
                    return _memory_reservation(stored, execute=True)
                if stored.request_hash != request_hash:
                    raise IdempotencyConflict
                if stored.state == "COMPLETED":
                    if stored.response is None:
                        raise ReservationStateError(
                            "completed reservation has no response"
                        )
                    _require_json_hash(
                        stored.response.model_dump(mode="json"),
                        self._assessment_hashes[(tenant_id, stored.assessment_id)],
                        "assessment hash",
                    )
                    return _memory_reservation(stored, execute=False)
                if stored.state == "FAILED" or stored.lease_expires_at <= datetime.now(
                    UTC
                ):
                    stored.state = "PENDING"
                    stored.owner_token = str(uuid4())
                    stored.fencing_epoch += 1
                    stored.lease_expires_at = (
                        datetime.now(UTC) + self._reservation_lease
                    )
                    return _memory_reservation(stored, execute=True)
                self._on_pending_wait(tenant_id, idempotency_key)
                remaining = (
                    stored.lease_expires_at - datetime.now(UTC)
                ).total_seconds()
                self._condition.wait(timeout=max(0.001, remaining))

    def renew_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        reservation: AssessmentReservation,
    ) -> None:
        with self._lock:
            stored = self._reservations[(tenant_id, idempotency_key)]
            _require_reservation_owner(stored, request_hash, reservation)
            stored.lease_expires_at = datetime.now(UTC) + self._reservation_lease

    def complete_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        reservation: AssessmentReservation,
        completion: AssessmentCompletion,
    ) -> None:
        _validate_completion_integrity(completion)
        key = (tenant_id, idempotency_key)
        with self._condition:
            stored = self._reservations[key]
            _require_reservation_owner(stored, request_hash, reservation)
            response = completion.response
            if response.assessment_id != reservation.assessment_id:
                raise ReservationStateError(
                    "completion assessment ID does not match reservation"
                )
            _validate_actor_id(completion.audit_event.actor_id)
            evidence_key = (tenant_id, completion.evidence.record_id)
            decision_key = (tenant_id, completion.decision.record_id)
            audit_key = (tenant_id, completion.audit_event.record_id)
            if (
                evidence_key in self._evidence_records
                or decision_key in self._decision_records
                or audit_key in self._audit_events
            ):
                raise IdempotencyConflict
            evidence_records = dict(self._evidence_records)
            decision_records = dict(self._decision_records)
            audit_events = dict(self._audit_events)
            assessment_hashes = dict(self._assessment_hashes)
            by_id = dict(self._by_id)
            evidence_records[evidence_key] = deepcopy(completion.evidence)
            decision_records[decision_key] = deepcopy(completion.decision)
            audit_events[audit_key] = deepcopy(completion.audit_event)
            response_hash = _json_hash(response.model_dump(mode="json"))
            assessment_hashes[(tenant_id, response.assessment_id)] = response_hash
            by_id[(tenant_id, response.assessment_id)] = deepcopy(response)
            self._evidence_records = evidence_records
            self._decision_records = decision_records
            self._audit_events = audit_events
            self._assessment_hashes = assessment_hashes
            self._by_id = by_id
            stored.state = "COMPLETED"
            stored.response = deepcopy(response)
            self._condition.notify_all()

    def fail_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        reservation: AssessmentReservation,
    ) -> None:
        key = (tenant_id, idempotency_key)
        with self._condition:
            stored = self._reservations[key]
            _require_reservation_owner(stored, request_hash, reservation)
            stored.state = "FAILED"
            self._condition.notify_all()

    def save_engine_output(
        self,
        tenant_id: UUID,
        assessment_id: str,
        reservation: AssessmentReservation,
        stored: StoredEngineOutput,
    ) -> None:
        with self._lock:
            _require_memory_output_owner(
                self._reservations,
                tenant_id,
                assessment_id,
                reservation,
            )
            key = (tenant_id, assessment_id, stored.engine_name)
            prior = self._engine_outputs.get(key)
            if prior is not None and prior.output_hash != stored.output_hash:
                raise IdempotencyConflict
            self._engine_outputs[key] = deepcopy(stored)

    def get_engine_output(
        self,
        tenant_id: UUID,
        assessment_id: str,
        reservation: AssessmentReservation,
        engine_name: str,
    ) -> StoredEngineOutput | None:
        with self._lock:
            _require_memory_output_owner(
                self._reservations,
                tenant_id,
                assessment_id,
                reservation,
            )
            return deepcopy(
                self._verified_engine_output(
                    self._engine_outputs.get((tenant_id, assessment_id, engine_name))
                )
            )

    @staticmethod
    def _verified_engine_output(
        stored: StoredEngineOutput | None,
    ) -> StoredEngineOutput | None:
        if stored is not None:
            _require_json_hash(
                stored.output,
                stored.output_hash,
                "engine output hash",
            )
        return stored

    def get_assessment(
        self,
        tenant_id: UUID,
        assessment_id: str,
    ) -> AssessmentResponse | None:
        with self._lock:
            response = self._by_id.get((tenant_id, assessment_id))
            if response is None:
                return None
            _require_json_hash(
                response.model_dump(mode="json"),
                self._assessment_hashes[(tenant_id, assessment_id)],
                "assessment hash",
            )
            return deepcopy(response)

    def save_approval(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        stored: StoredApproval,
        audit_event: StoredAuditEvent,
    ) -> StoredApproval:
        _validate_audit_integrity(audit_event)
        _validate_actor_id(audit_event.actor_id)
        with self._lock:
            approval = stored.approval
            if (tenant_id, approval.assessment_id) not in self._by_id:
                raise AssessmentNotFound(approval.assessment_id)
            idempotency_key_with_tenant = (tenant_id, idempotency_key)
            prior = self._approval_idempotency.get(idempotency_key_with_tenant)
            if prior is not None:
                return deepcopy(prior)
            audit_key = (tenant_id, audit_event.record_id)
            if audit_key in self._audit_events:
                raise IdempotencyConflict
            copied = deepcopy(stored)
            approval_idempotency = dict(self._approval_idempotency)
            approvals = dict(self._approvals)
            audit_events = dict(self._audit_events)
            approval_idempotency[idempotency_key_with_tenant] = copied
            approvals[(tenant_id, approval.assessment_id)] = copied
            audit_events[audit_key] = deepcopy(audit_event)
            self._approval_idempotency = approval_idempotency
            self._approvals = approvals
            self._audit_events = audit_events
            return deepcopy(copied)

    def get_approval_by_idempotency_key(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> StoredApproval | None:
        with self._lock:
            return deepcopy(
                self._approval_idempotency.get((tenant_id, idempotency_key))
            )

    def get_governance_records(self, tenant_id: UUID) -> GovernanceRecords:
        with self._lock:
            return GovernanceRecords(
                evidence_records=tuple(
                    deepcopy(record)
                    for (record_tenant, _), record in self._evidence_records.items()
                    if record_tenant == tenant_id
                ),
                decision_records=tuple(
                    deepcopy(record)
                    for (record_tenant, _), record in self._decision_records.items()
                    if record_tenant == tenant_id
                ),
                audit_events=tuple(
                    deepcopy(record)
                    for (record_tenant, _), record in self._audit_events.items()
                    if record_tenant == tenant_id
                ),
            )


class SqlAlchemyAssessmentRepository:
    """PostgreSQL adapter that applies Task 5 transaction-local RLS context."""

    _pending_poll_seconds = 0.05

    def __init__(
        self,
        engine: Engine,
        *,
        reservation_lease: timedelta = timedelta(minutes=5),
        heartbeat_interval_seconds: float | None = None,
    ) -> None:
        self._engine = engine
        if reservation_lease <= timedelta(0):
            raise ValueError("reservation lease must be positive")
        self._reservation_lease = reservation_lease
        interval = heartbeat_interval_seconds
        if interval is None:
            interval = min(60.0, reservation_lease.total_seconds() / 3)
        if interval <= 0 or interval >= reservation_lease.total_seconds():
            raise ValueError("heartbeat interval must be positive and below lease")
        self._heartbeat_interval_seconds = interval

    @property
    def heartbeat_interval_seconds(self) -> float:
        return self._heartbeat_interval_seconds

    def _on_pending_wait(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> None:
        """Test seam invoked only after a follower observes live PENDING state."""
        del tenant_id, idempotency_key

    def reserve_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        provenance: dict[str, object],
    ) -> AssessmentReservation:
        while True:
            should_wait = False
            with self._engine.begin() as connection:
                set_tenant_context(connection, tenant_id)
                _lock_idempotency_key(connection, tenant_id, idempotency_key)
                row = connection.execute(
                    select(
                        AssessmentRecord.domain_assessment_id,
                        AssessmentRecord.assessment,
                        AssessmentRecord.assessment_hash,
                        (AssessmentRecord.lease_expires_at > _database_clock()).label(
                            "lease_active"
                        ),
                    ).where(
                        AssessmentRecord.tenant_id == tenant_id,
                        AssessmentRecord.idempotency_key == idempotency_key,
                    )
                ).one_or_none()
                if row is None:
                    assessment_id = str(uuid4())
                    owner_token = str(uuid4())
                    payload = _pending_payload(
                        request_hash,
                        owner_token,
                        1,
                    )
                    connection.execute(
                        insert(AssessmentRecord).values(
                            id=UUID(assessment_id),
                            tenant_id=tenant_id,
                            domain_assessment_id=assessment_id,
                            idempotency_key=idempotency_key,
                            assessment=payload,
                            assessment_hash=request_hash,
                            provenance=provenance,
                            lease_expires_at=_database_lease_expiry(
                                self._reservation_lease
                            ),
                        )
                    )
                    return AssessmentReservation(
                        assessment_id=assessment_id,
                        owner_token=owner_token,
                        fencing_epoch=1,
                        execute=True,
                    )

                assessment_id = row.domain_assessment_id
                payload = row.assessment
                if payload["request_hash"] != request_hash:
                    raise IdempotencyConflict
                if payload["state"] == "COMPLETED":
                    _require_json_hash(
                        payload["response"],
                        row.assessment_hash,
                        "assessment hash",
                    )
                    return AssessmentReservation(
                        assessment_id=assessment_id,
                        owner_token=str(uuid4()),
                        fencing_epoch=int(payload.get("fencing_epoch", 0)),
                        execute=False,
                        response=AssessmentResponse.model_validate(payload["response"]),
                    )
                if payload["state"] == "FAILED" or row.lease_active is not True:
                    owner_token = str(uuid4())
                    fencing_epoch = int(payload.get("fencing_epoch", 0)) + 1
                    connection.execute(
                        update(AssessmentRecord)
                        .where(
                            AssessmentRecord.tenant_id == tenant_id,
                            AssessmentRecord.idempotency_key == idempotency_key,
                        )
                        .values(
                            assessment=_pending_payload(
                                request_hash,
                                owner_token,
                                fencing_epoch,
                            ),
                            assessment_hash=request_hash,
                            provenance=provenance,
                            lease_expires_at=_database_lease_expiry(
                                self._reservation_lease
                            ),
                        )
                    )
                    return AssessmentReservation(
                        assessment_id=assessment_id,
                        owner_token=owner_token,
                        fencing_epoch=fencing_epoch,
                        execute=True,
                    )
                should_wait = True
            if should_wait:
                self._on_pending_wait(tenant_id, idempotency_key)
                time.sleep(self._pending_poll_seconds)

    def renew_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        reservation: AssessmentReservation,
    ) -> None:
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            _lock_idempotency_key(connection, tenant_id, idempotency_key)
            assessment_id, payload, lease_active = _load_reservation(
                connection,
                tenant_id,
                idempotency_key,
            )
            _require_database_reservation_owner(
                assessment_id,
                payload,
                lease_active,
                request_hash,
                reservation,
            )
            connection.execute(
                update(AssessmentRecord)
                .where(
                    AssessmentRecord.tenant_id == tenant_id,
                    AssessmentRecord.idempotency_key == idempotency_key,
                )
                .values(
                    lease_expires_at=_database_lease_expiry(self._reservation_lease)
                )
            )

    def complete_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        reservation: AssessmentReservation,
        completion: AssessmentCompletion,
    ) -> None:
        _validate_completion_integrity(completion)
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            _lock_idempotency_key(connection, tenant_id, idempotency_key)
            assessment_id, payload, lease_active = _load_reservation(
                connection,
                tenant_id,
                idempotency_key,
            )
            _require_database_reservation_owner(
                assessment_id,
                payload,
                lease_active,
                request_hash,
                reservation,
            )
            response = completion.response
            if response.assessment_id != reservation.assessment_id:
                raise ReservationStateError(
                    "completion assessment ID does not match reservation"
                )
            assessment_record_id = connection.execute(
                select(AssessmentRecord.id).where(
                    AssessmentRecord.tenant_id == tenant_id,
                    AssessmentRecord.idempotency_key == idempotency_key,
                )
            ).scalar_one()
            connection.execute(
                insert(EvidenceRecord).values(
                    id=completion.evidence.record_id,
                    tenant_id=tenant_id,
                    source_id=completion.evidence.source_id,
                    raw_payload=completion.evidence.raw_payload,
                    normalized_payload=completion.evidence.normalized_payload,
                    raw_payload_hash=completion.evidence.raw_payload_hash,
                    normalized_payload_hash=(
                        completion.evidence.normalized_payload_hash
                    ),
                    provenance=completion.evidence.provenance,
                )
            )
            connection.execute(
                insert(DecisionRecord).values(
                    id=completion.decision.record_id,
                    tenant_id=tenant_id,
                    assessment_id=assessment_record_id,
                    decision=completion.decision.recommended_decision,
                    reasons={
                        "requested_decision": (completion.decision.requested_decision),
                        "recommended_decision": (
                            completion.decision.recommended_decision
                        ),
                        "gate_reasons": list(completion.decision.gate_reasons),
                    },
                    decision_hash=completion.decision.decision_hash,
                    provenance=completion.decision.provenance,
                )
            )
            connection.execute(
                insert(AuditEvent).values(
                    id=completion.audit_event.record_id,
                    tenant_id=tenant_id,
                    actor_id=completion.audit_event.actor_id,
                    event_type=completion.audit_event.action,
                    entity_type=completion.audit_event.entity_type,
                    entity_id=completion.audit_event.entity_id,
                    payload=completion.audit_event.payload,
                    integrity_hash=completion.audit_event.integrity_hash,
                    previous_event_hash=None,
                )
            )
            response_payload = response.model_dump(mode="json")
            connection.execute(
                update(AssessmentRecord)
                .where(
                    AssessmentRecord.tenant_id == tenant_id,
                    AssessmentRecord.idempotency_key == idempotency_key,
                )
                .values(
                    assessment={
                        "state": "COMPLETED",
                        "request_hash": request_hash,
                        "fencing_epoch": reservation.fencing_epoch,
                        "response": response_payload,
                    },
                    assessment_hash=_json_hash(response_payload),
                    provenance=response.provenance.model_dump(mode="json"),
                    lease_expires_at=None,
                )
            )

    def fail_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        reservation: AssessmentReservation,
    ) -> None:
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            _lock_idempotency_key(connection, tenant_id, idempotency_key)
            assessment_id, payload, lease_active = _load_reservation(
                connection,
                tenant_id,
                idempotency_key,
            )
            _require_database_reservation_owner(
                assessment_id,
                payload,
                lease_active,
                request_hash,
                reservation,
            )
            connection.execute(
                update(AssessmentRecord)
                .where(
                    AssessmentRecord.tenant_id == tenant_id,
                    AssessmentRecord.idempotency_key == idempotency_key,
                )
                .values(
                    assessment={
                        "state": "FAILED",
                        "request_hash": request_hash,
                        "fencing_epoch": reservation.fencing_epoch,
                        "retry_semantics": (
                            "the next identical request reuses this assessment_id"
                        ),
                    },
                    assessment_hash=request_hash,
                    lease_expires_at=None,
                )
            )

    def save_engine_output(
        self,
        tenant_id: UUID,
        assessment_id: str,
        reservation: AssessmentReservation,
        stored: StoredEngineOutput,
    ) -> None:
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            _lock_and_require_output_owner(
                connection,
                tenant_id,
                assessment_id,
                reservation,
            )
            prior_hash = connection.execute(
                select(EngineOutputRecord.output_hash).where(
                    EngineOutputRecord.tenant_id == tenant_id,
                    EngineOutputRecord.assessment_id == assessment_id,
                    EngineOutputRecord.engine_name == stored.engine_name,
                )
            ).scalar_one_or_none()
            if prior_hash is not None:
                if prior_hash != stored.output_hash:
                    raise IdempotencyConflict
                return
            connection.execute(
                insert(EngineOutputRecord).values(
                    id=uuid4(),
                    tenant_id=tenant_id,
                    assessment_id=assessment_id,
                    engine_name=stored.engine_name,
                    output=stored.output,
                    output_hash=stored.output_hash,
                    provenance=stored.provenance,
                )
            )

    def get_engine_output(
        self,
        tenant_id: UUID,
        assessment_id: str,
        reservation: AssessmentReservation,
        engine_name: str,
    ) -> StoredEngineOutput | None:
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            _lock_and_require_output_owner(
                connection,
                tenant_id,
                assessment_id,
                reservation,
            )
            row = connection.execute(
                select(
                    EngineOutputRecord.output,
                    EngineOutputRecord.output_hash,
                    EngineOutputRecord.provenance,
                ).where(
                    EngineOutputRecord.tenant_id == tenant_id,
                    EngineOutputRecord.assessment_id == assessment_id,
                    EngineOutputRecord.engine_name == engine_name,
                )
            ).one_or_none()
            if row is None:
                return None
            _require_json_hash(
                row.output,
                row.output_hash,
                "engine output hash",
            )
            return StoredEngineOutput(
                engine_name=engine_name,
                output=row.output,
                output_hash=row.output_hash,
                provenance=row.provenance,
            )

    def get_assessment(
        self,
        tenant_id: UUID,
        assessment_id: str,
    ) -> AssessmentResponse | None:
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            row = connection.execute(
                select(
                    AssessmentRecord.assessment,
                    AssessmentRecord.assessment_hash,
                ).where(
                    AssessmentRecord.tenant_id == tenant_id,
                    AssessmentRecord.domain_assessment_id == assessment_id,
                )
            ).one_or_none()
            if row is None:
                return None
            payload = row.assessment
            if payload.get("state") != "COMPLETED":
                return None
            _require_json_hash(
                payload["response"],
                row.assessment_hash,
                "assessment hash",
            )
            return AssessmentResponse.model_validate(payload["response"])

    def save_approval(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        stored: StoredApproval,
        audit_event: StoredAuditEvent,
    ) -> StoredApproval:
        _validate_audit_integrity(audit_event)
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            _lock_idempotency_key(connection, tenant_id, idempotency_key)
            prior = connection.execute(
                _approval_select().where(
                    HumanApprovalRecord.tenant_id == tenant_id,
                    HumanApprovalRecord.idempotency_key == idempotency_key,
                )
            ).one_or_none()
            if prior is not None:
                return _stored_approval(prior)
            assessment_record_id = connection.execute(
                select(AssessmentRecord.id).where(
                    AssessmentRecord.tenant_id == tenant_id,
                    AssessmentRecord.domain_assessment_id
                    == stored.approval.assessment_id,
                )
            ).scalar_one_or_none()
            if assessment_record_id is None:
                raise AssessmentNotFound(stored.approval.assessment_id)
            connection.execute(
                insert(HumanApprovalRecord).values(
                    id=stored.record_id,
                    tenant_id=tenant_id,
                    assessment_id=assessment_record_id,
                    approver_id=stored.approval.approver_id,
                    approved_at=stored.approval.approved_at,
                    idempotency_key=idempotency_key,
                    approval_hash=stored.request_hash,
                )
            )
            connection.execute(
                insert(AuditEvent).values(
                    id=audit_event.record_id,
                    tenant_id=tenant_id,
                    actor_id=audit_event.actor_id,
                    event_type=audit_event.action,
                    entity_type=audit_event.entity_type,
                    entity_id=audit_event.entity_id,
                    payload=audit_event.payload,
                    integrity_hash=audit_event.integrity_hash,
                    previous_event_hash=None,
                )
            )
            return stored

    def get_approval_by_idempotency_key(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> StoredApproval | None:
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            record = connection.execute(
                _approval_select().where(
                    HumanApprovalRecord.tenant_id == tenant_id,
                    HumanApprovalRecord.idempotency_key == idempotency_key,
                )
            ).one_or_none()
            return _stored_approval(record) if record is not None else None

    def get_governance_records(self, tenant_id: UUID) -> GovernanceRecords:
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            evidence_rows = connection.execute(
                select(
                    EvidenceRecord.id,
                    EvidenceRecord.source_id,
                    EvidenceRecord.raw_payload,
                    EvidenceRecord.normalized_payload,
                    EvidenceRecord.raw_payload_hash,
                    EvidenceRecord.normalized_payload_hash,
                    EvidenceRecord.provenance,
                ).where(EvidenceRecord.tenant_id == tenant_id)
            ).all()
            decision_rows = connection.execute(
                select(
                    DecisionRecord.id,
                    DecisionRecord.decision,
                    DecisionRecord.reasons,
                    DecisionRecord.decision_hash,
                    DecisionRecord.provenance,
                ).where(DecisionRecord.tenant_id == tenant_id)
            ).all()
            audit_rows = connection.execute(
                select(
                    AuditEvent.id,
                    AuditEvent.actor_id,
                    AuditEvent.event_type,
                    AuditEvent.entity_type,
                    AuditEvent.entity_id,
                    AuditEvent.payload,
                    AuditEvent.integrity_hash,
                )
                .where(AuditEvent.tenant_id == tenant_id)
                .order_by(AuditEvent.occurred_at, AuditEvent.id)
            ).all()

        return GovernanceRecords(
            evidence_records=tuple(
                StoredEvidenceRecord(
                    record_id=row.id,
                    source_id=row.source_id,
                    raw_payload=row.raw_payload,
                    normalized_payload=row.normalized_payload,
                    raw_payload_hash=row.raw_payload_hash,
                    normalized_payload_hash=row.normalized_payload_hash,
                    provenance=row.provenance,
                )
                for row in evidence_rows
            ),
            decision_records=tuple(
                _stored_decision_record(row) for row in decision_rows
            ),
            audit_events=tuple(
                StoredAuditEvent(
                    record_id=row.id,
                    actor_id=row.actor_id,
                    action=row.event_type,
                    entity_type=row.entity_type,
                    entity_id=row.entity_id,
                    payload=row.payload,
                    integrity_hash=row.integrity_hash,
                )
                for row in audit_rows
            ),
        )


class AssessmentNotFound(Exception):
    def __init__(self, assessment_id: str) -> None:
        super().__init__(assessment_id)
        self.assessment_id = assessment_id


class IdempotencyConflict(Exception):
    pass


class ReservationStateError(RuntimeError):
    pass


class PersistenceIntegrityError(RuntimeError):
    pass


class AssessmentService:
    def __init__(
        self,
        repository: AssessmentRepository,
        engine_registry: EngineRegistry | None = None,
    ) -> None:
        self._repository = repository
        self._engine_registry = engine_registry or foundation_engine_registry()

    def create_assessment(
        self,
        tenant_id: UUID,
        actor_id: str,
        idempotency_key: str,
        request: AssessmentInput,
    ) -> AssessmentResponse:
        request_hash = _model_hash(request)
        reservation = self._repository.reserve_assessment(
            tenant_id,
            idempotency_key,
            request_hash,
            request.provenance.model_dump(mode="json"),
        )
        if not reservation.execute:
            if reservation.response is None:
                raise ReservationStateError("completed reservation has no response")
            return reservation.response

        try:
            heartbeat = _ReservationHeartbeat(
                self._repository,
                tenant_id,
                idempotency_key,
                request_hash,
                reservation,
            )
            heartbeat.start()
            assessment_id = reservation.assessment_id
            engine_outputs: dict[str, BaseModel] = {}
            for registration in self._engine_registry.registrations:
                stored_output = self._repository.get_engine_output(
                    tenant_id,
                    assessment_id,
                    reservation,
                    registration.name,
                )
                if stored_output is None:
                    output = registration.run(request)
                    output_payload = output.model_dump(mode="json")
                    self._repository.save_engine_output(
                        tenant_id,
                        assessment_id,
                        reservation,
                        StoredEngineOutput(
                            engine_name=registration.name,
                            output=output_payload,
                            output_hash=_json_hash(output_payload),
                            provenance=request.provenance.model_dump(mode="json"),
                        ),
                    )
                else:
                    output = registration.output_model.model_validate(
                        stored_output.output
                    )
                engine_outputs[registration.name] = output

            economics_output = engine_outputs.get("economics")
            if not isinstance(economics_output, EconomicsAssessment):
                raise EngineContractError(
                    "registry must provide an EconomicsAssessment named 'economics'"
                )
            economics = economics_output
            gate_results = evaluate_gates(
                GateContext(
                    requested_decision=request.requested_decision,
                    assessment_id=assessment_id,
                    economics_assessment=economics,
                    compliance_passed=request.compliance_passed,
                    liquidity_passed=request.liquidity_passed,
                    data_quality_passed=request.data_quality_passed,
                    sample_size_passed=request.sample_size_passed,
                    operational_recency_passed=request.operational_recency_passed,
                    stop_loss_registered=request.stop_loss_registered,
                    human_approval=None,
                )
            )
            response = AssessmentResponse(
                assessment_id=assessment_id,
                data=AssessmentData(
                    economics=economics,
                    gate_results=gate_results,
                ),
                decision_reasons=economics.decision_reasons,
                missingness_status=economics.missingness_status,
                data_quality_status=(
                    DataQualityStatus.GOOD
                    if request.data_quality_passed
                    else DataQualityStatus.POOR
                ),
                review_status=ReviewStatus.PENDING,
                uncertainty=economics.uncertainty,
                provenance=request.provenance,
            )
            heartbeat.stop_and_verify()
            self._repository.renew_assessment(
                tenant_id,
                idempotency_key,
                request_hash,
                reservation,
            )
            self._repository.complete_assessment(
                tenant_id,
                idempotency_key,
                request_hash,
                reservation,
                _assessment_completion(request, response, actor_id),
            )
            return response
        except Exception:
            if "heartbeat" in locals():
                heartbeat.stop()
            self._repository.fail_assessment(
                tenant_id,
                idempotency_key,
                request_hash,
                reservation,
            )
            raise

    def get_assessment(
        self,
        tenant_id: UUID,
        assessment_id: str,
    ) -> AssessmentResponse:
        assessment = self._repository.get_assessment(tenant_id, assessment_id)
        if assessment is None:
            raise AssessmentNotFound(assessment_id)
        return assessment

    def approve_assessment(
        self,
        tenant_id: UUID,
        assessment_id: str,
        approver_id: str,
        idempotency_key: str,
        approved_at: datetime | None,
    ) -> HumanApproval:
        self.get_assessment(tenant_id, assessment_id)
        approval_request = ApprovalRequestIdentity(
            assessment_id=assessment_id,
            approver_id=approver_id,
            approved_at=approved_at,
        )
        request_hash = _model_hash(approval_request)
        prior = self._repository.get_approval_by_idempotency_key(
            tenant_id,
            idempotency_key,
        )
        if prior is not None:
            if prior.request_hash != request_hash:
                raise IdempotencyConflict
            return prior.approval
        stored = self._repository.save_approval(
            tenant_id,
            idempotency_key,
            stored_approval := StoredApproval(
                request_hash=request_hash,
                approval=HumanApproval(
                    approver_id=approver_id,
                    approved_at=approved_at or datetime.now(UTC),
                    assessment_id=assessment_id,
                ),
            ),
            _approval_audit_event(stored_approval),
        )
        if stored.request_hash != request_hash:
            raise IdempotencyConflict
        return stored.approval


class ApprovalRequestIdentity(BaseModel):
    assessment_id: str
    approver_id: str
    approved_at: datetime | None


class EngineContractError(RuntimeError):
    pass


def foundation_engine_registry() -> EngineRegistry:
    economics_engine = EconomicsEngine()
    return EngineRegistry(
        (
            EngineRegistration(
                name="economics",
                run=lambda request: economics_engine.assess(
                    request.economics,
                    request.provenance,
                ),
                output_model=EconomicsAssessment,
            ),
        )
    )


def _model_hash(model: BaseModel) -> str:
    payload = model.model_dump_json(exclude_none=False)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_hash(payload: object) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _assessment_completion(
    request: AssessmentInput,
    response: AssessmentResponse,
    actor_id: str,
) -> AssessmentCompletion:
    evidence_record_id = uuid4()
    decision_record_id = uuid4()
    economics_payload = request.economics.model_dump(mode="json")
    provenance = request.provenance.model_dump(mode="json")
    evidence = StoredEvidenceRecord(
        record_id=evidence_record_id,
        source_id=request.provenance.source_ids[0],
        raw_payload=economics_payload,
        normalized_payload=economics_payload,
        raw_payload_hash=_json_hash(economics_payload),
        normalized_payload_hash=_json_hash(economics_payload),
        provenance=provenance,
    )
    gate_reasons = tuple(
        result.model_dump(mode="json") for result in response.data.gate_results
    )
    recommended_decision = _recommended_decision(
        request.requested_decision,
        response.data.gate_results,
    )
    decision_payload = {
        "requested_decision": request.requested_decision.value,
        "recommended_decision": recommended_decision.value,
        "gate_reasons": list(gate_reasons),
    }
    decision = StoredDecisionRecord(
        record_id=decision_record_id,
        requested_decision=request.requested_decision.value,
        recommended_decision=recommended_decision.value,
        gate_reasons=gate_reasons,
        decision_hash=_json_hash(decision_payload),
        provenance=provenance,
    )
    audit_payload = {
        "assessment_id": response.assessment_id,
        "decision_record_id": str(decision_record_id),
        "evidence_record_id": str(evidence_record_id),
    }
    audit_event = _new_audit_event(
        actor_id=actor_id,
        action="assessment.created",
        entity_type="assessment",
        entity_id=response.assessment_id,
        payload=audit_payload,
    )
    return AssessmentCompletion(
        response=response,
        evidence=evidence,
        decision=decision,
        audit_event=audit_event,
    )


def _approval_audit_event(stored: StoredApproval) -> StoredAuditEvent:
    approval = stored.approval
    return _new_audit_event(
        actor_id=approval.approver_id,
        action="assessment.approved",
        entity_type="human_approval",
        entity_id=str(stored.record_id),
        payload={
            "approval_record_id": str(stored.record_id),
            "assessment_id": approval.assessment_id,
            "approver_id": approval.approver_id,
        },
    )


def _new_audit_event(
    *,
    actor_id: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
) -> StoredAuditEvent:
    record_id = uuid4()
    event_without_hash = {
        "record_id": str(record_id),
        "actor_id": actor_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payload": payload,
    }
    return StoredAuditEvent(
        record_id=record_id,
        actor_id=actor_id,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        payload=payload,
        integrity_hash=_json_hash(event_without_hash),
    )


def _recommended_decision(
    requested_decision: Decision,
    gate_results: tuple[GateResult, ...],
) -> Decision:
    if any(result.blocks_decision and not result.passed for result in gate_results):
        return Decision.HOLD
    return requested_decision


def _validate_completion_integrity(completion: AssessmentCompletion) -> None:
    _require_json_hash(
        completion.evidence.raw_payload,
        completion.evidence.raw_payload_hash,
        "evidence raw payload hash",
    )
    _require_json_hash(
        completion.evidence.normalized_payload,
        completion.evidence.normalized_payload_hash,
        "evidence normalized payload hash",
    )
    decision_payload = {
        "requested_decision": completion.decision.requested_decision,
        "recommended_decision": completion.decision.recommended_decision,
        "gate_reasons": list(completion.decision.gate_reasons),
    }
    _require_json_hash(
        decision_payload,
        completion.decision.decision_hash,
        "decision hash",
    )
    expected_audit_payload = {
        "assessment_id": completion.response.assessment_id,
        "decision_record_id": str(completion.decision.record_id),
        "evidence_record_id": str(completion.evidence.record_id),
    }
    if completion.audit_event.payload != expected_audit_payload:
        raise PersistenceIntegrityError("assessment audit entity IDs do not match")
    _validate_audit_integrity(completion.audit_event)


def _validate_audit_integrity(audit_event: StoredAuditEvent) -> None:
    payload = {
        "record_id": str(audit_event.record_id),
        "actor_id": audit_event.actor_id,
        "action": audit_event.action,
        "entity_type": audit_event.entity_type,
        "entity_id": audit_event.entity_id,
        "payload": audit_event.payload,
    }
    _require_json_hash(payload, audit_event.integrity_hash, "audit event hash")


def _validate_actor_id(actor_id: str) -> None:
    if not actor_id.strip():
        raise ValueError("actor_id must not be blank")
    if len(actor_id) > 255:
        raise ValueError("actor_id must not exceed 255 characters")


def _require_json_hash(payload: object, expected_hash: str, label: str) -> None:
    if _json_hash(payload) != expected_hash:
        raise PersistenceIntegrityError(f"{label} mismatch")


def _memory_reservation(
    stored: _MemoryReservation,
    *,
    execute: bool,
) -> AssessmentReservation:
    return AssessmentReservation(
        assessment_id=stored.assessment_id,
        owner_token=stored.owner_token if execute else str(uuid4()),
        fencing_epoch=stored.fencing_epoch,
        execute=execute,
        response=deepcopy(stored.response),
    )


def _require_reservation_owner(
    stored: _MemoryReservation,
    request_hash: str,
    reservation: AssessmentReservation,
) -> None:
    if stored.request_hash != request_hash:
        raise IdempotencyConflict
    if (
        stored.state != "PENDING"
        or stored.assessment_id != reservation.assessment_id
        or stored.owner_token != reservation.owner_token
        or stored.fencing_epoch != reservation.fencing_epoch
        or stored.lease_expires_at <= datetime.now(UTC)
    ):
        raise ReservationStateError("assessment reservation ownership was lost")


def _pending_payload(
    request_hash: str,
    owner_token: str,
    fencing_epoch: int,
) -> dict[str, object]:
    return {
        "state": "PENDING",
        "request_hash": request_hash,
        "owner_token": owner_token,
        "fencing_epoch": fencing_epoch,
        "retry_semantics": (
            "a failed or expired owner is retried with the same assessment_id"
        ),
    }


def _database_clock() -> Any:
    return func.clock_timestamp(type_=DateTime(timezone=True))


def _database_lease_expiry(lease: timedelta) -> Any:
    return _database_clock() + lease


def _load_reservation(
    connection: Connection,
    tenant_id: UUID,
    idempotency_key: str,
) -> tuple[str, dict[str, Any], bool]:
    row = connection.execute(
        select(
            AssessmentRecord.domain_assessment_id,
            AssessmentRecord.assessment,
            (AssessmentRecord.lease_expires_at > _database_clock()).label(
                "lease_active"
            ),
        ).where(
            AssessmentRecord.tenant_id == tenant_id,
            AssessmentRecord.idempotency_key == idempotency_key,
        )
    ).one_or_none()
    if row is None:
        raise ReservationStateError("assessment reservation is missing")
    return (
        row.domain_assessment_id,
        cast(dict[str, Any], row.assessment),
        row.lease_active is True,
    )


def _require_database_reservation_owner(
    assessment_id: str,
    payload: dict[str, Any],
    lease_active: bool,
    request_hash: str,
    reservation: AssessmentReservation,
) -> None:
    if payload["request_hash"] != request_hash:
        raise IdempotencyConflict
    if (
        payload["state"] != "PENDING"
        or assessment_id != reservation.assessment_id
        or payload["owner_token"] != reservation.owner_token
        or int(payload.get("fencing_epoch", 0)) != reservation.fencing_epoch
        or not lease_active
    ):
        raise ReservationStateError("assessment reservation ownership was lost")


def _require_memory_output_owner(
    reservations: dict[tuple[UUID, str], _MemoryReservation],
    tenant_id: UUID,
    assessment_id: str,
    reservation: AssessmentReservation,
) -> None:
    stored = next(
        (
            item
            for (item_tenant, _), item in reservations.items()
            if item_tenant == tenant_id and item.assessment_id == assessment_id
        ),
        None,
    )
    if stored is None:
        raise ReservationStateError("assessment reservation is missing")
    _require_reservation_owner(stored, stored.request_hash, reservation)


def _lock_and_require_output_owner(
    connection: Connection,
    tenant_id: UUID,
    assessment_id: str,
    reservation: AssessmentReservation,
) -> None:
    idempotency_key = connection.execute(
        select(AssessmentRecord.idempotency_key).where(
            AssessmentRecord.tenant_id == tenant_id,
            AssessmentRecord.domain_assessment_id == assessment_id,
        )
    ).scalar_one_or_none()
    if idempotency_key is None:
        raise ReservationStateError("assessment reservation is missing")
    _lock_idempotency_key(connection, tenant_id, idempotency_key)
    loaded_assessment_id, payload, lease_active = _load_reservation(
        connection,
        tenant_id,
        idempotency_key,
    )
    _require_database_reservation_owner(
        loaded_assessment_id,
        payload,
        lease_active,
        str(payload.get("request_hash", "")),
        reservation,
    )


class _ReservationHeartbeat:
    def __init__(
        self,
        repository: AssessmentRepository,
        tenant_id: UUID,
        idempotency_key: str,
        request_hash: str,
        reservation: AssessmentReservation,
    ) -> None:
        self._repository = repository
        self._tenant_id = tenant_id
        self._idempotency_key = idempotency_key
        self._request_hash = request_hash
        self._reservation = reservation
        self._stop = Event()
        self._error: BaseException | None = None
        self._thread = Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        interval = self._repository.heartbeat_interval_seconds
        while not self._stop.wait(interval):
            try:
                self._repository.renew_assessment(
                    self._tenant_id,
                    self._idempotency_key,
                    self._request_hash,
                    self._reservation,
                )
            except BaseException as error:
                self._error = error
                self._stop.set()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join()

    def stop_and_verify(self) -> None:
        self.stop()
        if self._error is not None:
            raise ReservationStateError(
                "assessment reservation heartbeat failed"
            ) from self._error


def _stored_approval(record: Row[Any]) -> StoredApproval:
    return StoredApproval(
        request_hash=record.approval_hash,
        approval=HumanApproval(
            approver_id=record.approver_id,
            approved_at=record.approved_at,
            assessment_id=record.domain_assessment_id,
        ),
        record_id=record.id,
    )


def _approval_select() -> Select[tuple[UUID, str, str, datetime, str]]:
    return select(
        HumanApprovalRecord.id,
        HumanApprovalRecord.approval_hash,
        HumanApprovalRecord.approver_id,
        HumanApprovalRecord.approved_at,
        AssessmentRecord.domain_assessment_id,
    ).join(
        AssessmentRecord,
        (AssessmentRecord.tenant_id == HumanApprovalRecord.tenant_id)
        & (AssessmentRecord.id == HumanApprovalRecord.assessment_id),
    )


def _stored_decision_record(record: Row[Any]) -> StoredDecisionRecord:
    reasons = cast(dict[str, Any], record.reasons)
    requested_decision = str(reasons.get("requested_decision", record.decision))
    recommended_decision = str(reasons.get("recommended_decision", record.decision))
    gate_reasons = tuple(
        cast(dict[str, Any], reason) for reason in reasons.get("gate_reasons", [])
    )
    decision_payload = {
        "requested_decision": requested_decision,
        "recommended_decision": recommended_decision,
        "gate_reasons": list(gate_reasons),
    }
    _require_json_hash(decision_payload, record.decision_hash, "decision hash")
    return StoredDecisionRecord(
        record_id=record.id,
        requested_decision=requested_decision,
        recommended_decision=recommended_decision,
        gate_reasons=gate_reasons,
        decision_hash=record.decision_hash,
        provenance=record.provenance,
    )


def _lock_idempotency_key(
    connection: Connection,
    tenant_id: UUID,
    idempotency_key: str,
) -> None:
    connection.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"{tenant_id}:{idempotency_key}"},
    )
