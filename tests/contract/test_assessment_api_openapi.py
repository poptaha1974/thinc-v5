import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Header

from thinc_v5.api.app import create_app
from thinc_v5.api.routes.assessments import TestIdentity
from thinc_v5.decision.service import InMemoryAssessmentRepository


def injected_test_identity(
    x_tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
    x_test_identity: Annotated[str, Header(alias="X-Test-Identity")],
) -> TestIdentity:
    return TestIdentity(tenant_id=x_tenant_id, actor_id=x_test_identity)


def test_assessment_api_openapi_matches_committed_contract() -> None:
    contract_path = Path("docs/contracts/assessment-api-v1.json")
    app = create_app(
        repository=InMemoryAssessmentRepository(),
        identity_provider=injected_test_identity,
    )

    committed = json.loads(contract_path.read_text(encoding="utf-8"))

    assert app.openapi() == committed
