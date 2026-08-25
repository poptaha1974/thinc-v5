from __future__ import annotations

import pytest

from thinc_v5.db.migration_config import configure_alembic_url

from .conftest import (
    _require_disposable_database,
    _require_ephemeral_role_test_cluster,
    alembic_config,
    safe_downgrade,
)


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


def test_test_database_name_alone_cannot_enable_role_mutations() -> None:
    with pytest.raises(RuntimeError, match="ephemeral GitHub Actions"):
        _require_ephemeral_role_test_cluster(
            "postgresql+psycopg://migrator@localhost/thinc_test",
            "postgresql+psycopg://postgres@localhost/thinc_test",
            {"THINC_TEST_DATABASE_DISPOSABLE": "1"},
        )


def test_destructive_role_token_alone_cannot_enable_role_mutations() -> None:
    with pytest.raises(RuntimeError, match="ephemeral GitHub Actions"):
        _require_ephemeral_role_test_cluster(
            "postgresql+psycopg://migrator@localhost/thinc_test",
            "postgresql+psycopg://postgres@localhost/thinc_test",
            {"THINC_DESTRUCTIVE_ROLE_TESTS": ("postgres16-github-actions-service-v1")},
        )


def test_all_ephemeral_ci_signals_enable_role_mutations() -> None:
    _require_ephemeral_role_test_cluster(
        "postgresql+psycopg://thinc_migrator@localhost/thinc_test",
        "postgresql+psycopg://postgres@localhost/thinc_test",
        {
            "GITHUB_ACTIONS": "true",
            "CI": "true",
            "THINC_DESTRUCTIVE_ROLE_TESTS": ("postgres16-github-actions-service-v1"),
            "THINC_TEST_DATABASE_DISPOSABLE": "1",
        },
    )
