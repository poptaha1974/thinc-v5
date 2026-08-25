from __future__ import annotations

import pytest

from thinc_v5.db.migration_config import configure_alembic_url

from .conftest import _require_disposable_database, alembic_config, safe_downgrade


def test_destructive_migrations_require_explicit_disposable_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("THINC_TEST_DATABASE_DISPOSABLE", raising=False)

    with pytest.raises(pytest.fail.Exception, match="Refusing destructive"):
        _require_disposable_database("postgresql+psycopg://db/thinc_test")


def test_destructive_migrations_reject_non_test_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("THINC_TEST_DATABASE_DISPOSABLE", "1")

    with pytest.raises(pytest.fail.Exception, match="outside a test database"):
        _require_disposable_database("postgresql+psycopg://db/thinc")


def test_disposable_guard_checks_explicit_url_even_when_environment_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("THINC_TEST_DATABASE_DISPOSABLE", "1")
    config = alembic_config("postgresql+psycopg://db/thinc")

    effective_url = configure_alembic_url(
        config,
        {
            "THINC_MIGRATION_DATABASE_URL": "postgresql+psycopg://db/thinc_test",
            "THINC_TEST_DATABASE_URL": "postgresql+psycopg://db/other_test",
        },
    )

    with pytest.raises(pytest.fail.Exception, match="outside a test database"):
        _require_disposable_database(effective_url)


def test_safe_downgrade_refuses_non_disposable_effective_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("THINC_TEST_DATABASE_DISPOSABLE", "1")
    config = alembic_config("postgresql+psycopg://db/production")

    with pytest.raises(pytest.fail.Exception, match="outside a test database"):
        safe_downgrade(config)
