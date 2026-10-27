"""Regression tests for accounting, validation, deterministic statistics, and edge cases."""
import math
import random
from typing import Any, Iterable, cast

import pytest
from pydantic import ValidationError

from engine import advance_time, apply_strategy, place_supplier_order, process_shipments, validate_action
from models import IncomingShipment, Order, SKU, Supplier, WorldState
from scoring import evaluate_scenario
from simulator import _percentile, simulate_strategy


def state_factory(*, cash=10_000.0, lead=2, reliability=1.0, stock=0, deposit=2_000.0, acceptance=0.8):
    return WorldState(
        cash=cash,
        inventory={"LAPTOP": SKU(qty=stock, unit_cost=500.0, unit_price=1_000.0)},
        suppliers={
            "FAST_SUPPLIER": Supplier(
                id="FAST_SUPPLIER", lead_time_days=lead, reliability=reliability,
            ),
        },
        active_orders=[Order(
            id="VIP-001", sku="LAPTOP", qty=10, priority="high",
            created_tick=0, deadline_tick=4, penalty_per_day=500.0,
        )],
        customer_deposit_amount=deposit,
        customer_deposit_acceptance_probability=acceptance,
    )


def test_inbound_inventory_prevents_duplicate_purchase():
    state = state_factory()
    state = place_supplier_order(state, "LAPTOP", 10, "FAST_SUPPLIER")
    valid, reason = validate_action(state, "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"])
    assert not valid
    assert "uncovered pending demand" in reason
    assert len(state.incoming_shipments) == 1


def test_customer_advance_feasibility_uses_the_capped_amount_actually_received():
    state = state_factory(cash=-6_000, deposit=20_000)
    valid, reason = validate_action(
        state, "request_customer_deposit_and_order", ["LAPTOP", 10, "FAST_SUPPLIER"]
    )
    # Although the configured advance says $20k, the advance cannot exceed the $10k order value.
    assert not valid
    assert "available funding is $4000.00" in reason


def test_opening_stock_is_valued_and_inventory_assets_reconcile_after_sale():
    state = WorldState(
        cash=10_000,
        inventory={"SKU_1": SKU(qty=2, unit_cost=500, unit_price=1_000)},
        suppliers={"SUPP_A": Supplier(id="SUPP_A", lead_time_days=2, reliability=1.0)},
        active_orders=[Order(id="ORD-1", sku="SKU_1", qty=4, deadline_tick=4)],
    )
    assert state.inventory_asset_value == 1_000
    state = place_supplier_order(state, "SKU_1", 2, "SUPP_A")
    assert state.cash == 9_000
    assert state.inventory_asset_value == 2_000
    state = advance_time(state, ticks=2, seed=4)
    result = evaluate_scenario(state)
    assert result["final_cash"] == 13_000
    assert result["operating_profit"] == 2_000
    assert result["ending_inventory_asset_value"] == 0
    assert result["ending_inventory_units"]["SKU_1"] == 0
    assert result["cash_plus_inventory_assets"] == 13_000


def test_accepted_deposit_is_applied_once_and_cleared_from_order_balance():
    state = state_factory(cash=4_000, acceptance=1.0)
    state = apply_strategy(
        state, "request_customer_deposit_and_order", ["LAPTOP", 10, "FAST_SUPPLIER"], random.Random(1)
    )
    state = advance_time(state, ticks=3, seed=4)
    result = evaluate_scenario(state)
    assert result["customer_deposits_received"] == 2_000
    assert result["customer_deposits_applied"] == 2_000
    assert result["customer_deposits_refunded"] == 0
    assert result["outstanding_customer_deposits"] == 0
    assert state.active_orders[0].deposit_received == 0
    assert result["operating_profit"] == 5_000
    assert result["final_cash"] == 9_000


