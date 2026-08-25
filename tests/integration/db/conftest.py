from __future__ import annotations

import os
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url

from alembic import command
from thinc_v5.db.migration_config import configure_alembic_url

PROJECT_ROOT = Path(__file__).parents[3]


@dataclass(frozen=True)
class MigratedDatabase:
    migration_engine: Engine
    app_engine: Engine


def alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    config.attributes["thinc_explicit_database_url"] = True
    return config


def safe_downgrade(config: Config, revision: str = "base") -> None:
    effective_url = configure_alembic_url(config)
    _require_disposable_database(effective_url)
    command.downgrade(config, revision)


@pytest.fixture(scope="session")
def database_urls() -> tuple[str, str]:
    migration_url = os.getenv("THINC_TEST_DATABASE_URL")
    app_url = os.getenv("THINC_TEST_APP_DATABASE_URL")
    if not migration_url or not app_url:
        pytest.skip(
            "THINC_TEST_DATABASE_URL and THINC_TEST_APP_DATABASE_URL are "
            "required for PostgreSQL integration"
        )
    for variable, url in (
        ("THINC_TEST_DATABASE_URL", migration_url),
        ("THINC_TEST_APP_DATABASE_URL", app_url),
    ):
        if not make_url(url).drivername.startswith("postgresql"):
            pytest.fail(f"{variable} must point to PostgreSQL")
    if make_url(migration_url).database != make_url(app_url).database:
        pytest.fail("migration and app URLs must point to the same database")
    return migration_url, app_url


@pytest.fixture
def database_url(database_urls: tuple[str, str]) -> str:
    return database_urls[0]


@pytest.fixture(scope="session")
def provisioner_url(database_urls: tuple[str, str]) -> str:
    url = os.getenv("THINC_TEST_PROVISIONER_DATABASE_URL")
    if not url:
        pytest.skip(
            "THINC_TEST_PROVISIONER_DATABASE_URL is required for role rejection tests"
        )
    if not make_url(url).drivername.startswith("postgresql"):
        pytest.fail("THINC_TEST_PROVISIONER_DATABASE_URL must point to PostgreSQL")
    if make_url(url).database != make_url(database_urls[0]).database:
        pytest.fail("provisioner and migration URLs must point to the same database")
    return url


@pytest.fixture
def migrated_database(
    database_urls: tuple[str, str],
) -> Iterator[MigratedDatabase]:
    migration_url, app_url = database_urls
    config = alembic_config(migration_url)
    effective_migration_url = configure_alembic_url(config)
    _require_disposable_database(effective_migration_url)
    migration_engine = create_engine(effective_migration_url)
    app_engine = create_engine(app_url, pool_size=1, max_overflow=0)
    try:
        _verify_connection_roles(migration_engine, app_engine)
        safe_downgrade(config)
        command.upgrade(config, "head")
        yield MigratedDatabase(migration_engine, app_engine)
    finally:
        app_engine.dispose()
        migration_engine.dispose()
        safe_downgrade(config)


def _require_disposable_database(database_url: str) -> None:
    if os.getenv("THINC_TEST_DATABASE_DISPOSABLE") != "1":
        pytest.fail(
            "Refusing destructive migration test without "
            "THINC_TEST_DATABASE_DISPOSABLE=1"
        )
    database_name = make_url(database_url).database
    if not database_name or "test" not in database_name.lower():
        pytest.fail("Refusing destructive migration test outside a test database")


def _verify_connection_roles(
    migration_engine: Engine,
    app_engine: Engine,
) -> None:
    with migration_engine.connect() as migration_connection:
        migration_identity = migration_connection.execute(
            text("SELECT current_database(), current_user")
        ).one()
    with app_engine.connect() as app_connection:
        app_identity = app_connection.execute(
            text("SELECT current_database(), current_user")
        ).one()
    if migration_identity[0] != app_identity[0]:
        pytest.fail("migration and app connections resolved to different databases")
    if migration_identity[1] == app_identity[1]:
        pytest.fail("migration and app URLs must authenticate as distinct roles")
    if app_identity[1] != "thinc_app":
        pytest.fail("THINC_TEST_APP_DATABASE_URL must authenticate as thinc_app")
