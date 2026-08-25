from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import text

from thinc_v5.db.session import set_tenant_context


def test_tenant_context_resets_when_transaction_returns_to_pool(
    migrated_database: Any,
) -> None:
    tenant_id = uuid.uuid4()

    with migrated_database.app_engine.begin() as connection:
        set_tenant_context(connection, tenant_id)
        active_tenant = connection.execute(
            text("SELECT current_setting('app.tenant_id', true)")
        ).scalar_one()

    with migrated_database.app_engine.begin() as connection:
        reset_tenant = connection.execute(
            text("SELECT current_setting('app.tenant_id', true)")
        ).scalar_one_or_none()

    assert active_tenant == str(tenant_id)
    assert reset_tenant in (None, "")
