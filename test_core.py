from models import WorldState, SKU, Supplier, Order
from engine import validate_action, place_supplier_order, advance_time, apply_strategy
from simulator import simulate_strategy
from scoring import evaluate_scenario
import random


def make_state(cash=4000, lead=2, reliability=1.0):
    return WorldState(
        cash=cash,
        inventory={"LAPTOP": SKU(qty=0, unit_cost=500, unit_price=1000)},
        suppliers={
            "FAST_SUPPLIER": Supplier(id="FAST_SUPPLIER", lead_time_days=lead, reliability=reliability),
            "SLOW_SUPPLIER": Supplier(id="SLOW_SUPPLIER", lead_time_days=6, reliability=0.8),
        },
        active_orders=[Order(id="VIP-001", sku="LAPTOP", qty=10, priority="high", created_tick=0, deadline_tick=4, penalty_per_day=500)],
    )


def test_unaffordable_order_rejected():
    ok, reason = validate_action(make_state(), "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"])
    assert not ok and "Unaffordable" in reason


def test_affordable_full_order_accepted():
    ok, _ = validate_action(make_state(cash=10000), "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"])
    assert ok


def test_partial_order_rejected():
    ok, reason = validate_action(make_state(cash=10000), "place_supplier_order", ["LAPTOP", 5, "FAST_SUPPLIER"])
    assert not ok and "partial fulfilment is not implemented" in reason


def test_bad_supplier_and_quantity_rejected():
    s = make_state(cash=10000)
    assert not validate_action(s, "place_supplier_order", ["LAPTOP", 10, "UNKNOWN"])[0]
    assert not validate_action(s, "place_supplier_order", ["LAPTOP", -1, "FAST_SUPPLIER"])[0]
    assert not validate_action(s, "place_supplier_order", ["LAPTOP", True, "FAST_SUPPLIER"])[0]


def test_over_ordering_is_rejected_when_future_demand_is_not_modelled():
    s = make_state(cash=10000)
    ok, reason = validate_action(s, "place_supplier_order", ["LAPTOP", 11, "FAST_SUPPLIER"])
    assert not ok and "exceeds current pending demand" in reason


def test_wait_requires_empty_args():
    assert validate_action(make_state(), None, [])[0]
    assert not validate_action(make_state(), None, ["extra"])[0]


def test_seed_reproducibility_and_state_isolation():
    s = make_state(cash=10000, reliability=0.7)
    before = s.model_dump()
    a = simulate_strategy(s, "Fast", "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"], num_runs=20)
    b = simulate_strategy(s, "Fast", "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"], num_runs=20)
    assert a == b
    assert s.model_dump() == before


def test_unaffordable_plan_marked_infeasible():
    result = simulate_strategy(make_state(), "Impossible", "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"], num_runs=5)
    assert result["feasible"] is False and result["runs"] == 0


def test_day_four_is_inclusive():
    s = make_state(cash=10000, lead=4, reliability=1.0)
    s = place_supplier_order(s, "LAPTOP", 10, "FAST_SUPPLIER")
    s = advance_time(s, ticks=4, seed=1)
    assert s.active_orders[0].status == "fulfilled"


def test_late_order_cancelled_and_penalized():
    s = make_state(cash=10000, lead=5, reliability=1.0)
    s = place_supplier_order(s, "LAPTOP", 10, "FAST_SUPPLIER")
    s = advance_time(s, ticks=6, seed=1)
    assert s.active_orders[0].status == "cancelled"
    assert s.metrics.sla_breaches == 1
    assert s.metrics.penalties_incurred == 500


def test_successful_sale_accounting():
    s = make_state(cash=10000, lead=2, reliability=1.0)
    s = place_supplier_order(s, "LAPTOP", 10, "FAST_SUPPLIER")
    s = advance_time(s, ticks=3, seed=1)
    m = evaluate_scenario(s)
    assert m["operating_profit"] == 5000
    assert m["final_cash"] == 15000
    assert m["sla_met"] is True


def test_customer_advance_strategy_can_fund_crisis_order():
    s = make_state(cash=4000, lead=2, reliability=1.0)
    ok, _ = validate_action(s, "request_customer_deposit_and_order", ["LAPTOP", 10, "FAST_SUPPLIER"])
    assert ok
    s = apply_strategy(s, "request_customer_deposit_and_order", ["LAPTOP", 10, "FAST_SUPPLIER"], random.Random(1))
    assert any("advance accepted" in line.lower() for line in s.action_log)
    assert s.cash == 1000
    s = advance_time(s, ticks=3, seed=1)
    m = evaluate_scenario(s)
    assert m["operating_profit"] == 5000
    assert m["final_cash"] == 9000


def test_customer_advance_decline_leaves_no_order():
    s = make_state(cash=4000)
    # Seed 2 produces a random draw greater than the configured 0.8 threshold.
    s = apply_strategy(s, "request_customer_deposit_and_order", ["LAPTOP", 10, "FAST_SUPPLIER"], random.Random(2))
    assert s.cash == 4000
    assert not s.incoming_shipments
    assert any("declined" in line.lower() for line in s.action_log)


def test_source_code_does_not_mutate_strategy_state():
    s = make_state(cash=10000)
    r = simulate_strategy(s, "Fast", "place_supplier_order", ["LAPTOP", 10, "FAST_SUPPLIER"], num_runs=5)
    assert r["runs"] == 5 and r["feasible"]
    assert s.cash == 10000 and s.inventory["LAPTOP"].qty == 0


def test_customer_advance_is_rejected_when_existing_cash_covers_procurement():
    s = make_state(cash=10000)
    ok, reason = validate_action(
        s, "request_customer_deposit_and_order", ["LAPTOP", 10, "FAST_SUPPLIER"]
    )
    assert not ok
    assert "only available when existing cash cannot fund" in reason
