from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from thinc_v5.decision.service import (
    AssessmentInput,
    AssessmentResponse,
    AssessmentService,
)
from thinc_v5.domain.common import NonBlankStr
from thinc_v5.domain.decisions import HumanApproval


class TestIdentity(BaseModel):
    """Identity supplied by tests; this is not production authentication."""

    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    actor_id: NonBlankStr = Field(max_length=255)

    __test__ = False

    @field_validator("tenant_id", mode="before")
    @classmethod
    def require_bounded_nonblank_tenant_id(cls, value: object) -> object:
        if isinstance(value, str):
            if not value.strip():
                raise ValueError("tenant_id must not be blank")
            if len(value) > 36:
                raise ValueError("tenant_id must not exceed 36 characters")
        return value


class ApprovalInput(BaseModel):
    approved_at: datetime | None = None


class ProblemDetails(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str
    instance: str
    errors: list[dict[str, Any]] | None = None


IdentityProvider = Callable[..., object]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        pattern=r".*\S.*",
    ),
]


def problem_responses(*status_codes: int) -> dict[int | str, dict[str, Any]]:
    schema = ProblemDetails.model_json_schema()
    return {
        status_code: {
            "description": "RFC 9457 problem details",
            "content": {
                "application/problem+json": {
                    "schema": schema,
                }
            },
        }
        for status_code in status_codes
    }


class IdentityValidationError(Exception):
    def __init__(self, errors: list[Any]) -> None:
        super().__init__("test identity validation failed")
        self.errors = [dict(error) for error in errors]


def create_assessment_router(
    service: AssessmentService,
    identity_provider: IdentityProvider,
) -> APIRouter:
    router = APIRouter(prefix="/v1/assessments", tags=["assessments"])

    def identity_boundary(
        raw_identity: Annotated[object, Depends(identity_provider)],
    ) -> TestIdentity:
        try:
            return TestIdentity.model_validate(raw_identity)
        except ValidationError as error:
            raise IdentityValidationError(error.errors()) from error

    @router.post(
        "",
        response_model=AssessmentResponse,
        status_code=status.HTTP_201_CREATED,
        responses=problem_responses(400, 409, 422, 500),
    )
    def create_assessment(
        request: AssessmentInput,
        idempotency_key: IdempotencyKey,
        identity: Annotated[TestIdentity, Depends(identity_boundary)],
    ) -> AssessmentResponse:
        return service.create_assessment(
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            idempotency_key=idempotency_key,
            request=request,
        )

    @router.get(
        "/{assessment_id}",
        response_model=AssessmentResponse,
        responses=problem_responses(404, 422, 500),
    )
    def get_assessment(
        assessment_id: str,
        identity: Annotated[TestIdentity, Depends(identity_boundary)],
    ) -> AssessmentResponse:
        return service.get_assessment(identity.tenant_id, assessment_id)

    @router.post(
        "/{assessment_id}/approvals",
        response_model=HumanApproval,
        status_code=status.HTTP_201_CREATED,
        responses=problem_responses(400, 404, 409, 422, 500),
    )
    def approve_assessment(
        assessment_id: str,
        request: ApprovalInput,
        idempotency_key: IdempotencyKey,
        identity: Annotated[TestIdentity, Depends(identity_boundary)],
    ) -> HumanApproval:
        return service.approve_assessment(
            tenant_id=identity.tenant_id,
            assessment_id=assessment_id,
            approver_id=identity.actor_id,
            idempotency_key=idempotency_key,
            approved_at=request.approved_at,
        )

    return router
