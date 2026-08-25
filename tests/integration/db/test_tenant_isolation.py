from __future__ import annotations

import io
import uuid
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import Engine, exc, inspect, text

from alembic import command
from thinc_v5.db.models import BUSINESS_TABLE_NAMES
from thinc_v5.db.session import set_tenant_context

from .conftest import PROJECT_ROOT, MigratedDatabase, alembic_config, safe_downgrade


def test_offline_migration_enables_and_forces_rls_for_every_business_table() -> None:
    output = io.StringIO()
    config = Config(str(PROJECT_ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://offline")

    command.upgrade(config, "head", sql=True)

    sql = output.getvalue()
    for table_name in BUSINESS_TABLE_NAMES:
        assert f"ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY" in sql
        assert f"ALTER TABLE {table_name} FORCE ROW LEVEL SECURITY" in sql
        assert f"CREATE POLICY tenant_isolation ON {table_name}" in sql
    assert "current_setting('app.tenant_id', true)::uuid" in sql
    assert "domain_assessment_id VARCHAR(255) NOT NULL" in sql
    assert "uq_assessment_records_tenant_id_id" in sql
    assert "uq_assessment_records_tenant_id_domain_assessment_id" in sql
    assert (
        "CONSTRAINT ck_assessment_records_domain_assessment_id_non_blank CHECK" in sql
    )
    assert (
        "FOREIGN KEY(tenant_id, assessment_id) REFERENCES assessment_records "
        "(tenant_id, id) ON DELETE RESTRICT"
    ) in sql


def test_offline_migration_quarantines_orphan_engine_outputs_before_fk() -> None:
    output = io.StringIO()
    config = Config(str(PROJECT_ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://offline")

    command.upgrade(config, "head", sql=True)

    sql = output.getvalue()
    create_at = sql.index("CREATE TABLE engine_output_quarantine")
    quarantine_at = sql.index("INSERT INTO engine_output_quarantine")
    delete_at = sql.index("DELETE FROM engine_output_records")
    fk_at = sql.index("fk_engine_output_records_assessment_tenant")
    assert create_at < quarantine_at < delete_at < fk_at
    assert "NOT EXISTS" in sql[quarantine_at:fk_at]
    assert "orphaned before tenant-aware assessment foreign key" in sql
    assert "quarantined_at" in sql


def test_upgrade_from_0003_quarantines_existing_orphan_engine_output(
    database_url: str,
    migrated_database: MigratedDatabase,
) -> None:
    config = alembic_config(database_url)
    command.downgrade(config, "0003_engine_output_records")
    tenant_id = uuid.uuid4()
    output_id = uuid.uuid4()
    with migrated_database.migration_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": tenant_id, "slug": f"tenant-{tenant_id}", "name": "Tenant"},
        )
        set_tenant_context(connection, tenant_id)
        connection.execute(
            text(
                "INSERT INTO engine_output_records "
                "(id, tenant_id, assessment_id, engine_name, output, "
                "output_hash, provenance) VALUES "
                "(:id, :tenant_id, 'missing-assessment', 'economics', "
                "CAST(:output AS jsonb), 'sha256:orphan', "
                "CAST(:provenance AS jsonb))"
            ),
            {
                "id": output_id,
                "tenant_id": tenant_id,
                "output": '{"value": "preserve-me"}',
                "provenance": '{"source_ids": ["legacy-source"]}',
            },
        )

    command.upgrade(config, "head")

    with migrated_database.migration_engine.connect() as connection:
        orphan = connection.execute(
            text("SELECT id FROM engine_output_records WHERE id = :id"),
            {"id": output_id},
        ).one_or_none()
        quarantined = connection.execute(
            text(
                "SELECT tenant_id, source_output_id, assessment_id, engine_name, "
                "output, output_hash, provenance, quarantine_reason, "
                "quarantined_at FROM engine_output_quarantine "
                "WHERE source_output_id = :id"
            ),
            {"id": output_id},
        ).one()

    assert orphan is None
    assert quarantined.tenant_id == tenant_id
    assert quarantined.assessment_id == "missing-assessment"
    assert quarantined.engine_name == "economics"
    assert quarantined.output == {"value": "preserve-me"}
    assert quarantined.output_hash == "sha256:orphan"
    assert quarantined.provenance == {"source_ids": ["legacy-source"]}
    assert quarantined.quarantine_reason == (
        "orphaned before tenant-aware assessment foreign key"
    )
    assert quarantined.quarantined_at is not None


def test_upgrade_downgrade_reupgrade_recreates_identical_schema(
    database_url: str,
    migrated_database: MigratedDatabase,
) -> None:
    config = alembic_config(database_url)
    first = _schema_snapshot(migrated_database.migration_engine)

    safe_downgrade(config)
    base = _schema_snapshot(migrated_database.migration_engine)
    assert base == _empty_schema_snapshot()
    command.upgrade(config, "head")

    assert _schema_snapshot(migrated_database.migration_engine) == first


def test_assessments_cannot_be_read_across_tenants(
    migrated_database: MigratedDatabase,
) -> None:
    tenant_a, tenant_b = _create_tenants(migrated_database.migration_engine)
    assessment_id = uuid.uuid4()

    with migrated_database.app_engine.begin() as connection:
        set_tenant_context(connection, tenant_a)
        _insert_assessment(connection, tenant_a, assessment_id, "assessment-a")
    with migrated_database.app_engine.begin() as connection:
        set_tenant_context(connection, tenant_b)
        all_rows = connection.execute(text("SELECT id FROM assessment_records")).all()
        direct_row = connection.execute(
            text("SELECT id FROM assessment_records WHERE id = :id"),
            {"id": assessment_id},
        ).first()

    assert all_rows == []
    assert direct_row is None


def test_cross_tenant_assessment_reference_is_rejected(
    migrated_database: MigratedDatabase,
) -> None:
    tenant_a, tenant_b = _create_tenants(migrated_database.migration_engine)
    assessment_id = uuid.uuid4()

    with migrated_database.app_engine.begin() as connection:
        set_tenant_context(connection, tenant_a)
        _insert_assessment(connection, tenant_a, assessment_id, "assessment-a")
    with pytest.raises(exc.IntegrityError) as error:
        with migrated_database.app_engine.begin() as connection:
            set_tenant_context(connection, tenant_b)
            connection.execute(
                text(
                    "INSERT INTO decision_records "
                    "(id, tenant_id, assessment_id, decision, reasons, "
                    "decision_hash, provenance) VALUES "
                    "(:id, :tenant_id, :assessment_id, 'HOLD', "
                    "CAST(:reasons AS jsonb), :decision_hash, "
                    "CAST(:provenance AS jsonb))"
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant_id": tenant_b,
                    "assessment_id": assessment_id,
                    "reasons": '["cross-tenant attempt"]',
                    "decision_hash": "sha256:decision",
                    "provenance": '{"source_ids": ["evidence-b"]}',
                },
            )

    assert getattr(error.value.orig, "sqlstate", None) == "23503"


def _create_tenants(engine: Engine) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    with engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO tenants (id, slug, name) VALUES "
                "(:tenant_a, :slug_a, 'Tenant A'), "
                "(:tenant_b, :slug_b, 'Tenant B')"
            ),
            {
                "tenant_a": tenant_a,
                "slug_a": f"tenant-{tenant_a}",
                "tenant_b": tenant_b,
                "slug_b": f"tenant-{tenant_b}",
            },
        )
    return tenant_a, tenant_b


def _insert_assessment(
    connection: Any,
    tenant_id: uuid.UUID,
    assessment_id: uuid.UUID,
    domain_assessment_id: str,
) -> None:
    connection.execute(
        text(
            "INSERT INTO assessment_records "
            "(id, tenant_id, domain_assessment_id, assessment, "
            "assessment_hash, provenance) VALUES "
            "(:id, :tenant_id, :domain_assessment_id, "
            "CAST(:assessment AS jsonb), :assessment_hash, "
            "CAST(:provenance AS jsonb))"
        ),
        {
            "id": assessment_id,
            "tenant_id": tenant_id,
            "domain_assessment_id": domain_assessment_id,
            "assessment": '{"score": 91}',
            "assessment_hash": "sha256:assessment-a",
            "provenance": '{"source_ids": ["evidence-a"]}',
        },
    )


def _schema_snapshot(engine: Engine) -> dict[str, object]:
    inspector = inspect(engine)
    table_names = sorted(
        table for table in inspector.get_table_names() if table != "alembic_version"
    )
    tables = {
        table: {
            "columns": [
                (
                    column["name"],
                    str(column["type"]),
                    column["nullable"],
                    column["default"],
                )
                for column in inspector.get_columns(table)
            ],
            "primary_key": inspector.get_pk_constraint(table),
            "foreign_keys": inspector.get_foreign_keys(table),
            "unique_constraints": inspector.get_unique_constraints(table),
            "check_constraints": inspector.get_check_constraints(table),
            "indexes": inspector.get_indexes(table),
        }
        for table in table_names
    }
    with engine.connect() as connection:
        return {
            "tables": tables,
            "policies": _rows(
                connection,
                "SELECT tablename, policyname, roles, cmd, qual, with_check "
                "FROM pg_policies WHERE schemaname = current_schema() "
                "AND tablename = ANY(:tables) ORDER BY tablename, policyname",
                table_names,
            ),
            "rls": _rows(
                connection,
                "SELECT relname, relrowsecurity, relforcerowsecurity "
                "FROM pg_class JOIN pg_namespace ON pg_namespace.oid = relnamespace "
                "WHERE nspname = current_schema() AND relname = ANY(:tables) "
                "ORDER BY relname",
                table_names,
            ),
            "functions": _rows(
                connection,
                "SELECT proname, pg_get_function_identity_arguments(pg_proc.oid), "
                "pg_get_functiondef(pg_proc.oid), owner.rolname "
                "FROM pg_proc JOIN pg_namespace ns ON ns.oid = pronamespace "
                "JOIN pg_roles owner ON owner.oid = proowner "
                "WHERE ns.nspname = current_schema() "
                "AND proname = 'reject_audit_event_mutation' ORDER BY proname",
            ),
            "schema_acl": _rows(
                connection,
                "SELECT namespace.nspname, grantor.rolname, grantee.rolname, "
                "acl.privilege_type, acl.is_grantable "
                "FROM pg_namespace namespace "
                "CROSS JOIN LATERAL aclexplode(COALESCE(namespace.nspacl, "
                "acldefault('n', namespace.nspowner))) acl "
                "JOIN pg_roles grantor ON grantor.oid = acl.grantor "
                "JOIN pg_roles grantee ON grantee.oid = acl.grantee "
                "WHERE namespace.nspname = current_schema() "
                "AND grantee.rolname = 'thinc_app' "
                "ORDER BY grantor.rolname, acl.privilege_type",
            ),
            "function_acl": _rows(
                connection,
                "SELECT routine.proname, grantor.rolname, "
                "COALESCE(grantee.rolname, 'PUBLIC'), acl.privilege_type, "
                "acl.is_grantable FROM pg_proc routine "
                "JOIN pg_namespace namespace ON namespace.oid = routine.pronamespace "
                "CROSS JOIN LATERAL aclexplode(COALESCE(routine.proacl, "
                "acldefault('f', routine.proowner))) acl "
                "JOIN pg_roles grantor ON grantor.oid = acl.grantor "
                "LEFT JOIN pg_roles grantee ON grantee.oid = acl.grantee "
                "WHERE namespace.nspname = current_schema() "
                "AND routine.proname = 'reject_audit_event_mutation' "
                "ORDER BY grantor.rolname, grantee.rolname, acl.privilege_type",
            ),
            "triggers": _rows(
                connection,
                "SELECT table_name, trigger_name, action_timing, event_manipulation, "
                "action_statement FROM information_schema.triggers "
                "WHERE trigger_schema = current_schema() "
                "AND table_name = ANY(:tables) "
                "ORDER BY table_name, trigger_name, event_manipulation",
                table_names,
            ),
            "grants": _rows(
                connection,
                "SELECT table_name, grantee, privilege_type, is_grantable "
                "FROM information_schema.table_privileges "
                "WHERE table_schema = current_schema() "
                "AND table_name = ANY(:tables) "
                "ORDER BY table_name, grantee, privilege_type",
                table_names,
            ),
            "ownership": _rows(
                connection,
                "SELECT tablename, tableowner FROM pg_tables "
                "WHERE schemaname = current_schema() "
                "AND tablename = ANY(:tables) ORDER BY tablename",
                table_names,
            ),
            "index_definitions": _rows(
                connection,
                "SELECT tablename, indexname, indexdef FROM pg_indexes "
                "WHERE schemaname = current_schema() "
                "AND tablename = ANY(:tables) ORDER BY tablename, indexname",
                table_names,
            ),
        }


def _rows(
    connection: Any,
    statement: str,
    table_names: list[str] | None = None,
) -> list[tuple[Any, ...]]:
    if table_names == []:
        return []
    parameters = {"tables": table_names} if table_names is not None else {}
    return list(connection.execute(text(statement), parameters).tuples())


def _empty_schema_snapshot() -> dict[str, object]:
    return {
        "tables": {},
        "policies": [],
        "rls": [],
        "functions": [],
        "schema_acl": [],
        "function_acl": [],
        "triggers": [],
        "grants": [],
        "ownership": [],
        "index_definitions": [],
    }
