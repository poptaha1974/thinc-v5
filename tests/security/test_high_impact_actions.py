from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Header
from fastapi.testclient import TestClient

from tests.integration.api.test_assessments import (
    TENANT_A_HEADERS,
    TENANT_B_HEADERS,
    complete_assessment_payload,
)
from thinc_v5.api.app import create_app
from thinc_v5.api.routes.assessments import TestIdentity
from thinc_v5.decision.service import InMemoryAssessmentRepository


def injected_test_identity(
    x_tenant_id: Annotated[UUID, Header(alias="X-Tenant-ID")],
    x_test_identity: Annotated[str, Header(alias="X-Test-Identity")],
) -> TestIdentity:
    return TestIdentity(tenant_id=x_tenant_id, actor_id=x_test_identity)


def build_client() -> TestClient:
    return TestClient(
        create_app(
            repository=InMemoryAssessmentRepository(),
            identity_provider=injected_test_identity,
        )
    )


def test_openapi_has_no_high_impact_action_paths() -> None:
    paths = build_client().app.openapi()["paths"]

    forbidden_terms = ("publish", "budget", "execute", "scale", "launch", "ads")

    assert paths
    assert all(
        forbidden not in path.lower()
        for path in paths
        for forbidden in forbidden_terms
    )


def test_approval_is_bound_to_tenant_and_does_not_mutate_engine_output() -> None:
    client = build_client()
    created = client.post(
        "/v1/assessments",
        headers={**TENANT_A_HEADERS, "Idempotency-Key": "approval-create"},
        json=complete_assessment_payload(),
    ).json()
    assessment_id = created["assessment_id"]
    economics_before = created["data"]["economics"]

    cross_tenant = client.post(
        f"/v1/assessments/{assessment_id}/approvals",
        headers={**TENANT_B_HEADERS, "Idempotency-Key": "approval-other"},
        json={"approved_at": "2026-08-25T10:00:00Z"},
    )
    approved = client.post(
        f"/v1/assessments/{assessment_id}/approvals",
        headers={**TENANT_A_HEADERS, "Idempotency-Key": "approval-owner"},
        json={"approved_at": "2026-08-25T10:00:00Z"},
    )
    fetched = client.get(
        f"/v1/assessments/{assessment_id}",
        headers=TENANT_A_HEADERS,
    )

    assert cross_tenant.status_code == 404
    assert approved.status_code == 201
    assert approved.json() == {
        "approver_id": "researcher-1",
        "approved_at": "2026-08-25T10:00:00Z",
        "assessment_id": assessment_id,
    }
    assert fetched.json()["data"]["economics"] == economics_before


def test_approval_post_requires_idempotency_key() -> None:
    client = build_client()
    created = client.post(
        "/v1/assessments",
        headers={**TENANT_A_HEADERS, "Idempotency-Key": "approval-key-create"},
        json=complete_assessment_payload(),
    ).json()

    response = client.post(
        f"/v1/assessments/{created['assessment_id']}/approvals",
        headers=TENANT_A_HEADERS,
        json={},
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_posts_reject_blank_idempotency_keys() -> None:
    response = build_client().post(
        "/v1/assessments",
        headers={**TENANT_A_HEADERS, "Idempotency-Key": "   "},
        json=complete_assessment_payload(),
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_approval_idempotency_key_cannot_be_replayed_by_another_identity() -> None:
    client = build_client()
    created = client.post(
        "/v1/assessments",
        headers={**TENANT_A_HEADERS, "Idempotency-Key": "identity-create"},
        json=complete_assessment_payload(),
    ).json()
    path = f"/v1/assessments/{created['assessment_id']}/approvals"
    approval_headers = {**TENANT_A_HEADERS, "Idempotency-Key": "identity-approval"}

    first = client.post(path, headers=approval_headers, json={})
    replay = client.post(
        path,
        headers={
            **approval_headers,
            "X-Test-Identity": "different-approver",
        },
        json={},
    )

    assert first.status_code == 201
    assert replay.status_code == 409
    assert replay.headers["content-type"].startswith("application/problem+json")
