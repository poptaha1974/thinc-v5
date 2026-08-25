"""Prevent engine outputs without a tenant-owned assessment reservation.

Revision ID: 0004_engine_output_assessment_fk
Revises: 0003_engine_output_records
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004_engine_output_assessment_fk"
down_revision: str | None = "0003_engine_output_records"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
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
