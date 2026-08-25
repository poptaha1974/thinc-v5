from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from thinc_v5.api.routes.assessments import (
    IdentityProvider,
    create_assessment_router,
)
from thinc_v5.decision.service import (
    AssessmentNotFound,
    AssessmentRepository,
    AssessmentService,
    IdempotencyConflict,
)


def create_app(
    *,
    repository: AssessmentRepository,
    identity_provider: IdentityProvider,
) -> FastAPI:
    """Build the Foundation API with explicitly injected test identity only.

    Production authentication is out of scope, so this application factory is
    deliberately not deployment-ready and has no default identity provider.
    """
    app = FastAPI(
        title="THINC v5 Research Preview API",
        version="1.0.0",
        description=(
            "Foundation-only Research Preview API. Production authentication "
            "is not implemented; deployment is unsafe."
        ),
    )
    app.include_router(
        create_assessment_router(
            AssessmentService(repository),
            identity_provider,
        )
    )

    @app.exception_handler(RequestValidationError)
    async def validation_problem(
        request: Request,
        error: RequestValidationError,
    ) -> JSONResponse:
        return _problem(
            request=request,
            status_code=422,
            title="Request validation failed",
            detail="The request did not satisfy the API contract.",
            errors=jsonable_encoder(error.errors()),
        )

    @app.exception_handler(AssessmentNotFound)
    async def not_found_problem(
        request: Request,
        error: AssessmentNotFound,
    ) -> JSONResponse:
        return _problem(
            request=request,
            status_code=404,
            title="Assessment not found",
            detail=f"Assessment {error.assessment_id!r} was not found.",
        )

    @app.exception_handler(IdempotencyConflict)
    async def idempotency_problem(
        request: Request,
        error: IdempotencyConflict,
    ) -> JSONResponse:
        del error
        return _problem(
            request=request,
            status_code=409,
            title="Idempotency conflict",
            detail="The idempotency key was already used for another request.",
        )

    return app


def _problem(
    *,
    request: Request,
    status_code: int,
    title: str,
    detail: str,
    errors: list[dict[str, object]] | None = None,
) -> JSONResponse:
    content: dict[str, object] = {
        "type": "about:blank",
        "title": title,
        "status": status_code,
        "detail": detail,
        "instance": str(request.url.path),
    }
    if errors is not None:
        content["errors"] = errors
    return JSONResponse(
        status_code=status_code,
        content=content,
        media_type="application/problem+json",
    )
