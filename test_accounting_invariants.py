"""Seeded integration properties for cash, inventory assets, liabilities, and profit."""
import random

import pytest

from api import create_base_state
from engine import advance_time, apply_strategy
from scoring import evaluate_scenario


@pytest.mark.parametrize(
    "disruption, action, args",
    [
        (False, None, []),
        (False, "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"]),
        (False, "place_supplier_order", ["LAPTOP", 10, "SLOW_SUPPLIER"]),
        (True, None, []),
        (True, "request_customer_deposit_and_order", ["LAPTOP", 10, "FAST_SUPPLIER"]),
        (True, "request_customer_deposit_and_order", ["LAPTOP", 10, "SLOW_SUPPLIER"]),
    ],
)
def test_balance_sheet_change_reconciles_to_operating_profit(disruption, action, args):
    """Assets minus outstanding customer advances must change by recognized profit."""
    initial = create_base_state(scenario_delay_days=7, disruption=disruption)
    initial_net_assets = round(
        initial.cash
        + initial.inventory_asset_value
        - sum(order.deposit_received for order in initial.active_orders),
        2,
    )

    # Cover acceptance/decline and several shipment/delay/loss paths without network calls.
    for seed in range(20):
        state = initial.model_copy(deep=True)
        state = apply_strategy(state, action, args, random.Random(seed))
        state = advance_time(state, ticks=7, seed=seed + 10_000)
        result = evaluate_scenario(state)
        final_net_assets = round(
            result["final_cash"]
            + result["ending_inventory_asset_value"]
            - result["outstanding_customer_deposits"],
            2,
        )
        assert round(final_net_assets - initial_net_assets, 2) == result["operating_profit"]
        assert result["net_assets_after_customer_advances"] == final_net_assets
        # Pydantic's state invariant also ensures this basis corresponds to stock + inbound goods.
        expected_inventory_basis = round(
            sum(item.qty * item.unit_cost for item in state.inventory.values())
            + sum(
                shipment.qty * shipment.unit_cost
                for shipment in state.incoming_shipments
                if shipment.status in ("in_transit", "delayed")
            ),
            2,
        )
        assert state.inventory_asset_value == pytest.approx(expected_inventory_basis, abs=0.02)


def test_supplier_fee_is_expensed_and_balance_sheet_reconciles():
    from models import SKU, Supplier, Order, WorldState

    state = WorldState(
        cash=10000,
        inventory={"FAN": SKU(qty=0, unit_cost=100, unit_price=300)},
        suppliers={"EXPRESS": Supplier(id="EXPRESS", lead_time_days=1, reliability=1.0, per_unit_fee=20)},
        active_orders=[Order(id="FAN-1", sku="FAN", qty=10, priority="high", deadline_tick=2, penalty_per_day=100)],
    )
    initial_net_assets = state.cash + state.inventory_asset_value
    state = apply_strategy(state, "place_supplier_order", ["FAN", 10, "EXPRESS"], random.Random(7))
    assert state.cash == 8800
    assert state.inventory_asset_value == 1000  # Supplier fee is not capitalized into inventory.
    state = advance_time(state, ticks=2, seed=8)
    result = evaluate_scenario(state)
    assert result["supplier_fees_incurred"] == 200
    assert result["operating_profit"] == 1800
    final_net_assets = result["final_cash"] + result["ending_inventory_asset_value"] - result["outstanding_customer_deposits"]
    assert round(final_net_assets - initial_net_assets, 2) == result["operating_profit"]
