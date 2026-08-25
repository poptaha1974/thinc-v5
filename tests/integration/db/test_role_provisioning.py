from __future__ import annotations

import uuid

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, exc, text
from sqlalchemy.engine import make_url

from alembic import command

from .conftest import alembic_config, safe_downgrade


def test_migration_rejects_missing_app_role(
    database_url: str,
    provisioner_url: str,
) -> None:
    renamed_role = f"thinc_app_missing_{uuid.uuid4().hex[:8]}"
    config = _base_config(database_url)
    provisioner = create_engine(provisioner_url)
    role_was_renamed = False
    try:
        _execute(provisioner, f"ALTER ROLE thinc_app RENAME TO {renamed_role}")
        role_was_renamed = True
        _assert_upgrade_rejected(
            config,
            "Required PostgreSQL role thinc_app is missing",
        )
    finally:
        if role_was_renamed:
            _execute(provisioner, f"ALTER ROLE {renamed_role} RENAME TO thinc_app")
        provisioner.dispose()
        _cleanup(config)


@pytest.mark.parametrize(
    ("unsafe_change", "safe_change"),
    [
        ("ALTER ROLE thinc_app SUPERUSER", "ALTER ROLE thinc_app NOSUPERUSER"),
        ("ALTER ROLE thinc_app BYPASSRLS", "ALTER ROLE thinc_app NOBYPASSRLS"),
    ],
    ids=["superuser", "bypassrls"],
)
def test_migration_rejects_privileged_app_role_attributes(
    database_url: str,
    provisioner_url: str,
    unsafe_change: str,
    safe_change: str,
) -> None:
    config = _base_config(database_url)
    provisioner = create_engine(provisioner_url)
    try:
        _execute(provisioner, unsafe_change)
        _assert_upgrade_rejected(
            config,
            "thinc_app has forbidden privileged role attributes",
        )
    finally:
        _execute(provisioner, safe_change)
        provisioner.dispose()
        _cleanup(config)


def test_migration_rejects_membership_in_migration_owner_role(
    database_url: str,
    provisioner_url: str,
) -> None:
    config = _base_config(database_url)
    provisioner = create_engine(provisioner_url)
    try:
        _execute(provisioner, "GRANT thinc_migrator TO thinc_app")
        _assert_upgrade_rejected(
            config,
            "thinc_app must not inherit the migration owner role",
        )
    finally:
        _execute(provisioner, "REVOKE thinc_migrator FROM thinc_app")
        provisioner.dispose()
        _cleanup(config)


@pytest.mark.parametrize(
    "grant_scope",
    ["database", "schema"],
    ids=["database_create", "schema_create"],
)
def test_migration_rejects_effective_app_role_create_privilege(
    database_url: str,
    provisioner_url: str,
    grant_scope: str,
) -> None:
    config = _base_config(database_url)
    provisioner = create_engine(provisioner_url)
    database_name = make_url(database_url).database
    assert database_name is not None
    quoted_database = provisioner.dialect.identifier_preparer.quote(database_name)
    target = (
        f"DATABASE {quoted_database}" if grant_scope == "database" else "SCHEMA public"
    )
    try:
        _execute(provisioner, f"GRANT CREATE ON {target} TO thinc_app")
        _assert_upgrade_rejected(
            config,
            "thinc_app must not have effective DDL privileges",
        )
    finally:
        _execute(provisioner, f"REVOKE CREATE ON {target} FROM thinc_app")
        provisioner.dispose()
        _cleanup(config)


def _base_config(database_url: str) -> Config:
    config = alembic_config(database_url)
    safe_downgrade(config)
    return config


def _assert_upgrade_rejected(config: Config, message: str) -> None:
    with pytest.raises(exc.DBAPIError, match=message):
        command.upgrade(config, "head")


def _execute(engine: Engine, statement: str) -> None:
    with engine.begin() as connection:
        connection.execute(text(statement))


def _cleanup(config: Config) -> None:
    safe_downgrade(config)
