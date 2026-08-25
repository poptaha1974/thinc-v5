from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

import thinc_v5.engines.economics as economics_module
from thinc_v5.domain.common import MissingnessStatus, Provenance
from thinc_v5.domain.economics import EconomicsInput
from thinc_v5.engines.economics import EconomicsEngine


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


def test_delivered_contribution_profit_uses_all_variable_costs() -> None:
    data = EconomicsInput(
        collected_revenue=Decimal("1000"),
        product_cost=Decimal("300"),
        ad_spend=Decimal("200"),
        shipping=Decimal("80"),
        collection_fees=Decimal("20"),
        return_cost=Decimal("40"),
        variable_operations_cost=Decimal("60"),
        delivered_orders=10,
    )

    result = EconomicsEngine().assess(data, build_provenance())

    assert result.missingness_status is MissingnessStatus.COMPLETE
    assert result.delivered_contribution_profit == Decimal("300")
    assert result.profit_per_delivered_order == Decimal("30")


def test_missing_money_fields_are_reported_without_coercing_to_zero() -> None:
    data = EconomicsInput(
        collected_revenue=None,
        product_cost=Decimal("300"),
        ad_spend=None,
        shipping=Decimal("80"),
        collection_fees=Decimal("20"),
        return_cost=Decimal("40"),
        variable_operations_cost=Decimal("60"),
        delivered_orders=10,
    )

    result = EconomicsEngine().assess(data, build_provenance())

    assert result.missingness_status is MissingnessStatus.NOT_COLLECTED
    assert result.delivered_contribution_profit is None
    assert result.profit_per_delivered_order is None
    assert len(result.decision_reasons) == 2
    assert any("collected_revenue" in reason for reason in result.decision_reasons)
    assert any("ad_spend" in reason for reason in result.decision_reasons)


def test_zero_delivered_orders_returns_no_per_order_profit_with_reason() -> None:
    data = EconomicsInput(
        collected_revenue=Decimal("1000"),
        product_cost=Decimal("300"),
        ad_spend=Decimal("200"),
        shipping=Decimal("80"),
        collection_fees=Decimal("20"),
        return_cost=Decimal("40"),
        variable_operations_cost=Decimal("60"),
        delivered_orders=0,
    )

    result = EconomicsEngine().assess(data, build_provenance())

    assert result.missingness_status is MissingnessStatus.COMPLETE
    assert result.delivered_contribution_profit == Decimal("300")
    assert result.profit_per_delivered_order is None
    assert any(
        "delivered_orders" in reason and "zero" in reason.lower()
        for reason in result.decision_reasons
    )


def test_negative_financial_inputs_are_rejected() -> None:
    with pytest.raises(ValidationError):
        EconomicsInput(
            collected_revenue=Decimal("-1"),
            product_cost=Decimal("300"),
            ad_spend=Decimal("200"),
            shipping=Decimal("80"),
            collection_fees=Decimal("20"),
            return_cost=Decimal("40"),
            variable_operations_cost=Decimal("60"),
            delivered_orders=10,
        )


def test_negative_delivered_orders_are_rejected() -> None:
    with pytest.raises(ValidationError):
        EconomicsInput(
            collected_revenue=Decimal("1000"),
            product_cost=Decimal("300"),
            ad_spend=Decimal("200"),
            shipping=Decimal("80"),
            collection_fees=Decimal("20"),
            return_cost=Decimal("40"),
            variable_operations_cost=Decimal("60"),
            delivered_orders=-1,
        )


def test_runtime_guard_raises_if_missing_values_reach_computation_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(economics_module, "MONEY_FIELDS", ())

    data = EconomicsInput(
        collected_revenue=None,
        product_cost=Decimal("300"),
        ad_spend=Decimal("200"),
        shipping=Decimal("80"),
        collection_fees=Decimal("20"),
        return_cost=Decimal("40"),
        variable_operations_cost=Decimal("60"),
        delivered_orders=10,
    )

    with pytest.raises(
        RuntimeError,
        match="economics computation received unexpected missing values",
    ):
        EconomicsEngine().assess(data, build_provenance())
