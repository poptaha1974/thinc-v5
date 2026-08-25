from __future__ import annotations

import uuid

import pytest

from thinc_v5.db.session import set_tenant_context


class NoTransactionConnection:
    def in_transaction(self) -> bool:
        return False

    def execute(self, statement: object, parameters: object | None = None) -> None:
        del statement, parameters
        raise AssertionError("execute must not be reached without a transaction")


def test_set_tenant_context_requires_an_active_transaction() -> None:
    with pytest.raises(
        RuntimeError, match="tenant context requires an active transaction"
    ):
        set_tenant_context(
            NoTransactionConnection(),  # type: ignore[arg-type]
            uuid.UUID("11111111-1111-4111-8111-111111111111"),
        )
