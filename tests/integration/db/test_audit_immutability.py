from __future__ import annotations

import io
import uuid

import pytest
from alembic.config import Config
from sqlalchemy import exc, text

from alembic import command
from thinc_v5.db.session import set_tenant_context

from .conftest import PROJECT_ROOT, MigratedDatabase


def test_offline_migration_enforces_append_only_audit_events() -> None:
    output = io.StringIO()
    config = Config(str(PROJECT_ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://offline")

    command.upgrade(config, "head", sql=True)

    sql = output.getvalue()
    assert "BEFORE UPDATE OR DELETE ON audit_events" in sql
    assert "ERRCODE = '42501'" in sql
    assert "CREATE FUNCTION public.reject_audit_event_mutation()" in sql
    assert "EXECUTE FUNCTION public.reject_audit_event_mutation()" in sql
    assert (
        "REVOKE ALL PRIVILEGES ON FUNCTION "
        "public.reject_audit_event_mutation() FROM PUBLIC, thinc_app"
    ) in sql
    assert "Required PostgreSQL role thinc_app is missing" in sql
    assert "thinc_app must have LOGIN" in sql
    assert "GRANT USAGE ON SCHEMA public TO thinc_app" in sql
    assert "GRANT SELECT, INSERT ON audit_events TO thinc_app" in sql
    assert "REVOKE UPDATE, DELETE ON audit_events FROM thinc_app" in sql
    assert (
        "GRANT SELECT, INSERT, UPDATE, DELETE ON assessment_records TO thinc_app" in sql
    )


def test_app_role_has_only_effective_runtime_privileges(
    migrated_database: MigratedDatabase,
) -> None:
    expected_privileges = {
        "tenants": (True, False, False, False, False, False, False),
        "evidence_records": (True, True, True, True, False, False, False),
        "assessment_records": (True, True, True, True, False, False, False),
        "decision_records": (True, True, True, True, False, False, False),
        "human_approval_records": (
            True,
            True,
            True,
            True,
            False,
            False,
            False,
        ),
        "audit_events": (True, True, False, False, False, False, False),
    }
    with migrated_database.app_engine.connect() as connection:
        role = connection.execute(
            text(
                "SELECT rolname, rolcanlogin, rolsuper, rolcreatedb, rolcreaterole, "
                "rolbypassrls FROM pg_roles WHERE rolname = current_user"
            )
        ).one()
        privileged_memberships = connection.execute(
            text(
                "SELECT inherited_role.rolname FROM pg_roles inherited_role "
                "WHERE inherited_role.rolname <> current_user "
                "AND pg_has_role(current_user, inherited_role.oid, 'MEMBER') "
                "AND (inherited_role.rolsuper OR inherited_role.rolcreatedb "
                "OR inherited_role.rolcreaterole OR inherited_role.rolbypassrls)"
            )
        ).all()
        database_create, schema_create = connection.execute(
            text(
                "SELECT has_database_privilege(current_user, current_database(), "
                "'CREATE'), has_schema_privilege(current_user, current_schema(), "
                "'CREATE')"
            )
        ).one()
        privileges = {
            table_name: tuple(
                connection.execute(
                    text(
                        "SELECT "
                        "has_table_privilege(current_user, :table, 'SELECT'), "
                        "has_table_privilege(current_user, :table, 'INSERT'), "
                        "has_table_privilege(current_user, :table, 'UPDATE'), "
                        "has_table_privilege(current_user, :table, 'DELETE'), "
                        "has_table_privilege(current_user, :table, 'TRUNCATE'), "
                        "has_table_privilege(current_user, :table, 'REFERENCES'), "
                        "has_table_privilege(current_user, :table, 'TRIGGER')"
                    ),
                    {"table": table_name},
                ).one()
            )
            for table_name in expected_privileges
        }
        app_owned_tables = connection.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = current_schema() "
                "AND tableowner = current_user"
            )
        ).all()
        audit_function_execute = connection.execute(
            text(
                "SELECT has_function_privilege(current_user, "
                "'public.reject_audit_event_mutation()', 'EXECUTE')"
            )
        ).scalar_one()

    assert tuple(role) == ("thinc_app", True, False, False, False, False)
    assert privileged_memberships == []
    assert (database_create, schema_create) == (False, False)
    assert privileges == expected_privileges
    assert app_owned_tables == []
    assert audit_function_execute is False


