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


def _validate_provisioned_roles() -> None:
    op.execute(
        """
        DO $$
        DECLARE
            app_role pg_roles%ROWTYPE;
        BEGIN
            SELECT * INTO app_role FROM pg_roles WHERE rolname = 'thinc_app';
            IF NOT FOUND THEN
                RAISE EXCEPTION 'Required PostgreSQL role thinc_app is missing'
                    USING ERRCODE = '42704';
            END IF;
            IF current_user = 'thinc_app' THEN
                RAISE EXCEPTION 'Migration role and thinc_app must be distinct'
                    USING ERRCODE = '42501';
            END IF;
            IF NOT app_role.rolcanlogin THEN
                RAISE EXCEPTION 'thinc_app must have LOGIN'
                    USING ERRCODE = '42501';
            END IF;
            IF app_role.rolsuper OR app_role.rolbypassrls
                OR app_role.rolcreatedb OR app_role.rolcreaterole THEN
                RAISE EXCEPTION
                    'thinc_app has forbidden privileged role attributes'
                    USING ERRCODE = '42501';
            END IF;
            IF pg_has_role('thinc_app', current_user, 'MEMBER') THEN
                RAISE EXCEPTION 'thinc_app must not inherit the migration owner role'
                    USING ERRCODE = '42501';
            END IF;
            IF EXISTS (
                SELECT 1
                FROM pg_roles inherited_role
                WHERE inherited_role.rolname <> 'thinc_app'
                  AND pg_has_role('thinc_app', inherited_role.oid, 'MEMBER')
                  AND (
                      inherited_role.rolsuper
                      OR inherited_role.rolbypassrls
                      OR inherited_role.rolcreatedb
                      OR inherited_role.rolcreaterole
                  )
            ) THEN
                RAISE EXCEPTION 'thinc_app inherits a privileged role'
                    USING ERRCODE = '42501';
            END IF;
            IF has_database_privilege(
                'thinc_app', current_database(), 'CREATE'
            ) OR has_schema_privilege('thinc_app', 'public', 'CREATE') THEN
                RAISE EXCEPTION 'thinc_app must not have effective DDL privileges'
                    USING ERRCODE = '42501';
            END IF;
        END;
        $$
        """
    )


def upgrade() -> None:
    _validate_provisioned_roles()
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
        sa.Column(
            "domain_assessment_id",
            sa.String(length=255),
            nullable=False,
            comment="Text assessment_id from the domain model",
        ),
        sa.Column("assessment", postgresql.JSONB(), nullable=False),
        sa.Column("assessment_hash", sa.String(length=128), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        _created_at_column(),
        sa.CheckConstraint(
            "btrim(domain_assessment_id) <> ''",
            name="domain_assessment_id_non_blank",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_assessment_records_tenant_id_id",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "domain_assessment_id",
            name="uq_assessment_records_tenant_id_domain_assessment_id",
        ),
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
            nullable=False,
        ),
        sa.Column("decision", sa.String(length=32), nullable=False),
        sa.Column("reasons", postgresql.JSONB(), nullable=False),
        sa.Column("decision_hash", sa.String(length=128), nullable=False),
        sa.Column("provenance", postgresql.JSONB(), nullable=False),
        _created_at_column(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessment_records.tenant_id", "assessment_records.id"],
            name="fk_decision_records_assessment_tenant",
            ondelete="RESTRICT",
        ),
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
            nullable=False,
        ),
        sa.Column("approver_id", sa.String(length=255), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approval_hash", sa.String(length=128), nullable=False),
        _created_at_column(),
        sa.ForeignKeyConstraint(
            ["tenant_id", "assessment_id"],
            ["assessment_records.tenant_id", "assessment_records.id"],
            name="fk_human_approval_records_assessment_tenant",
            ondelete="RESTRICT",
        ),
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
        CREATE FUNCTION public.reject_audit_event_mutation()
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
        FOR EACH ROW EXECUTE FUNCTION public.reject_audit_event_mutation()
        """
    )
    op.execute(
        "REVOKE ALL PRIVILEGES ON FUNCTION "
        "public.reject_audit_event_mutation() FROM PUBLIC, thinc_app"
    )
    op.execute("GRANT USAGE ON SCHEMA public TO thinc_app")
    op.execute("REVOKE ALL PRIVILEGES ON tenants FROM PUBLIC, thinc_app")
    op.execute("GRANT SELECT ON tenants TO thinc_app")
    for table_name in BUSINESS_TABLE_NAMES[:-1]:
        op.execute(f"REVOKE ALL PRIVILEGES ON {table_name} FROM PUBLIC, thinc_app")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table_name} TO thinc_app")
    op.execute("REVOKE ALL PRIVILEGES ON audit_events FROM PUBLIC, thinc_app")
    op.execute("GRANT SELECT, INSERT ON audit_events TO thinc_app")
    op.execute("REVOKE UPDATE, DELETE ON audit_events FROM thinc_app")


def downgrade() -> None:
    op.drop_table("audit_events")
    op.execute("DROP FUNCTION public.reject_audit_event_mutation()")
    op.drop_table("human_approval_records")
    op.drop_table("decision_records")
    op.drop_table("assessment_records")
    op.drop_table("evidence_records")
    op.drop_table("tenants")
    op.execute("REVOKE USAGE ON SCHEMA public FROM thinc_app")
