import json
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Header

from thinc_v5.api.app import create_app
from thinc_v5.decision.service import InMemoryAssessmentRepository


def injected_test_identity(
    x_tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
    x_test_identity: Annotated[str, Header(alias="X-Test-Identity")],
) -> dict[str, object]:
    return {"tenant_id": x_tenant_id, "actor_id": x_test_identity}


def test_assessment_api_openapi_matches_committed_contract() -> None:
    contract_path = Path("docs/contracts/assessment-api-v1.json")
    app = create_app(
        repository=InMemoryAssessmentRepository(),
        identity_provider=injected_test_identity,
    )

    committed = json.loads(contract_path.read_text(encoding="utf-8"))

    assert app.openapi() == committed


def test_openapi_declares_rfc_9457_problem_responses() -> None:
    app = create_app(
        repository=InMemoryAssessmentRepository(),
        identity_provider=injected_test_identity,
    )
    paths = app.openapi()["paths"]
    expected_statuses = {
        ("/v1/assessments", "post"): {"400", "409", "422", "500"},
        ("/v1/assessments/{assessment_id}", "get"): {"404", "422", "500"},
        ("/v1/assessments/{assessment_id}/approvals", "post"): {
            "400",
            "404",
            "409",
            "422",
            "500",
        },
    }

    for (path, method), statuses in expected_statuses.items():
        responses = paths[path][method]["responses"]
        for status in statuses:
            assert set(responses[status]["content"]) == {"application/problem+json"}
            schema = responses[status]["content"]["application/problem+json"]["schema"]
            assert schema["title"] == "ProblemDetails"

    assert "HTTPValidationError" not in app.openapi().get("components", {}).get(
        "schemas", {}
    )
