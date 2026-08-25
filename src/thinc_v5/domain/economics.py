from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, Field, field_validator

from thinc_v5.domain.common import (
    MissingnessStatus,
    NonBlankStr,
    Provenance,
    Uncertainty,
)

MONEY_FIELDS = (
    "collected_revenue",
    "product_cost",
    "ad_spend",
    "shipping",
    "collection_fees",
    "return_cost",
    "variable_operations_cost",
)


class EconomicsInput(BaseModel):
    collected_revenue: Decimal | None = None
    product_cost: Decimal | None = None
    ad_spend: Decimal | None = None
    shipping: Decimal | None = None
    collection_fees: Decimal | None = None
    return_cost: Decimal | None = None
    variable_operations_cost: Decimal | None = None
    delivered_orders: int = Field(ge=0)

    @field_validator(*MONEY_FIELDS)
    @classmethod
    def require_non_negative_money(
        cls,
        value: Decimal | None,
    ) -> Decimal | None:
        if value is not None and value < 0:
            raise ValueError("money inputs must be greater than or equal to zero")
        return value


class EconomicsAssessment(BaseModel):
    delivered_contribution_profit: Decimal | None
    profit_per_delivered_order: Decimal | None
    decision_reasons: list[NonBlankStr] = Field(min_length=1)
    missingness_status: MissingnessStatus
    uncertainty: Uncertainty
    provenance: Provenance
