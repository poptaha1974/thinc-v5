from datetime import UTC, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from thinc_v5.domain.common import Provenance
from thinc_v5.domain.economics import EconomicsInput
from thinc_v5.engines.economics import EconomicsEngine

MONEY = st.decimals(min_value=0, max_value=1_000_000, places=2)


def build_provenance() -> Provenance:
    return Provenance(
        schema_version="1.0.0",
        model_version="economics-engine.1",
        engine_commit="abc1234",
        generated_at=datetime.now(UTC),
        evidence_as_of=datetime.now(UTC),
        market="EG",
        source_ids=["source-1"],
    )


def build_input(
    *,
    collected_revenue: Decimal,
    product_cost: Decimal,
    ad_spend: Decimal,
    shipping: Decimal,
    collection_fees: Decimal,
    return_cost: Decimal,
    variable_operations_cost: Decimal,
    delivered_orders: int,
) -> EconomicsInput:
    return EconomicsInput(
        collected_revenue=collected_revenue,
        product_cost=product_cost,
        ad_spend=ad_spend,
        shipping=shipping,
        collection_fees=collection_fees,
        return_cost=return_cost,
        variable_operations_cost=variable_operations_cost,
        delivered_orders=delivered_orders,
    )


@settings(max_examples=100)
@given(
    collected_revenue=MONEY,
    product_cost=MONEY,
    ad_spend=MONEY,
    shipping=MONEY,
    collection_fees=MONEY,
    return_cost=MONEY,
    variable_operations_cost=MONEY,
    delivered_orders=st.integers(min_value=1, max_value=10_000),
    delta=MONEY.filter(lambda value: value > 0),
)
def test_increasing_one_cost_never_increases_profit(
    collected_revenue: Decimal,
    product_cost: Decimal,
    ad_spend: Decimal,
    shipping: Decimal,
    collection_fees: Decimal,
    return_cost: Decimal,
    variable_operations_cost: Decimal,
    delivered_orders: int,
    delta: Decimal,
) -> None:
    baseline = build_input(
        collected_revenue=collected_revenue,
        product_cost=product_cost,
        ad_spend=ad_spend,
        shipping=shipping,
        collection_fees=collection_fees,
        return_cost=return_cost,
        variable_operations_cost=variable_operations_cost,
        delivered_orders=delivered_orders,
    )
    increased_cost = build_input(
        collected_revenue=collected_revenue,
        product_cost=product_cost + delta,
        ad_spend=ad_spend,
        shipping=shipping,
        collection_fees=collection_fees,
        return_cost=return_cost,
        variable_operations_cost=variable_operations_cost,
        delivered_orders=delivered_orders,
    )

    engine = EconomicsEngine()
    baseline_profit = engine.assess(
        baseline,
        provenance=build_provenance(),
    ).delivered_contribution_profit
    increased_profit = engine.assess(
        increased_cost,
        provenance=build_provenance(),
    ).delivered_contribution_profit

    assert baseline_profit is not None
    assert increased_profit is not None
    assert increased_profit <= baseline_profit


@settings(max_examples=100)
@given(
    collected_revenue=MONEY,
    product_cost=MONEY,
    ad_spend=MONEY,
    shipping=MONEY,
    collection_fees=MONEY,
    return_cost=MONEY,
    variable_operations_cost=MONEY,
    delivered_orders=st.integers(min_value=1, max_value=10_000),
)
def test_profit_equals_revenue_minus_exact_variable_costs(
    collected_revenue: Decimal,
    product_cost: Decimal,
    ad_spend: Decimal,
    shipping: Decimal,
    collection_fees: Decimal,
    return_cost: Decimal,
    variable_operations_cost: Decimal,
    delivered_orders: int,
) -> None:
    data = build_input(
        collected_revenue=collected_revenue,
        product_cost=product_cost,
        ad_spend=ad_spend,
        shipping=shipping,
        collection_fees=collection_fees,
        return_cost=return_cost,
        variable_operations_cost=variable_operations_cost,
        delivered_orders=delivered_orders,
    )

    result = EconomicsEngine().assess(data, provenance=build_provenance())

    assert result.delivered_contribution_profit == (
        collected_revenue
        - product_cost
        - ad_spend
        - shipping
        - collection_fees
        - return_cost
        - variable_operations_cost
    )


@settings(max_examples=100)
@given(
    collected_revenue=MONEY,
    product_cost=MONEY,
    ad_spend=MONEY,
    shipping=MONEY,
    collection_fees=MONEY,
    return_cost=MONEY,
    variable_operations_cost=MONEY,
    delivered_orders=st.integers(min_value=0, max_value=10_000),
)
def test_serialization_round_trip_preserves_decimal_values(
    collected_revenue: Decimal,
    product_cost: Decimal,
    ad_spend: Decimal,
    shipping: Decimal,
    collection_fees: Decimal,
    return_cost: Decimal,
    variable_operations_cost: Decimal,
    delivered_orders: int,
) -> None:
    original = build_input(
        collected_revenue=collected_revenue,
        product_cost=product_cost,
        ad_spend=ad_spend,
        shipping=shipping,
        collection_fees=collection_fees,
        return_cost=return_cost,
        variable_operations_cost=variable_operations_cost,
        delivered_orders=delivered_orders,
    )

    round_tripped = EconomicsInput.model_validate_json(original.model_dump_json())

    assert round_tripped == original
