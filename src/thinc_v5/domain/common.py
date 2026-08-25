from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"


class MissingnessStatus(str, Enum):
    NOT_COLLECTED = "NOT_COLLECTED"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"


class DataQualityStatus(str, Enum):
    POOR = "POOR"
    ACCEPTABLE = "ACCEPTABLE"
    GOOD = "GOOD"


class ReviewStatus(str, Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class Uncertainty(BaseModel):
    method: str
    lower: Decimal | None = None
    upper: Decimal | None = None
    notes: list[str] = Field(default_factory=list)

    @field_validator("method")
    @classmethod
    def require_method(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("method must not be empty")
        return value

    @field_validator("notes")
    @classmethod
    def require_nonempty_notes(cls, value: list[str]) -> list[str]:
        if any(not note.strip() for note in value):
            raise ValueError("notes must not contain empty entries")
        return value

    @model_validator(mode="after")
    def validate_bounds(self) -> Uncertainty:
        if (
            self.lower is not None
            and self.upper is not None
            and self.lower > self.upper
        ):
            raise ValueError("lower must be less than or equal to upper")
        return self


class Provenance(BaseModel):
    schema_version: str = Field(pattern=SEMVER_PATTERN)
    model_version: str
    engine_commit: str
    generated_at: datetime
    evidence_as_of: datetime
    market: Literal["EG"]
    source_ids: list[str]

    @field_validator("schema_version", "model_version", "engine_commit")
    @classmethod
    def require_nonempty_strings(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("generated_at", "evidence_as_of")
    @classmethod
    def require_timezone_aware_datetimes(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value

    @field_validator("source_ids")
    @classmethod
    def require_source_ids(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("source_ids must not be empty")
        if any(not source_id.strip() for source_id in value):
            raise ValueError("source_ids must not contain empty entries")
        return value


class ResearchPreviewResult[PayloadT](BaseModel):
    data: PayloadT
    missingness_status: MissingnessStatus
    data_quality_status: DataQualityStatus
    review_status: ReviewStatus
    uncertainty: Uncertainty
    provenance: Provenance
