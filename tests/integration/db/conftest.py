from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic.config import Config
from sqlalchemy import Connection, create_engine

from alembic import command

PROJECT_ROOT = Path(__file__).parents[3]


def alembic_config(database_url: str) -> Config:
    config = Config(str(PROJECT_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(PROJECT_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.getenv("THINC_TEST_DATABASE_URL")
    if not url:
        pytest.skip("THINC_TEST_DATABASE_URL is required for PostgreSQL integration")
    if not url.startswith(("postgresql://", "postgresql+psycopg://")):
        pytest.fail("THINC_TEST_DATABASE_URL must point to PostgreSQL")
    return url


@pytest.fixture
def migrated_connection(database_url: str) -> Iterator[Connection]:
    config = alembic_config(database_url)
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            yield connection
            connection.rollback()
    finally:
        engine.dispose()
        command.downgrade(config, "base")
