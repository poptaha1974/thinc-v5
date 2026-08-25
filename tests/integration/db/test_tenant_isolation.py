from __future__ import annotations

import io
import uuid

from alembic.config import Config
from sqlalchemy import Connection, inspect, text

from alembic import command
from thinc_v5.db.models import BUSINESS_TABLE_NAMES

from .conftest import PROJECT_ROOT, alembic_config


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


def test_upgrade_downgrade_reupgrade_recreates_identical_schema(
    database_url: str,
) -> None:
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    first = _schema_snapshot(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")

    assert _schema_snapshot(database_url) == first


def test_assessments_cannot_be_read_across_tenants(
    migrated_connection: Connection,
) -> None:
    bypasses_rls = migrated_connection.execute(
        text(
            "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
        )
    ).scalar_one()
    assert bypasses_rls is False, (
        "THINC_TEST_DATABASE_URL must use a non-superuser, non-BYPASSRLS role"
    )

    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    assessment_id = uuid.uuid4()

    migrated_connection.execute(
        text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": tenant_a, "slug": f"tenant-{tenant_a}", "name": "Tenant A"},
    )
    migrated_connection.execute(
        text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": tenant_b, "slug": f"tenant-{tenant_b}", "name": "Tenant B"},
    )
    migrated_connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
        {"tenant_id": str(tenant_a)},
    )
    migrated_connection.execute(
        text(
            "INSERT INTO assessment_records "
            "(id, tenant_id, assessment, assessment_hash, provenance) "
            "VALUES (:id, :tenant_id, CAST(:assessment AS jsonb), "
            ":assessment_hash, CAST(:provenance AS jsonb))"
        ),
        {
            "id": assessment_id,
            "tenant_id": tenant_a,
            "assessment": '{"score": 91}',
            "assessment_hash": "sha256:assessment-a",
            "provenance": '{"source_ids": ["evidence-a"]}',
        },
    )
    migrated_connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
        {"tenant_id": str(tenant_b)},
    )

    all_rows = migrated_connection.execute(
        text("SELECT id FROM assessment_records")
    ).all()
    direct_row = migrated_connection.execute(
        text("SELECT id FROM assessment_records WHERE id = :id"),
        {"id": assessment_id},
    ).first()

    assert all_rows == []
    assert direct_row is None


def _schema_snapshot(database_url: str) -> dict[str, object]:
    from sqlalchemy import create_engine

    engine = create_engine(database_url)
    try:
        inspector = inspect(engine)
        table_names = sorted(
            table for table in inspector.get_table_names() if table != "alembic_version"
        )
        tables = {
            table: {
                "columns": [
                    (column["name"], str(column["type"]), column["nullable"])
                    for column in inspector.get_columns(table)
                ],
                "foreign_keys": sorted(
                    (
                        tuple(foreign_key["constrained_columns"]),
                        foreign_key["referred_table"],
                        tuple(foreign_key["referred_columns"]),
                    )
                    for foreign_key in inspector.get_foreign_keys(table)
                ),
            }
            for table in table_names
        }
        with engine.connect() as connection:
            policies = (
                connection.execute(
                    text(
                        "SELECT tablename, policyname, qual, with_check "
                        "FROM pg_policies WHERE schemaname = current_schema() "
                        "ORDER BY tablename, policyname"
                    )
                )
                .tuples()
                .all()
            )
            rls_flags = (
                connection.execute(
                    text(
                        "SELECT relname, relrowsecurity, relforcerowsecurity "
                        "FROM pg_class "
                        "JOIN pg_namespace ON pg_namespace.oid = relnamespace "
                        "WHERE nspname = current_schema() AND relkind = 'r' "
                        "ORDER BY relname"
                    )
                )
                .tuples()
                .all()
            )
        return {"tables": tables, "policies": policies, "rls": rls_flags}
    finally:
        engine.dispose()