def test_migration_role_owns_schema_tables(
    migrated_database: MigratedDatabase,
) -> None:
    with migrated_database.migration_engine.connect() as connection:
        migration_role = connection.execute(text("SELECT current_user")).scalar_one()
        owners = (
            connection.execute(
                text(
                    "SELECT DISTINCT tableowner FROM pg_tables "
                    "WHERE schemaname = current_schema() "
                    "AND tablename <> 'alembic_version'"
                )
            )
            .scalars()
            .all()
        )

    assert owners == [migration_role]
    assert migration_role != "thinc_app"


def test_app_role_cannot_create_tables(
    migrated_database: MigratedDatabase,
) -> None:
    with pytest.raises(exc.DBAPIError) as error:
        with migrated_database.app_engine.begin() as connection:
            connection.execute(text("CREATE TABLE forbidden_ddl (id integer)"))

    assert getattr(error.value.orig, "sqlstate", None) == "42501"


@pytest.mark.parametrize("mutation", ["UPDATE", "DELETE"])
def test_app_role_cannot_mutate_audit_events(
    migrated_database: MigratedDatabase,
    mutation: str,
) -> None:
    tenant_id, event_id = _insert_audit_event(migrated_database)
    statement = (
        "UPDATE audit_events SET event_type = 'changed' WHERE id = :id"
        if mutation == "UPDATE"
        else "DELETE FROM audit_events WHERE id = :id"
    )

    with pytest.raises(exc.DBAPIError) as error:
        with migrated_database.app_engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            connection.execute(text(statement), {"id": event_id})

    assert getattr(error.value.orig, "sqlstate", None) == "42501"


@pytest.mark.parametrize("mutation", ["UPDATE", "DELETE"])
def test_owner_is_still_blocked_by_audit_trigger(
    migrated_database: MigratedDatabase,
    mutation: str,
) -> None:
    tenant_id, event_id = _insert_audit_event(migrated_database)
    statement = (
        "UPDATE audit_events SET event_type = 'changed' WHERE id = :id"
        if mutation == "UPDATE"
        else "DELETE FROM audit_events WHERE id = :id"
    )

    with pytest.raises(exc.DBAPIError) as error:
        with migrated_database.migration_engine.begin() as connection:
            set_tenant_context(connection, tenant_id)
            connection.execute(text(statement), {"id": event_id})

    assert getattr(error.value.orig, "sqlstate", None) == "42501"
    assert "audit events are append-only" in str(error.value.orig)


def _insert_audit_event(
    migrated_database: MigratedDatabase,
) -> tuple[uuid.UUID, uuid.UUID]:
    tenant_id = uuid.uuid4()
    event_id = uuid.uuid4()
    with migrated_database.migration_engine.begin() as connection:
        connection.execute(
            text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
            {"id": tenant_id, "slug": f"tenant-{tenant_id}", "name": "Tenant"},
        )
    with migrated_database.app_engine.begin() as connection:
        set_tenant_context(connection, tenant_id)
        connection.execute(
            text(
                "INSERT INTO audit_events "
                "(id, tenant_id, actor_id, event_type, entity_type, entity_id, "
                "payload, integrity_hash) VALUES "
                "(:id, :tenant_id, 'user-1', 'created', 'assessment', "
                "'assessment-1', CAST(:payload AS jsonb), :integrity_hash)"
            ),
            {
                "id": event_id,
                "tenant_id": tenant_id,
                "payload": '{"reason": "created"}',
                "integrity_hash": "sha256:audit-event",
            },
        )
    return tenant_id, event_id
