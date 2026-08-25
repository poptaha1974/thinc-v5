"""Add tenant-scoped idempotency keys for assessment API writes.

Revision ID: 0002_assessment_api_idempotency
Revises: 0001_foundation
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_assessment_api_idempotency"
down_revision: str | None = "0001_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "assessment_records",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_assessment_records_tenant_id_idempotency_key",
        "assessment_records",
        ["tenant_id", "idempotency_key"],
    )
    op.add_column(
        "human_approval_records",
        sa.Column("idempotency_key", sa.String(length=255), nullable=True),
    )
    op.create_unique_constraint(
        "uq_human_approval_records_tenant_id_idempotency_key",
        "human_approval_records",
        ["tenant_id", "idempotency_key"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_human_approval_records_tenant_id_idempotency_key",
        "human_approval_records",
        type_="unique",
    )
    op.drop_column("human_approval_records", "idempotency_key")
    op.drop_constraint(
        "uq_assessment_records_tenant_id_idempotency_key",
        "assessment_records",
        type_="unique",
    )
    op.drop_column("assessment_records", "idempotency_key")
