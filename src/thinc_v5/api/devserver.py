from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, Header

from thinc_v5.api.app import create_app
from thinc_v5.decision.service import InMemoryAssessmentRepository


class InsecureTestIdentityDisabledError(RuntimeError):
    pass


def HeaderTestIdentityProvider(
    x_tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
    x_test_identity: Annotated[str, Header(alias="X-Test-Identity")],
) -> dict[str, object]:
    return {"tenant_id": x_tenant_id, "actor_id": x_test_identity}


def create_dev_app() -> FastAPI:
    if os.getenv("THINC_ENABLE_INSECURE_TEST_IDENTITY") != "true":
        raise InsecureTestIdentityDisabledError(
            "Refusing to start dev/test API without "
            "THINC_ENABLE_INSECURE_TEST_IDENTITY=true. "
            "This startup path is non-production and synthetic-only."
        )

    return create_app(
        repository=InMemoryAssessmentRepository(),
        identity_provider=HeaderTestIdentityProvider,
    )
