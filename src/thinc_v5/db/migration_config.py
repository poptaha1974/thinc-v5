from __future__ import annotations

import os
from collections.abc import Mapping

from alembic.config import Config


def configure_alembic_url(
    config: Config,
    environ: Mapping[str, str] = os.environ,
) -> str:
    """Resolve one effective Alembic URL without overriding explicit config."""
    if config.attributes.get("thinc_explicit_database_url") is True:
        return _require_configured_url(config)

    migration_url = environ.get("THINC_MIGRATION_DATABASE_URL")
    test_url = environ.get("THINC_TEST_DATABASE_URL")
    if migration_url and test_url and migration_url != test_url:
        raise RuntimeError(
            "Conflicting Alembic database URLs: set only one of "
            "THINC_MIGRATION_DATABASE_URL and THINC_TEST_DATABASE_URL"
        )

    effective_url = migration_url or test_url
    if effective_url:
        config.set_main_option(
            "sqlalchemy.url",
            effective_url.replace("%", "%%"),
        )
    return _require_configured_url(config)


def _require_configured_url(config: Config) -> str:
    configured_url = config.get_main_option("sqlalchemy.url")
    if not configured_url:
        raise RuntimeError("Alembic sqlalchemy.url is required")
    return configured_url
