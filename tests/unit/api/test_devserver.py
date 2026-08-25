from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError

from thinc_v5.api.devserver import (
    HeaderTestIdentityProvider,
    InsecureTestIdentityDisabledError,
    create_dev_app,
)
from thinc_v5.api.routes.assessments import TestIdentity


def test_create_dev_app_fails_closed_without_explicit_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("THINC_ENABLE_INSECURE_TEST_IDENTITY", raising=False)

    with pytest.raises(InsecureTestIdentityDisabledError):
        create_dev_app()


def test_create_dev_app_fails_closed_for_non_true_env_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("THINC_ENABLE_INSECURE_TEST_IDENTITY", "false")

    with pytest.raises(InsecureTestIdentityDisabledError):
        create_dev_app()


def test_create_dev_app_uses_header_test_identity_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("THINC_ENABLE_INSECURE_TEST_IDENTITY", "true")

    app = create_dev_app()
    openapi = app.openapi()

    assert app.title == "THINC v5 Research Preview API"
    assert "/v1/assessments" in openapi["paths"]
    assert "/v1/assessments/{assessment_id}/approvals" in openapi["paths"]


def test_header_test_identity_provider_returns_expected_mapping() -> None:
    identity = HeaderTestIdentityProvider(
        UUID("11111111-1111-4111-8111-111111111111"),
        "researcher-1",
    )

    assert identity == {
        "tenant_id": UUID("11111111-1111-4111-8111-111111111111"),
        "actor_id": "researcher-1",
    }


def test_test_identity_accepts_a_bounded_nonblank_tenant_id_string() -> None:
    identity = TestIdentity.model_validate(
        {
            "tenant_id": "11111111-1111-4111-8111-111111111111",
            "actor_id": "researcher-1",
        }
    )

    assert identity.tenant_id == UUID("11111111-1111-4111-8111-111111111111")


@pytest.mark.parametrize(
    ("tenant_id", "message"),
    [
        ("   ", "tenant_id must not be blank"),
        ("1" * 37, "tenant_id must not exceed 36 characters"),
    ],
)
def test_test_identity_rejects_blank_and_overlong_tenant_ids(
    tenant_id: str,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        TestIdentity.model_validate(
            {
                "tenant_id": tenant_id,
                "actor_id": "researcher-1",
            }
        )