def test_late_arrival_cancels_order_refunds_advance_and_keeps_unsold_stock_as_asset():
    state = state_factory(cash=4_000, lead=5, reliability=1.0, acceptance=1.0)
    state = apply_strategy(
        state, "request_customer_deposit_and_order", ["LAPTOP", 10, "FAST_SUPPLIER"], random.Random(1)
    )
    state = advance_time(state, ticks=7, seed=4)
    result = evaluate_scenario(state)
    assert state.active_orders[0].status == "cancelled"
    assert result["customer_deposits_received"] == 2_000
    assert result["customer_deposits_applied"] == 0
    assert result["customer_deposits_refunded"] == 2_000
    assert result["outstanding_customer_deposits"] == 0
    assert result["penalties"] == 500
    assert result["operating_profit"] == -500
    assert result["final_cash"] == -1_500
    assert result["ending_inventory_asset_value"] == 5_000
    assert result["ending_inventory_units"]["LAPTOP"] == 10
    assert result["cash_plus_inventory_assets"] == 3_500


class FixedRng(random.Random):
    """Small deterministic RNG stub for exercising the permanent-loss branch."""
    def __init__(self, values: Iterable[float]) -> None:
        super().__init__(0)
        self._values = iter(values)

    def random(self) -> float:
        return next(self._values)

    def randint(self, a: int, b: int) -> int:
        # Keep returning your deterministic value (historically 'low', which is 'a')
        return a


def test_permanent_shipment_loss_writes_off_the_asset_exactly_once():
    state = state_factory(reliability=0.0)
    state = place_supplier_order(state, "LAPTOP", 10, "FAST_SUPPLIER")
    state.current_tick = 2
    state = process_shipments(state, FixedRng([0.99, 0.01]))
    result = evaluate_scenario(state)
    assert result["shipment_losses"] == 5_000
    assert result["ending_inventory_asset_value"] == 0
    assert result["cash_plus_inventory_assets"] == 5_000
    assert state.incoming_shipments == []
    assert sum("SHIPMENT LOSS" in line for line in state.action_log) == 1


def test_asset_basis_mismatch_and_nonfinite_money_are_rejected():
    with pytest.raises(ValidationError):
        SKU(qty=0, unit_cost=float("nan"), unit_price=100)
    with pytest.raises(ValidationError):
        WorldState(
            cash=1_000,
            inventory_asset_value=0,
            inventory={"LAPTOP": SKU(qty=2, unit_cost=500, unit_price=1_000)},
            suppliers={"S": Supplier(id="S", lead_time_days=2, reliability=1.0)},
            active_orders=[],
        )


def test_nearest_rank_percentile_has_explicit_small_sample_behavior():
    values = list(range(1, 21))
    assert _percentile(values, 0.00) == 1
    assert _percentile(values, 0.05) == 1
    assert _percentile(values, 0.50) == 10
    assert _percentile(values, 0.95) == 19
    assert _percentile(values, 1.00) == 20
    assert _percentile([], 0.05) == 0
    with pytest.raises(ValueError):
        _percentile(values, 1.1)


def test_monte_carlo_outputs_are_bounded_reproducible_and_include_horizon():
    state = state_factory()
    one = simulate_strategy(state, "Fast", "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"], num_runs=100)
    two = simulate_strategy(state, "Fast", "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"], num_runs=100)
    assert one == two
    assert one["runs"] == 100
    assert one["horizon_days"] == 7
    assert one["worst_case_cash"] <= one["p05_cash"]
    assert one["solvency_probability"] in range(0, 101)
    assert 0 <= one["sla_success_probability"] <= 100
    assert math.isfinite(one["expected_profit"])


def test_unhashable_action_is_rejected_instead_of_raising_type_error():
    state = state_factory()
    valid, reason = validate_action(state, cast(Any, {"malicious": "value"}), [])
    assert not valid
    assert reason == "Unsupported action."


def test_simulation_rejects_boolean_run_count_and_time_rejects_invalid_ticks():
    state = state_factory()
    with pytest.raises(ValueError):
        simulate_strategy(state, "Fast", "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"], num_runs=cast(Any, True))
    with pytest.raises(ValueError):
        advance_time(state, ticks=cast(Any, True))
    with pytest.raises(ValueError):
        advance_time(state, ticks=-1)


def test_sla_compliance_is_not_reported_as_100_percent_before_any_order_is_processed():
    state = state_factory()
    result = evaluate_scenario(state)
    assert state.metrics.sla_compliance_pct is None
    assert result["sla_compliance_pct"] is None
