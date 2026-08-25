from collections.abc import Callable
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, status
from pydantic import BaseModel, ConfigDict

from thinc_v5.decision.service import (
    AssessmentInput,
    AssessmentResponse,
    AssessmentService,
)
from thinc_v5.domain.decisions import HumanApproval


class TestIdentity(BaseModel):
    """Identity supplied by tests; this is not production authentication."""

    model_config = ConfigDict(frozen=True)

    tenant_id: UUID
    actor_id: str

    __test__ = False


class ApprovalInput(BaseModel):
    approved_at: datetime | None = None


IdentityProvider = Callable[..., TestIdentity]
IdempotencyKey = Annotated[
    str,
    Header(
        alias="Idempotency-Key",
        min_length=1,
        max_length=255,
        pattern=r".*\S.*",
    ),
]


def create_assessment_router(
    service: AssessmentService,
    identity_provider: IdentityProvider,
) -> APIRouter:
    router = APIRouter(prefix="/v1/assessments", tags=["assessments"])

    @router.post(
        "",
        response_model=AssessmentResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_assessment(
        request: AssessmentInput,
        idempotency_key: IdempotencyKey,
        identity: Annotated[TestIdentity, Depends(identity_provider)],
    ) -> AssessmentResponse:
        return service.create_assessment(
            tenant_id=identity.tenant_id,
            actor_id=identity.actor_id,
            idempotency_key=idempotency_key,
            request=request,
        )

    @router.get("/{assessment_id}", response_model=AssessmentResponse)
    def get_assessment(
        assessment_id: str,
        identity: Annotated[TestIdentity, Depends(identity_provider)],
    ) -> AssessmentResponse:
        return service.get_assessment(identity.tenant_id, assessment_id)

    @router.post(
        "/{assessment_id}/approvals",
        response_model=HumanApproval,
        status_code=status.HTTP_201_CREATED,
    )
    def approve_assessment(
        assessment_id: str,
        request: ApprovalInput,
        idempotency_key: IdempotencyKey,
        identity: Annotated[TestIdentity, Depends(identity_provider)],
    ) -> HumanApproval:
        return service.approve_assessment(
            tenant_id=identity.tenant_id,
            assessment_id=assessment_id,
            approver_id=identity.actor_id,
            idempotency_key=idempotency_key,
            approved_at=request.approved_at,
        )

    return router
