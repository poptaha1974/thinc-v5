from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from thinc_v5.db.base import Base, metadata

BUSINESS_TABLE_NAMES = (
    "evidence_records",
    "assessment_records",
    "engine_output_records",
    "decision_records",
    "human_approval_records",
    "audit_events",
)


class IdMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TenantOwnedMixin:
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )


class CreatedAtMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class Tenant(IdMixin, CreatedAtMixin, Base):
    __tablename__ = "tenants"

    slug: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class EvidenceRecord(IdMixin, TenantOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "evidence_records"

    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    normalized_payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    raw_payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    normalized_payload_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class AssessmentRecord(IdMixin, TenantOwnedMixin, CreatedAtMixin, Base):
    """Persistence UUID plus tenant-scoped mapping to the domain text ID."""

    __tablename__ = "assessment_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_assessment_records_tenant_id_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "domain_assessment_id",
            name="uq_assessment_records_tenant_id_domain_assessment_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_assessment_records_tenant_id_idempotency_key",
        ),
        CheckConstraint(
            "btrim(domain_assessment_id) <> ''",
            name="domain_assessment_id_non_blank",
        ),
    )

    domain_assessment_id: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="Text assessment_id from the domain model",
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assessment: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    assessment_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class EngineOutputRecord(IdMixin, TenantOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "engine_output_records"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "assessment_id",
            "engine_name",
            name=(
                "uq_engine_output_records_tenant_id_assessment_id_engine_name"
            ),
        ),
    )

    assessment_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    engine_name: Mapped[str] = mapped_column(String(100), nullable=False)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    output_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class DecisionRecord(IdMixin, TenantOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "decision_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessment_records.tenant_id", "assessment_records.id"],
            name="fk_decision_records_assessment_tenant",
            ondelete="RESTRICT",
        ),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    reasons: Mapped[list[str]] = mapped_column(JSONB, nullable=False)
    decision_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    provenance: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)


class HumanApprovalRecord(IdMixin, TenantOwnedMixin, CreatedAtMixin, Base):
    __tablename__ = "human_approval_records"
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessment_records.tenant_id", "assessment_records.id"],
            name="fk_human_approval_records_assessment_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_human_approval_records_tenant_id_idempotency_key",
        ),
    )

    assessment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        nullable=False,
        index=True,
    )
    approver_id: Mapped[str] = mapped_column(String(255), nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    approval_hash: Mapped[str] = mapped_column(String(128), nullable=False)


class AuditEvent(IdMixin, TenantOwnedMixin, Base):
    __tablename__ = "audit_events"

    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(100), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(255), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    integrity_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    previous_event_hash: Mapped[str | None] = mapped_column(Text, nullable=True)


__all__ = [
    "AssessmentRecord",
    "AuditEvent",
    "BUSINESS_TABLE_NAMES",
    "DecisionRecord",
    "EngineOutputRecord",
    "EvidenceRecord",
    "HumanApprovalRecord",
    "Tenant",
    "metadata",
]
