from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Literal

from pydantic import BaseModel, field_validator

from thinc_v5.domain.common import NonBlankStr
from thinc_v5.domain.economics import EconomicsAssessment


class Decision(str, Enum):
    RESEARCH = "RESEARCH"
    TEST = "TEST"
    FIX = "FIX"
    HOLD = "HOLD"
    REPOSITION = "REPOSITION"
    SCALE = "SCALE"
    KILL = "KILL"


class GateName(str, Enum):
    COMPLIANCE = "COMPLIANCE"
    LIQUIDITY = "LIQUIDITY"
    DELIVERED_PROFIT = "DELIVERED_PROFIT"
    DATA_QUALITY = "DATA_QUALITY"
    SAMPLE_SIZE = "SAMPLE_SIZE"
    OPERATIONAL_RECENCY = "OPERATIONAL_RECENCY"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"


class HumanApproval(BaseModel):
    approver_id: NonBlankStr
    approved_at: datetime
    assessment_id: NonBlankStr

    @field_validator("approved_at")
    @classmethod
    def require_timezone_aware_datetime(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("datetime must be timezone-aware")
        return value


class GateContext(BaseModel):
    requested_decision: Decision
    assessment_id: NonBlankStr
    economics_assessment: EconomicsAssessment
    compliance_passed: bool
    liquidity_passed: bool
    data_quality_passed: bool
    sample_size_passed: bool
    operational_recency_passed: bool
    stop_loss_registered: bool = False
    human_approval: HumanApproval | None = None


class GateResult(BaseModel):
    name: GateName
    passed: bool
    blocks_decision: bool
    override_allowed: Literal[False] = False
    reason: NonBlankStr
