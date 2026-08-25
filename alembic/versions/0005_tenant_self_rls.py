"""Restrict application tenant metadata reads to the current tenant.

Revision ID: 0005_tenant_self_rls
Revises: 0004_engine_output_assessment_fk
Create Date: 2026-08-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0005_tenant_self_rls"
down_revision: str | None = "0004_engine_output_assessment_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("REVOKE ALL PRIVILEGES ON tenants FROM PUBLIC, thinc_app")
    op.execute("GRANT SELECT ON tenants TO thinc_app")
    op.execute("ALTER TABLE tenants ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY tenant_self_access ON tenants FOR SELECT TO thinc_app "
        "USING (id = current_setting('app.tenant_id', true)::uuid)"
    )
    op.execute(
        "CREATE POLICY tenant_owner_management ON tenants TO CURRENT_USER "
        "USING (true) WITH CHECK (true)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY tenant_owner_management ON tenants")
    op.execute("DROP POLICY tenant_self_access ON tenants")
    op.execute("ALTER TABLE tenants NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE tenants DISABLE ROW LEVEL SECURITY")
