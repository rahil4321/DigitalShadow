"""Reproducible quantitative checks for the documented hackathon demo scenario."""
from api import create_base_state
from simulator import find_minimum_advance_acceptance, simulate_strategy


def test_baseline_fast_supplier_headline_metrics_reconcile():
    state = create_base_state(scenario_delay_days=14, disruption=False)
    result = simulate_strategy(
        state, "Place Order · Fast Supplier", "place_supplier_order",
        ["LAPTOP", 10, "FAST_SUPPLIER"], num_runs=1000,
    )
    assert result["expected_profit"] == 4979.00
    assert result["cash"] == 14979.00
    assert result["cash"] == state.cash + result["expected_profit"]
    assert result["sla_success_runs"] == 998
    assert result["sla_success_probability"] == 99.8
    assert result["sla_success_ci95"]["lower"] == 99.2737
    assert result["p05_cash"] == 15000.00
    assert result["worst_case_cash"] == 4500.00


def test_budget_crisis_advance_fast_metrics_reconcile_with_declines_and_rare_loss():
    state = create_base_state(scenario_delay_days=14, disruption=True)
    result = simulate_strategy(
        state, "Customer Advance · Fast Supplier", "request_customer_deposit_and_order",
        ["LAPTOP", 10, "FAST_SUPPLIER"], num_runs=1000,
    )
    assert result["expected_profit"] == 3801.50
    assert result["cash"] == 7801.50
    assert result["cash"] == state.cash + result["expected_profit"]
    assert result["sla_success_runs"] == 783
    assert result["sla_success_probability"] == 78.3
    assert result["sla_success_ci95"]["lower"] == 75.6395
    assert result["solvent_runs"] == 999
    assert result["solvency_probability"] == 99.9
    assert result["p05_cash"] == 3500.00
    assert result["worst_case_cash"] == -1500.00


def test_budget_crisis_standard_supplier_negative_cash_is_liquidity_not_profit_loss():
    state = create_base_state(scenario_delay_days=14, disruption=True)
    result = simulate_strategy(
        state, "Customer Advance · Standard Supplier", "request_customer_deposit_and_order",
        ["LAPTOP", 10, "SLOW_SUPPLIER"], num_runs=1000,
    )
    # The order is cancelled and the advance refunded, while the purchased goods remain an inventory asset in transit.
    assert result["expected_profit"] == -500.00
    assert result["cash"] == -420.00
    assert result["solvency_probability"] == 21.6
    assert result["expected_inventory_asset_value"] == 3920.00
    assert result["expected_net_assets_after_advances"] == 3500.00
    assert result["expected_outstanding_customer_deposits"] == 0.00
    assert result["cash"] + result["expected_inventory_asset_value"] - result["expected_outstanding_customer_deposits"] == result["expected_net_assets_after_advances"]
    assert result["expected_net_assets_after_advances"] == 4000.00 + result["expected_profit"] - 0.00
    assert result["p05_cash"] == -1500.00
    assert result["worst_case_cash"] == -1500.00


def test_tipping_point_is_precise_and_clears_the_statistical_guardrail():
    result = find_minimum_advance_acceptance(
        create_base_state(scenario_delay_days=14, disruption=True), num_runs=1000,
    )
    assert result["minimum_probability"] == 0.752
    assert result["margin_percentage_points"] == 4.8
    assert result["threshold_sla_success_probability"] == 73.0
    assert result["threshold_sla_success_ci95"]["lower"] >= 70.0
    assert result["passes_guardrails_at_threshold"] is True
