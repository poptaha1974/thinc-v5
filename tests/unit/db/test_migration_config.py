from __future__ import annotations

import pytest
from alembic.config import Config

from thinc_v5.db.migration_config import configure_alembic_url


def test_explicit_alembic_url_is_not_replaced_by_environment() -> None:
    explicit_url = "postgresql+psycopg://migrator/db_test"
    config = Config()
    config.set_main_option("sqlalchemy.url", explicit_url)
    config.attributes["thinc_explicit_database_url"] = True

    effective_url = configure_alembic_url(
        config,
        {
            "THINC_MIGRATION_DATABASE_URL": "postgresql+psycopg://migrator/prod",
            "THINC_TEST_DATABASE_URL": "postgresql+psycopg://migrator/other_test",
        },
    )

    assert effective_url == explicit_url
    assert config.get_main_option("sqlalchemy.url") == explicit_url


def test_conflicting_environment_urls_are_rejected() -> None:
    config = Config()
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://ini/default")

    with pytest.raises(RuntimeError, match="Conflicting Alembic database URLs"):
        configure_alembic_url(
            config,
            {
                "THINC_MIGRATION_DATABASE_URL": "postgresql+psycopg://migrator/prod",
                "THINC_TEST_DATABASE_URL": "postgresql+psycopg://migrator/db_test",
            },
        )


def test_matching_environment_urls_resolve_to_one_source() -> None:
    shared_url = "postgresql+psycopg://migrator/db_test"
    config = Config()
    config.set_main_option("sqlalchemy.url", "postgresql+psycopg://ini/default")

    effective_url = configure_alembic_url(
        config,
        {
            "THINC_MIGRATION_DATABASE_URL": shared_url,
            "THINC_TEST_DATABASE_URL": shared_url,
        },
    )

    assert effective_url == shared_url


def test_missing_alembic_url_is_rejected() -> None:
    with pytest.raises(RuntimeError, match="Alembic sqlalchemy.url is required"):
        configure_alembic_url(Config(), {})
