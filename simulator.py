"""Seeded Monte Carlo evaluator for candidate decisions."""
import math
import random
import statistics
from typing import Optional, Sequence
from models import WorldState
from engine import advance_time, apply_strategy, validate_action
from scoring import evaluate_scenario


SIMULATION_SEED = 20261011
SIMULATION_HORIZON_DAYS = 7
WILSON_Z_95 = 1.959963984540054


def wilson_interval(successes: int, total: int, z: float = WILSON_Z_95) -> dict | None:
    """Return a 95%-style Wilson score interval as percentages (not a guarantee)."""
    if isinstance(total, bool) or not isinstance(total, int) or total <= 0:
        return None
    if isinstance(successes, bool) or not isinstance(successes, int) or not 0 <= successes <= total:
        raise ValueError("successes must be an integer between 0 and total")
    p = successes / total
    z2 = z * z
    denominator = 1 + z2 / total
    center = p + z2 / (2 * total)
    margin = z * math.sqrt((p * (1 - p) / total) + (z2 / (4 * total * total)))
    lower = max(0.0, (center - margin) / denominator)
    upper = min(1.0, (center + margin) / denominator)
    return {"lower": round(100 * lower, 4), "upper": round(100 * upper, 4)}


def _percentile(values: Sequence[float], percentile: float) -> float:
    """Nearest-rank percentile: rank = ceil(p * n), with p in [0, 1]."""
    if not 0 <= percentile <= 1:
        raise ValueError("percentile must be between 0 and 1")
    if not values:
        return 0.0
    ordered = sorted(values)
    if percentile == 0:
        index = 0
    else:
        index = math.ceil(percentile * len(ordered)) - 1
    return round(ordered[index], 2)


def simulate_strategy(
    initial_state: WorldState,
    strategy_name: str,
    action_name: Optional[str],
    action_args: list,
    num_runs: int = 1000,
    horizon_days: int = SIMULATION_HORIZON_DAYS,
) -> dict:
    if isinstance(horizon_days, bool) or not isinstance(horizon_days, int) or not 1 <= horizon_days <= 60:
        raise ValueError("horizon_days must be an integer between 1 and 60")
    if isinstance(num_runs, bool) or not isinstance(num_runs, int) or not 1 <= num_runs <= 5000:
        raise ValueError("num_runs must be an integer between 1 and 5000")
    valid, reason = validate_action(initial_state, action_name, action_args)
    if not valid:
        return {
            "name": strategy_name, "feasible": False, "rejection_reason": reason,
            "expected_profit": None, "cash": None, "sla": 0.0, "score": None,
            "worst_case_cash": None, "p05_cash": None,
            "expected_inventory_asset_value": None, "expected_net_assets_after_advances": None,
            "expected_outstanding_customer_deposits": None,
            "solvency_probability": 0.0,
            "sla_success_probability": 0.0, "sla_success_ci95": None,
            "solvency_ci95": None, "runs": 0,
        }

    profits: list[float] = []
    cashes: list[float] = []
    inventory_assets: list[float] = []
    net_assets_after_advances: list[float] = []
    outstanding_deposits: list[float] = []
    slas: list[float] = []
    solvencies: list[bool] = []
    sla_successes: list[bool] = []
    # Same reproducible scenario-seed schedule for every strategy; action randomness is separate.
    seed_generator = random.Random(SIMULATION_SEED)
    run_seeds = [seed_generator.getrandbits(32) for _ in range(num_runs)]
    for run_seed in run_seeds:
        state = initial_state.model_copy(deep=True)
        action_rng = random.Random(run_seed ^ 0x5A17C9E3)
        state = apply_strategy(state, action_name, action_args, action_rng)
        state = advance_time(state, ticks=horizon_days, seed=run_seed)
        outcome = evaluate_scenario(state)
        profits.append(outcome["operating_profit"])
        cashes.append(outcome["final_cash"])
        inventory_assets.append(outcome["ending_inventory_asset_value"])
        net_assets_after_advances.append(outcome["net_assets_after_customer_advances"])
        outstanding_deposits.append(outcome["outstanding_customer_deposits"])
        if outcome["sla_compliance_pct"] is not None:
            slas.append(outcome["sla_compliance_pct"])
        solvencies.append(outcome["is_solvent"])
        sla_successes.append(outcome["sla_met"])

    expected_profit = statistics.fmean(profits)
    solvent_runs = sum(solvencies)
    sla_success_runs = sum(sla_successes)
    return {
        "name": strategy_name,
        "feasible": True,
        "expected_profit": round(expected_profit, 2),
        "cash": round(statistics.fmean(cashes), 2),
        "sla": round(statistics.fmean(slas), 1) if slas else None,
        # Kept as a compatibility alias; the recommendation policy explicitly uses expected_profit.
        "score": round(expected_profit, 2),
        "worst_case_cash": round(min(cashes), 2),
        "p05_cash": _percentile(cashes, 0.05),
        # Liquidity and net assets are distinct when purchased stock is still in transit.
        "expected_inventory_asset_value": round(statistics.fmean(inventory_assets), 2),
        "expected_net_assets_after_advances": round(statistics.fmean(net_assets_after_advances), 2),
        "expected_outstanding_customer_deposits": round(statistics.fmean(outstanding_deposits), 2),
        "solvency_probability": round(100 * solvent_runs / num_runs, 1),
        "solvency_ci95": wilson_interval(solvent_runs, num_runs),
        "sla_success_probability": round(100 * sla_success_runs / num_runs, 1),
        "sla_success_ci95": wilson_interval(sla_success_runs, num_runs),
        # Counts preserve exact guardrail decisions despite display rounding.
        "solvent_runs": solvent_runs,
        "sla_success_runs": sla_success_runs,
        "runs": num_runs,
        "horizon_days": horizon_days,
    }


