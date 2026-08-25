from __future__ import annotations

import io
import uuid

import pytest
from alembic.config import Config
from sqlalchemy import Connection, exc, text

from alembic import command

from .conftest import PROJECT_ROOT


def test_offline_migration_enforces_append_only_audit_events() -> None:
    output = io.StringIO()
    config = Config(str(PROJECT_ROOT / "alembic.ini"), output_buffer=output)
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://offline")

    command.upgrade(config, "head", sql=True)

    sql = output.getvalue()
    assert "BEFORE UPDATE OR DELETE ON audit_events" in sql
    assert "ERRCODE = '42501'" in sql
    assert "REVOKE UPDATE, DELETE ON audit_events FROM PUBLIC" in sql
    assert "REVOKE UPDATE, DELETE ON audit_events FROM thinc_app" in sql


@pytest.mark.parametrize("mutation", ["UPDATE", "DELETE"])
def test_audit_events_reject_mutation(
    migrated_connection: Connection,
    mutation: str,
) -> None:
    tenant_id = uuid.uuid4()
    event_id = uuid.uuid4()
    migrated_connection.execute(
        text("INSERT INTO tenants (id, slug, name) VALUES (:id, :slug, :name)"),
        {"id": tenant_id, "slug": f"tenant-{tenant_id}", "name": "Tenant"},
    )
    migrated_connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, false)"),
        {"tenant_id": str(tenant_id)},
    )
    migrated_connection.execute(
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

    statement = (
        "UPDATE audit_events SET event_type = 'changed' WHERE id = :id"
        if mutation == "UPDATE"
        else "DELETE FROM audit_events WHERE id = :id"
    )
    with pytest.raises(exc.DBAPIError) as error:
        migrated_connection.execute(text(statement), {"id": event_id})

    assert getattr(error.value.orig, "sqlstate", None) == "42501"
