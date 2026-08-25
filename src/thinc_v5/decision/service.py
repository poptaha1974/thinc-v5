from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel
from sqlalchemy import insert, select, text
from sqlalchemy.engine import Connection, Engine, Row
from sqlalchemy.sql import Select

from thinc_v5.db.models import AssessmentRecord, HumanApprovalRecord
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


@dataclass(frozen=True)
class StoredAssessment:
    request_hash: str
    response: AssessmentResponse


@dataclass(frozen=True)
class StoredApproval:
    request_hash: str
    approval: HumanApproval


class AssessmentRepository(Protocol):
    def get_by_idempotency_key(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> StoredAssessment | None: ...

    def save_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        stored: StoredAssessment,
    ) -> StoredAssessment: ...

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
    ) -> StoredApproval: ...

    def get_approval_by_idempotency_key(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> StoredApproval | None: ...


class InMemoryAssessmentRepository:
    """Tenant-isolated test repository; it is not production persistence."""

    def __init__(self) -> None:
        self._lock = RLock()
        self._by_idempotency: dict[tuple[UUID, str], StoredAssessment] = {}
        self._by_id: dict[tuple[UUID, str], AssessmentResponse] = {}
        self._approvals: dict[tuple[UUID, str], StoredApproval] = {}
        self._approval_idempotency: dict[tuple[UUID, str], StoredApproval] = {}

    def get_by_idempotency_key(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> StoredAssessment | None:
        with self._lock:
            stored = self._by_idempotency.get((tenant_id, idempotency_key))
            return deepcopy(stored)

    def save_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        stored: StoredAssessment,
    ) -> StoredAssessment:
        with self._lock:
            key = (tenant_id, idempotency_key)
            prior = self._by_idempotency.get(key)
            if prior is not None:
                return deepcopy(prior)
            copied = deepcopy(stored)
            self._by_idempotency[key] = copied
            self._by_id[(tenant_id, stored.response.assessment_id)] = deepcopy(
                stored.response
            )
            return deepcopy(copied)

    def get_assessment(
        self,
        tenant_id: UUID,
        assessment_id: str,
    ) -> AssessmentResponse | None:
        with self._lock:
            return deepcopy(self._by_id.get((tenant_id, assessment_id)))

    def save_approval(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        stored: StoredApproval,
    ) -> StoredApproval:
        with self._lock:
            approval = stored.approval
            if (tenant_id, approval.assessment_id) not in self._by_id:
                raise AssessmentNotFound(approval.assessment_id)
            idempotency_key_with_tenant = (tenant_id, idempotency_key)
            prior = self._approval_idempotency.get(idempotency_key_with_tenant)
            if prior is not None:
                return deepcopy(prior)
            copied = deepcopy(stored)
            self._approval_idempotency[idempotency_key_with_tenant] = copied
            self._approvals[(tenant_id, approval.assessment_id)] = copied
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


class SqlAlchemyAssessmentRepository:
    """PostgreSQL adapter that applies Task 5 transaction-local RLS context."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_by_idempotency_key(
        self,
        tenant_id: UUID,
        idempotency_key: str,
    ) -> StoredAssessment | None:
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            payload = connection.execute(
                select(AssessmentRecord.assessment).where(
                    AssessmentRecord.tenant_id == tenant_id,
                    AssessmentRecord.idempotency_key == idempotency_key,
                )
            ).scalar_one_or_none()
            return _stored_assessment(payload) if payload is not None else None

    def save_assessment(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        stored: StoredAssessment,
    ) -> StoredAssessment:
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            _lock_idempotency_key(connection, tenant_id, idempotency_key)
            prior_payload = connection.execute(
                select(AssessmentRecord.assessment).where(
                    AssessmentRecord.tenant_id == tenant_id,
                    AssessmentRecord.idempotency_key == idempotency_key,
                )
            ).scalar_one_or_none()
            if prior_payload is not None:
                return _stored_assessment(prior_payload)
            response_payload = stored.response.model_dump(mode="json")
            connection.execute(
                insert(AssessmentRecord).values(
                    id=UUID(stored.response.assessment_id),
                    tenant_id=tenant_id,
                    domain_assessment_id=stored.response.assessment_id,
                    idempotency_key=idempotency_key,
                    assessment={
                        "request_hash": stored.request_hash,
                        "response": response_payload,
                    },
                    assessment_hash=_json_hash(response_payload),
                    provenance=stored.response.provenance.model_dump(mode="json"),
                )
            )
            return stored

    def get_assessment(
        self,
        tenant_id: UUID,
        assessment_id: str,
    ) -> AssessmentResponse | None:
        with self._engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            payload = connection.execute(
                select(AssessmentRecord.assessment).where(
                    AssessmentRecord.tenant_id == tenant_id,
                    AssessmentRecord.domain_assessment_id == assessment_id,
                )
            ).scalar_one_or_none()
            if payload is None:
                return None
            return AssessmentResponse.model_validate(payload["response"])

    def save_approval(
        self,
        tenant_id: UUID,
        idempotency_key: str,
        stored: StoredApproval,
    ) -> StoredApproval:
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
                    id=uuid4(),
                    tenant_id=tenant_id,
                    assessment_id=assessment_record_id,
                    approver_id=stored.approval.approver_id,
                    approved_at=stored.approval.approved_at,
                    idempotency_key=idempotency_key,
                    approval_hash=stored.request_hash,
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


class AssessmentNotFound(Exception):
    def __init__(self, assessment_id: str) -> None:
        super().__init__(assessment_id)
        self.assessment_id = assessment_id


class IdempotencyConflict(Exception):
    pass


class AssessmentService:
    def __init__(
        self,
        repository: AssessmentRepository,
        economics_engine: EconomicsEngine | None = None,
    ) -> None:
        self._repository = repository
        self._economics_engine = economics_engine or EconomicsEngine()

    def create_assessment(
        self,
        tenant_id: UUID,
        actor_id: str,
        idempotency_key: str,
        request: AssessmentInput,
    ) -> AssessmentResponse:
        del actor_id  # Reserved for the durable audit adapter.
        request_hash = _model_hash(request)
        prior = self._repository.get_by_idempotency_key(
            tenant_id,
            idempotency_key,
        )
        if prior is not None:
            if prior.request_hash != request_hash:
                raise IdempotencyConflict
            return prior.response

        assessment_id = str(uuid4())
        economics = self._economics_engine.assess(
            request.economics,
            request.provenance,
        )
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
        stored = self._repository.save_assessment(
            tenant_id,
            idempotency_key,
            StoredAssessment(request_hash=request_hash, response=response),
        )
        if stored.request_hash != request_hash:
            raise IdempotencyConflict
        return stored.response

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
            StoredApproval(
                request_hash=request_hash,
                approval=HumanApproval(
                    approver_id=approver_id,
                    approved_at=approved_at or datetime.now(UTC),
                    assessment_id=assessment_id,
                ),
            ),
        )
        if stored.request_hash != request_hash:
            raise IdempotencyConflict
        return stored.approval


class ApprovalRequestIdentity(BaseModel):
    assessment_id: str
    approver_id: str
    approved_at: datetime | None


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


def _stored_assessment(payload: dict[str, Any]) -> StoredAssessment:
    return StoredAssessment(
        request_hash=str(payload["request_hash"]),
        response=AssessmentResponse.model_validate(payload["response"]),
    )


def _stored_approval(record: Row[Any]) -> StoredApproval:
    return StoredApproval(
        request_hash=record.approval_hash,
        approval=HumanApproval(
            approver_id=record.approver_id,
            approved_at=record.approved_at,
            assessment_id=record.domain_assessment_id,
        ),
    )


def _approval_select() -> Select[tuple[str, str, datetime, str]]:
    return (
        select(
            HumanApprovalRecord.approval_hash,
            HumanApprovalRecord.approver_id,
            HumanApprovalRecord.approved_at,
            AssessmentRecord.domain_assessment_id,
        )
        .join(
            AssessmentRecord,
            (AssessmentRecord.tenant_id == HumanApprovalRecord.tenant_id)
            & (AssessmentRecord.id == HumanApprovalRecord.assessment_id),
        )
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
