"""Additional, deterministic engine smoke tests; run with pytest -q."""
from models import WorldState, SKU, Supplier, Order
from engine import place_supplier_order, advance_time
from scoring import evaluate_scenario


def test_engine_smoke():
    state = WorldState(
        cash=10000,
        inventory={"SKU_1": SKU(qty=0, unit_cost=100, unit_price=300)},
        suppliers={"SUPP_A": Supplier(id="SUPP_A", lead_time_days=2, reliability=1.0)},
        active_orders=[Order(id="ORD1", sku="SKU_1", qty=10, priority="high", created_tick=0, deadline_tick=3, penalty_per_day=500)],
    )
    state = place_supplier_order(state, "SKU_1", 10, "SUPP_A")
    state = advance_time(state, ticks=3, seed=10)
    metrics = evaluate_scenario(state)
    assert metrics["final_cash"] == 12000
    assert metrics["operating_profit"] == 2000
    assert metrics["is_solvent"] is True
