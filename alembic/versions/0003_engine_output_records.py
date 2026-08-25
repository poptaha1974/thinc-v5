"""Persist each registered engine output independently.

Revision ID: 0003_engine_output_records
Revises: 0002_assessment_api_idempotency
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0003_engine_output_records"
down_revision: str | None = "0002_assessment_api_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "engine_output_records",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            primary_key=True,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("assessment_id", sa.String(length=255), nullable=False),
        sa.Column("engine_name", sa.String(length=100), nullable=False),
        sa.Column("output", postgresql.JSONB(), nullable=False),
        sa.Column("output_hash", sa.String(length=128), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "assessment_id",
            "engine_name",
            name=(
                "uq_engine_output_records_tenant_id_assessment_id_engine_name"
            ),
        ),
    )
    op.create_index(
        "ix_engine_output_records_tenant_id",
        "engine_output_records",
        ["tenant_id"],
    )
    op.create_index(
        "ix_engine_output_records_assessment_id",
        "engine_output_records",
        ["assessment_id"],
    )
    op.execute("ALTER TABLE engine_output_records ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE engine_output_records FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_isolation ON engine_output_records "
        "USING (tenant_id = current_setting('app.tenant_id', true)::uuid) "
        "WITH CHECK (tenant_id = current_setting('app.tenant_id', true)::uuid)"
    )
    op.execute(
        "REVOKE ALL PRIVILEGES ON engine_output_records FROM PUBLIC, thinc_app"
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON engine_output_records TO thinc_app"
    )


def downgrade() -> None:
    op.drop_table("engine_output_records")
