from __future__ import annotations

from decimal import Decimal
from typing import cast

from thinc_v5.domain.common import MissingnessStatus, Provenance, Uncertainty
from thinc_v5.domain.economics import (
    MONEY_FIELDS,
    EconomicsAssessment,
    EconomicsInput,
)
from thinc_v5.domain.engines import Engine


class EconomicsEngine(Engine[EconomicsInput, EconomicsAssessment]):
    def assess(
        self,
        input: EconomicsInput,
        provenance: Provenance,
    ) -> EconomicsAssessment:
        missing_fields = [
            field_name
            for field_name in MONEY_FIELDS
            if getattr(input, field_name) is None
        ]
        if missing_fields:
            return EconomicsAssessment(
                delivered_contribution_profit=None,
                profit_per_delivered_order=None,
                decision_reasons=[
                    (
                        f"{field_name} was not collected; delivered "
                        "contribution profit cannot be computed."
                    )
                    for field_name in missing_fields
                ],
                missingness_status=MissingnessStatus.NOT_COLLECTED,
                uncertainty=Uncertainty(
                    method="not_computable",
                    notes=["One or more required money fields were not collected."],
                ),
                provenance=provenance,
            )

        collected_revenue = input.collected_revenue
        product_cost = input.product_cost
        ad_spend = input.ad_spend
        shipping = input.shipping
        collection_fees = input.collection_fees
        return_cost = input.return_cost
        variable_operations_cost = input.variable_operations_cost

        if any(
            value is None
            for value in (
                collected_revenue,
                product_cost,
                ad_spend,
                shipping,
                collection_fees,
                return_cost,
                variable_operations_cost,
            )
        ):
            raise RuntimeError(
                "economics computation received unexpected missing values"
            )

        collected_revenue = cast(Decimal, collected_revenue)
        product_cost = cast(Decimal, product_cost)
        ad_spend = cast(Decimal, ad_spend)
        shipping = cast(Decimal, shipping)
        collection_fees = cast(Decimal, collection_fees)
        return_cost = cast(Decimal, return_cost)
        variable_operations_cost = cast(Decimal, variable_operations_cost)

        delivered_contribution_profit = (
            collected_revenue
            - product_cost
            - ad_spend
            - shipping
            - collection_fees
            - return_cost
            - variable_operations_cost
        )

        decision_reasons = [
            (
                "Calculated delivered contribution profit from collected "
                "revenue and variable costs."
            )
        ]
        profit_per_delivered_order: Decimal | None
        if input.delivered_orders == 0:
            profit_per_delivered_order = None
            decision_reasons.append(
                "delivered_orders is zero; profit_per_delivered_order "
                "cannot be computed."
            )
        else:
            profit_per_delivered_order = delivered_contribution_profit / Decimal(
                input.delivered_orders
            )

        return EconomicsAssessment(
            delivered_contribution_profit=delivered_contribution_profit,
            profit_per_delivered_order=profit_per_delivered_order,
            decision_reasons=decision_reasons,
            missingness_status=MissingnessStatus.COMPLETE,
            uncertainty=Uncertainty(method="deterministic"),
            provenance=provenance,
        )