def find_minimum_advance_acceptance(
    initial_state: WorldState,
    num_runs: int = 1000,
    sla_guardrail_pct: float = 70.0,
    cash_guardrail_pct: float = 95.0,
    iterations: int = 12,
) -> dict:
    """Find a model-conditioned acceptance threshold for the fast-supplier recovery option.

    The search is deterministic because `simulate_strategy` uses a fixed seed schedule.
    This is a scenario tipping point, not an estimate of actual customer behavior.
    """
    action = "request_customer_deposit_and_order"
    args = ["LAPTOP", _required_order_qty(initial_state, "LAPTOP"), "FAST_SUPPLIER"]

    def evaluate(probability: float) -> dict:
        state = initial_state.model_copy(deep=True)
        state.customer_deposit_acceptance_probability = probability
        return simulate_strategy(state, "Advance + FAST_SUPPLIER", action, args, num_runs=num_runs)

    def passes(result: dict) -> bool:
        sla_ci = result.get("sla_success_ci95") or {}
        cash_ci = result.get("solvency_ci95") or {}
        return (
            float(sla_ci.get("lower", 0.0)) >= sla_guardrail_pct
            and float(cash_ci.get("lower", 0.0)) >= cash_guardrail_pct
        )

    max_case = evaluate(1.0)
    if not max_case.get("feasible") or not passes(max_case):
        return {
            "available": False,
            "current_assumption_probability": round(initial_state.customer_deposit_acceptance_probability, 4),
            "minimum_probability": None,
            "message": "The recovery option cannot meet both confidence-bound guardrails even at 100% advance acceptance under these assumptions.",
            "runs_per_check": num_runs,
            "checks": iterations + 1,
        }

    low, high = 0.0, 1.0
    for _ in range(max(1, min(iterations, 12))):
        mid = (low + high) / 2.0
        result = evaluate(mid)
        if passes(result):
            high = mid
        else:
            low = mid

    threshold = round(high, 3)
    # The UI displays three decimals. Re-check that exact displayed value: rounding the
    # binary-search bound down could otherwise show a probability that narrowly fails.
    threshold_result = evaluate(threshold)
    while threshold < 1.0 and not passes(threshold_result):
        threshold = round(threshold + 0.001, 3)
        threshold_result = evaluate(threshold)
    current = float(initial_state.customer_deposit_acceptance_probability)
    return {
        "available": True,
        "current_assumption_probability": round(current, 4),
        "minimum_probability": threshold,
        "margin_percentage_points": round((current - threshold) * 100, 1),
        "passes_guardrails_at_threshold": passes(threshold_result),
        "threshold_sla_success_probability": threshold_result["sla_success_probability"],
        "threshold_sla_success_ci95": threshold_result["sla_success_ci95"],
        "threshold_nonnegative_cash_probability": threshold_result["solvency_probability"],
        "threshold_nonnegative_cash_ci95": threshold_result["solvency_ci95"],
        "guardrails": {
            "sla_lower_bound_minimum_pct": sla_guardrail_pct,
            "nonnegative_cash_lower_bound_minimum_pct": cash_guardrail_pct,
        },
        "runs_per_check": num_runs,
        "checks": iterations + 2,
        "method": "Binary search over the fixed seeded Monte Carlo schedule; conditional on illustrative model assumptions.",
    }


def _required_order_qty(state: WorldState, sku: str) -> int:
    """Local demand calculation avoids coupling the sensitivity helper to engine internals."""
    pending = sum(order.qty for order in state.active_orders if order.status == "pending" and order.sku == sku)
    available = state.inventory[sku].qty if sku in state.inventory else 0
    inbound = sum(
        shipment.qty for shipment in state.incoming_shipments
        if shipment.sku == sku and shipment.status in ("in_transit", "delayed")
    )
    return max(0, pending - available - inbound)
