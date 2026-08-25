from __future__ import annotations

import pytest

from thinc_v5.db.migration_config import configure_alembic_url

from .conftest import (
    _require_disposable_database,
    _require_ephemeral_role_test_cluster,
    alembic_config,
    safe_downgrade,
)

EPHEMERAL_CI_SIGNALS = {
    "GITHUB_ACTIONS": "true",
    "CI": "true",
    "THINC_DESTRUCTIVE_ROLE_TESTS": "postgres16-github-actions-service-v1",
    "THINC_TEST_DATABASE_DISPOSABLE": "1",
}
WORKFLOW_DATABASE_URLS = (
    "postgresql+psycopg://thinc_migrator:migration@localhost:5432/thinc_test",
    "postgresql+psycopg://thinc_app:application@localhost:5432/thinc_test",
    "postgresql+psycopg://postgres:postgres@localhost:5432/thinc_test",
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


@pytest.mark.parametrize("missing_signal", tuple(EPHEMERAL_CI_SIGNALS))
def test_each_ephemeral_ci_signal_is_required_for_role_mutations(
    missing_signal: str,
) -> None:
    incomplete_signals = {
        key: value
        for key, value in EPHEMERAL_CI_SIGNALS.items()
        if key != missing_signal
    }

    with pytest.raises(RuntimeError, match="ephemeral GitHub Actions"):
        _require_ephemeral_role_test_cluster(
            *WORKFLOW_DATABASE_URLS,
            incomplete_signals,
        )


@pytest.mark.parametrize(
    "database_urls",
    [
        WORKFLOW_DATABASE_URLS,
        (
            "postgresql+psycopg://thinc_migrator@localhost:5432/thinc_test",
            "postgresql+psycopg://thinc_app@localhost:5432/thinc_test",
            "postgresql+psycopg://postgres@localhost:5432/thinc_test",
        ),
    ],
    ids=["workflow-passwords", "external-password-source"],
)
def test_canonical_ephemeral_ci_urls_enable_role_mutations(
    database_urls: tuple[str, str, str],
) -> None:
    _require_ephemeral_role_test_cluster(
        *database_urls,
        EPHEMERAL_CI_SIGNALS,
    )


@pytest.mark.parametrize(
    "url_index",
    range(3),
    ids=["migration", "app", "provisioner"],
)
def test_destructive_role_guard_rejects_query_destination_override(
    url_index: int,
) -> None:
    database_urls = list(WORKFLOW_DATABASE_URLS)
    database_urls[url_index] += (
        "?host=shared.example&port=6432&dbname=production&user=postgres"
    )
    migration_url, app_url, provisioner_url = database_urls

    with pytest.raises(RuntimeError, match="canonical query-free"):
        _require_ephemeral_role_test_cluster(
            migration_url,
            app_url,
            provisioner_url,
            EPHEMERAL_CI_SIGNALS,
        )


@pytest.mark.parametrize(
    ("url_index", "unsafe_url"),
    [
        (
            0,
            "postgresql://thinc_migrator:migration@localhost:5432/thinc_test",
        ),
        (
            0,
            "postgresql+psycopg://thinc_migrator:migration@localhost/thinc_test",
        ),
        (
            0,
            "postgresql+psycopg://thinc_migrator:migration@127.0.0.1:5432/thinc_test",
        ),
        (
            0,
            "postgresql+psycopg://thinc%5Fmigrator:migration@localhost:5432/thinc_test",
        ),
        (
            0,
            "postgresql+psycopg://thinc_migrator:migration@localhost:5432/another_test",
        ),
        (
            1,
            "postgresql+psycopg://thinc_migrator:application@localhost:5432/thinc_test",
        ),
        (
            2,
            "postgresql+psycopg://postgres:postgres@shared.example:5432/thinc_test",
        ),
        (
            2,
            "postgresql+psycopg://postgres:postgres@localhost:5432/thinc_test"
            "?sslmode=disable",
        ),
    ],
    ids=[
        "driver-alias",
        "implicit-port",
        "loopback-alias",
        "encoded-identity",
        "alternate-test-database",
        "wrong-app-identity",
        "non-loopback-host",
        "query-parameter",
    ],
)
def test_destructive_role_guard_rejects_non_allowlisted_url_shapes(
    url_index: int,
    unsafe_url: str,
) -> None:
    database_urls = list(WORKFLOW_DATABASE_URLS)
    database_urls[url_index] = unsafe_url
    migration_url, app_url, provisioner_url = database_urls

    with pytest.raises(RuntimeError, match="canonical query-free"):
        _require_ephemeral_role_test_cluster(
            migration_url,
            app_url,
            provisioner_url,
            EPHEMERAL_CI_SIGNALS,
        )
