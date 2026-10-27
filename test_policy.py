"""Regression tests for the recommendation guardrail policy."""
import pytest

from api import select_recommendation
from simulator import wilson_interval


def candidate(name, profit, sla, solvency, feasible=True):
    return {
        "name": name,
        "expected_profit": profit,
        "sla_success_probability": sla,
        "solvency_probability": solvency,
        "feasible": feasible,
    }


def test_policy_maximizes_profit_only_inside_both_guardrails():
    results = [
        candidate("highest profit but unsafe", 10000, 69.9, 100),
        candidate("safe but lower profit", 4000, 70, 95),
        candidate("safe and highest eligible profit", 4500, 90, 98),
        candidate("infeasible distractor", 100000, 100, 100, feasible=False),
    ]
    winner, note = select_recommendation(results)
    assert winner["name"] == "safe and highest eligible profit"
    assert "maximize expected operating profit" in note


def test_policy_uses_best_effort_lexicographic_order_when_no_candidate_passes():
    results = [
        candidate("more profit", 9000, 60, 100),
        candidate("better SLA", -500, 70, 50),
        candidate("equal SLA better solvency", 10, 70, 80),
    ]
    winner, note = select_recommendation(results)
    assert winner["name"] == "equal SLA better solvency"
    assert "best-effort fallback" in note


def test_policy_uses_profit_as_last_tie_breaker_in_best_effort_mode():
    results = [
        candidate("lower profit", 100, 70, 80),
        candidate("higher profit", 101, 70, 80),
    ]
    winner, note = select_recommendation(results)
    assert winner["name"] == "higher profit"
    assert "rank by the 95% Wilson lower bound for SLA success" in note


def test_policy_rejects_all_infeasible_candidates():
    with pytest.raises(ValueError, match="without a feasible strategy"):
        select_recommendation([candidate("bad", 999, 100, 100, feasible=False)])


def test_wilson_interval_accounts_for_zero_observed_failures():
    interval = wilson_interval(200, 200)
    assert interval["lower"] < 100.0
    assert interval["upper"] == 100.0
    assert interval["lower"] == pytest.approx(98.1154, abs=0.001)


def test_guardrails_use_lower_confidence_bound_not_rounded_point_probability():
    high_point_but_underpowered = candidate("underpowered", 100000, 70.0, 100.0)
    high_point_but_underpowered.update(runs=100, sla_success_runs=70, solvent_runs=100)
    confidence_bound_eligible = candidate("robust sample", 100, 78.0, 98.0)
    confidence_bound_eligible.update(runs=1000, sla_success_runs=780, solvent_runs=980)

    winner, note = select_recommendation([high_point_but_underpowered, confidence_bound_eligible])
    assert winner["name"] == "robust sample"
    assert "95% Wilson lower bounds" in note


def test_policy_does_not_trust_rounded_probability_when_counts_are_available():
    rounded_up_but_ineligible = candidate("display rounds to 70", 100000, 70.0, 100.0)
    rounded_up_but_ineligible.update(runs=999, sla_success_runs=699, solvent_runs=999)
    eligible = candidate("eligible", 100, 80.0, 100.0)
    eligible.update(runs=1000, sla_success_runs=800, solvent_runs=1000)

    winner, _ = select_recommendation([rounded_up_but_ineligible, eligible])
    assert winner["name"] == "eligible"
