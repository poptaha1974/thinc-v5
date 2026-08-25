from __future__ import annotations

import pytest

from thinc_v5.api.devserver import (
    InsecureTestIdentityDisabledError,
    create_dev_app,
)


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
