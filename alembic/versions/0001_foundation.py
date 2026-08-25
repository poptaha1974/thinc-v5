"""Create the tenant-isolated foundation schema.

Revision ID: 0001_foundation
Revises:
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0001_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

BUSINESS_TABLE_NAMES = (
    "evidence_records",
    "assessment_records",
    "decision_records",
    "human_approval_records",
    "audit_events",
)


def _id_column() -> sa.Column[Any]:
    return sa.Column(
        "id", postgresql.UUID(as_uuid=True), nullable=False, primary_key=True
    )


def _tenant_column() -> sa.Column[Any]:
    return sa.Column(
        "tenant_id",
        postgresql.UUID(as_uuid=True),
        sa.ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )


def _created_at_column() -> sa.Column[Any]:
    return sa.Column(
        "created_at",
        sa.DateTime(timezone=True),
        nullable=False,
        server_default=sa.func.now(),
    )


def upgrade() -> None:
    op.create_table(
        "tenants",
        _id_column(),
        sa.Column("slug", sa.String(length=100), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        _created_at_column(),
        sa.UniqueConstraint("slug", name="uq_tenants_slug"),
    )
    op.create_table(
        "evidence_records",
        _id_column(),
        _tenant_column(),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column("raw_payload", postgresql.JSONB(), nullable=False),
        sa.Column("normalized_payload", postgresql.JSONB(), nullable=False),
        sa.Column("raw_payload_hash", sa.String(length=128), nullable=False),
        sa.Column("normalized_payload_hash", sa.String(length=128), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        _created_at_column(),
    )
    op.create_index("ix_evidence_records_tenant_id", "evidence_records", ["tenant_id"])
    op.create_table(
        "assessment_records",
        _id_column(),
        _tenant_column(),
        sa.Column("assessment", postgresql.JSONB(), nullable=False),
        sa.Column("assessment_hash", sa.String(length=128), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        _created_at_column(),
    )
    op.create_index(
        "ix_assessment_records_tenant_id",
        "assessment_records",
        ["tenant_id"],
    )
    op.create_table(
        "decision_records",
        _id_column(),
        _tenant_column(),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
        sa.Column("decision_hash", sa.String(length=128), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        _created_at_column(),
    )
    op.create_index("ix_decision_records_tenant_id", "decision_records", ["tenant_id"])
    op.create_index(
        "ix_decision_records_assessment_id",
        "decision_records",
        ["assessment_id"],
    )
    op.create_table(
        "human_approval_records",
        _id_column(),
        _tenant_column(),
        sa.Column(
            "assessment_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assessment_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("approver_id", sa.String(length=255), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approval_hash", sa.String(length=128), nullable=False),
        _created_at_column(),
    )
    op.create_index(
        "ix_human_approval_records_tenant_id",
        "human_approval_records",
        ["tenant_id"],
    )
    op.create_index(
        "ix_human_approval_records_assessment_id",
        "human_approval_records",
        ["assessment_id"],
    )
    op.create_table(
        "audit_events",
        _id_column(),
        _tenant_column(),
        sa.Column("actor_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("entity_type", sa.String(length=100), nullable=False),
        sa.Column("entity_id", sa.String(length=255), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("integrity_hash", sa.String(length=128), nullable=False),
        sa.Column("previous_event_hash", sa.Text(), nullable=True),
    )
    op.create_index("ix_audit_events_tenant_id", "audit_events", ["tenant_id"])

    for table_name in BUSINESS_TABLE_NAMES:
        op.execute(f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"CREATE POLICY tenant_isolation ON {table_name} "
            "USING (tenant_id = "
            "current_setting('app.tenant_id', true)::uuid) "
            "WITH CHECK (tenant_id = "
            "current_setting('app.tenant_id', true)::uuid)"
        )

    op.execute(
        """
        CREATE FUNCTION reject_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit events are append-only'
                USING ERRCODE = '42501';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW EXECUTE FUNCTION reject_audit_event_mutation()
        """
    )
    op.execute("REVOKE UPDATE, DELETE ON audit_events FROM PUBLIC")
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'thinc_app') THEN
                GRANT SELECT, INSERT ON audit_events TO thinc_app;
                REVOKE UPDATE, DELETE ON audit_events FROM thinc_app;
            END IF;
        END;
        $$
        """
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION reject_audit_event_mutation()")
    op.drop_table("human_approval_records")
    op.drop_table("decision_records")
    op.drop_table("assessment_records")
    op.drop_table("evidence_records")
    op.drop_table("tenants")
