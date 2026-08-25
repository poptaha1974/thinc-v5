from __future__ import annotations

import uuid

from sqlalchemy import Connection, text


def set_tenant_context(connection: Connection, tenant_id: uuid.UUID) -> None:
    """Scope PostgreSQL tenant isolation to the active transaction."""
    if not connection.in_transaction():
        raise RuntimeError("tenant context requires an active transaction")
    connection.execute(
        text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
        {"tenant_id": str(tenant_id)},
    )
