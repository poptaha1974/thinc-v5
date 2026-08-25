"""Prevent engine outputs without a tenant-owned assessment reservation.

Revision ID: 0004_engine_output_assessment_fk
Revises: 0003_engine_output_records
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0004_engine_output_assessment_fk"
down_revision: str | None = "0003_engine_output_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engine_output_quarantine",
        sa.Column(
            "source_output_id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            nullable=False,
        ),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assessment_id", sa.String(length=255), nullable=False),
        sa.Column("engine_name", sa.String(length=100), nullable=False),
        sa.Column("output", postgresql.JSONB(), nullable=False),
        sa.Column("output_hash", sa.String(length=128), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column("original_created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quarantine_reason", sa.Text(), nullable=False),
        sa.Column(
            "quarantined_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.execute(
        "REVOKE ALL PRIVILEGES ON engine_output_quarantine FROM PUBLIC, thinc_app"
    )
    op.execute("LOCK TABLE engine_output_records IN ACCESS EXCLUSIVE MODE")
    op.execute("ALTER TABLE engine_output_records NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "INSERT INTO engine_output_quarantine "
        "(source_output_id, tenant_id, assessment_id, engine_name, output, "
        "output_hash, provenance, original_created_at, quarantine_reason) "
        "SELECT output_record.id, output_record.tenant_id, "
        "output_record.assessment_id, output_record.engine_name, "
        "output_record.output, output_record.output_hash, "
        "output_record.provenance, output_record.created_at, "
        "'orphaned before tenant-aware assessment foreign key' "
        "FROM engine_output_records AS output_record "
        "WHERE NOT EXISTS ("
        "SELECT 1 FROM assessment_records AS assessment_record "
        "WHERE assessment_record.tenant_id = output_record.tenant_id "
        "AND assessment_record.domain_assessment_id = output_record.assessment_id"
        ")"
    )
    op.execute(
        "DELETE FROM engine_output_records AS output_record "
        "WHERE NOT EXISTS ("
        "SELECT 1 FROM assessment_records AS assessment_record "
        "WHERE assessment_record.tenant_id = output_record.tenant_id "
        "AND assessment_record.domain_assessment_id = output_record.assessment_id"
        ")"
    )
    op.execute("ALTER TABLE engine_output_records FORCE ROW LEVEL SECURITY")
    op.create_foreign_key(
        "fk_engine_output_records_assessment_tenant",
        "engine_output_records",
        "assessment_records",
        ["tenant_id", "assessment_id"],
        ["tenant_id", "domain_assessment_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_engine_output_records_assessment_tenant",
        "engine_output_records",
        type_="foreignkey",
    )
    op.execute("LOCK TABLE engine_output_records IN ACCESS EXCLUSIVE MODE")
    op.execute("ALTER TABLE engine_output_records NO FORCE ROW LEVEL SECURITY")
    op.execute(
        "INSERT INTO engine_output_records "
        "(id, tenant_id, assessment_id, engine_name, output, output_hash, "
        "provenance, created_at) "
        "SELECT source_output_id, tenant_id, assessment_id, engine_name, output, "
        "output_hash, provenance, original_created_at "
        "FROM engine_output_quarantine ON CONFLICT DO NOTHING"
    )
    op.execute("ALTER TABLE engine_output_records FORCE ROW LEVEL SECURITY")
    op.drop_table("engine_output_quarantine")
