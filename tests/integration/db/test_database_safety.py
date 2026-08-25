from __future__ import annotations

import pytest

from .conftest import _require_disposable_database


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
