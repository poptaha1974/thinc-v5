"""PostgreSQL persistence models for THINC v5."""

from thinc_v5.db.base import Base, metadata
from thinc_v5.db.session import set_tenant_context

__all__ = ["Base", "metadata", "set_tenant_context"]
