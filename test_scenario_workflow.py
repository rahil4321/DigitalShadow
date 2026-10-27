"""Regression tests for the user-driven, evidence-grounded scenario workflow."""
import math
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import agents
import api
import scenario_workflow as workflow
from scenario_workflow import ScenarioSpec, build_scenario_state, deterministic_draft, run_custom_simulation


def stub_agents(monkeypatch):
    monkeypatch.setattr(workflow, "generate_strategies_with_status", lambda context, intel, state: (
        agents.fallback_strategies(state),
        {"provider": "test", "model": "test", "status": "fallback_test", "used_live_model": False},
    ))
    monkeypatch.setattr(workflow, "analyze_results_with_status", lambda context, summary, winner: (
        f"Python selected {winner}.", {"provider": "test", "model": "test", "status": "fallback_test", "used_live_model": False},
    ))


def base_scenario(**overrides):
    values = {
        "description": "A possible port disruption may delay an urgent customer shipment.",
        "starting_cash": 6000,
        "sku_name": "LAPTOP",
        "starting_inventory_qty": 0,
        "unit_cost": 500,
        "unit_price": 1000,
        "order_quantity": 10,
        "deadline_days": 4,
        "simulation_horizon_days": 14,
        "num_runs": 100,
    }
    values.update(overrides)
    return ScenarioSpec(**values)


def test_deterministic_draft_extracts_only_contextually_explicit_values():
    draft = deterministic_draft(
        "My distributor has $6,000 in cash. Unit cost $250, sale price $400. "
        "I need 12 phones within 5 days because shipping is disrupted."
    )
    assert draft["starting_cash"] == 6000
    assert draft["unit_cost"] == 250
    assert draft["unit_price"] == 400
    assert draft["order_quantity"] == 12
    assert draft["deadline_days"] == 5
    assert draft["sku_name"] == "PHONE"
    assert draft["simulation_horizon_days"] >= 5


def test_draft_does_not_mistake_first_unit_cost_for_starting_cash():
    draft = deterministic_draft("Unit cost $250; sale price $400; supplier lead time unclear.")
    assert draft["unit_cost"] == 250
    assert draft["unit_price"] == 400
    assert draft["starting_cash"] == 6000  # conspicuously retained as a default


def test_scenario_schema_rejects_horizon_shorter_than_deadline():
    with pytest.raises(ValueError, match="horizon must be at least"):
        base_scenario(deadline_days=10, simulation_horizon_days=7)


def test_scenario_schema_rejects_duplicate_supplier_names():
    with pytest.raises(ValueError, match="must be different"):
        base_scenario(primary_supplier_name="Same", alternate_supplier_name=" same ")


def test_scenario_schema_rejects_non_finite_numeric_inputs():
    with pytest.raises(ValueError):
        base_scenario(starting_cash=math.inf)


def test_scenario_schema_normalizes_sku_and_text():
    scenario = base_scenario(description="  A supplier delay may block our order.  ", sku_name="  laptop  ")
    assert scenario.description == "A supplier delay may block our order."
    assert scenario.sku_name == "LAPTOP"


def test_custom_simulation_returns_strategy_comparison_and_provenance(monkeypatch):
    stub_agents(monkeypatch)
    scenario = base_scenario()
    payload = run_custom_simulation(scenario, {})
    assert payload["scenario"]["sku_name"] == "LAPTOP"
    assert payload["strategies"]
    assert payload["best_strategy_data"]["strategy_id"]
    assert payload["assumption_provenance"]
    assert all(row["direct_source_verified"] is False for row in payload["assumption_provenance"])
    assert payload["evidence_to_assumption_map"] == []
    assert payload["evidence"]["evidence_used"] is False
    assert "guaranteed forecasts" in payload["assumptions"]["risk_warning"]


def test_custom_simulation_sanitizes_source_urls_and_does_not_claim_numeric_facts(monkeypatch):
    stub_agents(monkeypatch)
    scenario = base_scenario()
    evidence = {
        "status": "live_success", "provider": "Tavily Search + Extract", "evidence_used": True,
        "summary": "Three articles discuss broad port disruption.",
        "sources": [
            {"title": "Good source", "url": "https://example.com/story", "content": "Some reported context", "extracted": True, "score": 0.8},
            {"title": "Bad source", "url": "javascript:alert(1)", "content": "not allowed"},
            {"title": "Credential source", "url": "https://user:secret@example.com/story", "content": "not allowed"},
        ],
    }
    payload = run_custom_simulation(scenario, evidence)
    assert len(payload["evidence"]["sources"]) == 1
    assert payload["evidence"]["sources"][0]["url"] == "https://example.com/story"
    assert payload["evidence_to_assumption_map"][0]["numeric_model_input_changed_by_source"] is False
    assert "supplier's lead time" in payload["evidence_to_assumption_map"][0]["does_not_automatically_verify"][0]
    assert all(row["direct_source_verified"] is False for row in payload["assumption_provenance"])


def test_non_finite_external_relevance_scores_are_sanitized(monkeypatch):
    stub_agents(monkeypatch)
    scenario = base_scenario()
    evidence = {
        "status": "live_success",
        "sources": [{"title": "Odd score", "url": "https://example.com", "score": math.nan}],
    }
    payload = run_custom_simulation(scenario, evidence)
    assert payload["evidence"]["sources"][0]["score"] == 0.0
    # The API promises finite JSON numbers; this must not break allow_nan=False serialization.
    import json
    json.dumps(payload, allow_nan=False)


def test_custom_simulation_handles_inventory_that_covers_entire_order(monkeypatch):
    stub_agents(monkeypatch)
    payload = run_custom_simulation(base_scenario(starting_inventory_qty=12, order_quantity=10), {})
    assert payload["world_state"]["inventory"]["LAPTOP"]["qty"] == 12
    assert payload["strategies"]
    assert all(item["action"] is None for item in payload["strategies"])


def test_custom_simulation_with_partial_inventory_procures_only_uncovered_quantity(monkeypatch):
    stub_agents(monkeypatch)
    payload = run_custom_simulation(base_scenario(starting_inventory_qty=6, order_quantity=10), {})
    order_strategies = [item for item in payload["strategies"] if item["action"] == "place_supplier_order"]
    assert order_strategies
    assert all(item["args"][1] == 4 for item in order_strategies)


def test_custom_simulation_does_not_recommend_unaffordable_or_unfunded_procurement(monkeypatch):
    stub_agents(monkeypatch)
    payload = run_custom_simulation(base_scenario(starting_cash=0, customer_advance_amount=0), {})
    assert payload["strategies"]
    assert all(item["action"] is None for item in payload["strategies"])
    assert not any("Order" in item["name"] for item in payload["strategies"])


def test_custom_simulation_supports_order_quantity_above_legacy_limit(monkeypatch):
    stub_agents(monkeypatch)
    scenario = base_scenario(starting_cash=100_000, unit_cost=100, unit_price=150, order_quantity=120, deadline_days=10, simulation_horizon_days=14)
    payload = run_custom_simulation(scenario, {})
    order_strategies = [item for item in payload["strategies"] if item["action"] == "place_supplier_order"]
    assert order_strategies
    assert all(item["args"][1] == 120 for item in order_strategies)


def test_balanced_best_effort_prefers_guardrail_progress_when_nobody_passes():
    scenario = base_scenario(objective="balanced", sla_guardrail_pct=70, solvency_guardrail_pct=95)
    results = [
        {"name": "profit but unsafe", "feasible": True, "expected_profit": 9000, "sla_success_ci95": {"lower": 10}, "solvency_ci95": {"lower": 20}},
        {"name": "risk reduction", "feasible": True, "expected_profit": 100, "sla_success_ci95": {"lower": 65}, "solvency_ci95": {"lower": 90}},
    ]
    winner, note = workflow._select_scenario_recommendation(results, scenario)
    assert winner["name"] == "risk reduction"
    assert "risk remains unresolved" in note.lower()



def test_supplier_premium_changes_affordability_and_selection(monkeypatch):
    stub_agents(monkeypatch)
    scenario = base_scenario(
        starting_cash=6000,
        primary_supplier_fee_per_unit=100,
        alternate_supplier_fee_per_unit=0,
        primary_supplier_reliability=0.98,
        alternate_supplier_reliability=0.98,
        alternate_supplier_lead_time_days=3,
        customer_advance_amount=0,
    )
    payload = run_custom_simulation(scenario, {})
    assert payload["funding_diagnosis"]["primary_supplier_total_cost"] == 6000
    assert payload["funding_diagnosis"]["alternate_supplier_total_cost"] == 5000
    direct_orders = [r for r in payload["strategies"] if r["action"] == "place_supplier_order"]
    assert len(direct_orders) == 2
    primary = next(r for r in direct_orders if "Express Supplier" in r["name"])
    alternate = next(r for r in direct_orders if "Standard Supplier" in r["name"])
    assert primary["expected_profit"] < alternate["expected_profit"]
    assert payload["best_strategy"] == alternate["name"]


def test_cash_reserve_sensitivity_reports_cash_guardrail(monkeypatch):
    stub_agents(monkeypatch)
    payload = run_custom_simulation(base_scenario(starting_cash=5200, num_runs=100), {})
    sensitivity = payload["cash_reserve_sensitivity"]
    assert sensitivity["available"] is True
    assert sensitivity["minimum_starting_cash_estimate"] >= sensitivity["primary_procurement_outflow"]
    assert sensitivity["nonnegative_cash_ci95"]["lower"] >= sensitivity["cash_guardrail_lower_bound_pct"]
    assert sensitivity["runs_per_check"] == 100


def test_custom_scenario_api_persists_simulation_and_strategy_binding(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "DB_PATH", str(tmp_path / "scenario.sqlite3"))
    api.init_db()
    stub_agents(monkeypatch)
    client = TestClient(api.app)
    scenario = base_scenario().model_dump()
    response = client.post("/api/scenario/simulate", json={"scenario": scenario, "evidence": {}})
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["simulation_id"]
    assert payload["strategies"]
    assert payload["evidence_to_assumption_map"] == []
    with api.db() as conn:
        row = conn.execute("SELECT payload FROM simulations WHERE id=?", (payload["simulation_id"],)).fetchone()
    assert row is not None
    # Approvals are bound to this scenario's ID and remain simulated-only.
    response = client.post("/api/execute", json={"simulation_id": payload["simulation_id"], "strategy_id": payload["best_strategy_data"]["strategy_id"]})
    assert response.status_code == 200, response.text
    assert "no supplier was contacted" in " ".join(response.json()["audit_log"]).lower()


def test_research_endpoint_is_honest_without_tavily_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    client = TestClient(api.app)
    response = client.post("/api/scenario/research", json={"description": "A port disruption may delay an urgent customer order."})
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "fallback_missing_key"
    assert payload["sources"] == []
    assert payload["evidence_used"] is False
    assert "not configured" in payload["summary"].lower()


def test_draft_endpoint_returns_editable_fallback_without_nebius_key(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    client = TestClient(api.app)
    response = client.post("/api/scenario/draft", json={"description": "We have $6,000 in cash and need 8 phones within 5 days."})
    assert response.status_code == 200
    payload = response.json()
    assert payload["draft"]["starting_cash"] == 6000
    assert payload["draft"]["order_quantity"] == 8
    assert payload["draft"]["deadline_days"] == 5
    assert payload["integration"]["used_live_model"] is False



def test_funding_diagnosis_flags_unfunded_order_with_actionable_gap():
    scenario = base_scenario(starting_cash=1000, unit_cost=500, order_quantity=10, customer_advance_amount=2000)
    diagnosis = workflow.diagnose_funding(scenario)
    assert diagnosis["status"] == "funding_gap"
    assert diagnosis["estimated_procurement_cost"] == 5000
    assert diagnosis["cash_shortfall_before_advance"] == 4000
    assert diagnosis["funding_shortfall_after_advance"] == 2000
    assert any("beyond starting cash" in item.lower() for item in diagnosis["next_steps"])


def test_funding_diagnosis_respects_partial_inventory_and_cash():
    scenario = base_scenario(starting_cash=2500, starting_inventory_qty=6, order_quantity=10, unit_cost=500)
    diagnosis = workflow.diagnose_funding(scenario)
    assert diagnosis["uncovered_quantity"] == 4
    assert diagnosis["estimated_procurement_cost"] == 2000
    assert diagnosis["status"] == "cash_funded"


def test_funding_diagnosis_does_not_recommend_procurement_when_inventory_covers_order():
    scenario = base_scenario(starting_cash=0, starting_inventory_qty=12, order_quantity=10)
    diagnosis = workflow.diagnose_funding(scenario)
    assert diagnosis["status"] == "inventory_covers_demand"
    assert diagnosis["uncovered_quantity"] == 0
    assert diagnosis["estimated_procurement_cost"] == 0


def test_custom_simulation_includes_funding_diagnosis_when_no_order_is_affordable(monkeypatch):
    stub_agents(monkeypatch)
    payload = run_custom_simulation(base_scenario(starting_cash=1000, customer_advance_amount=2000), {})
    assert payload["funding_diagnosis"]["status"] == "funding_gap"
    assert len(payload["strategies"]) == 1
    assert payload["best_strategy"] == "Preserve Cash / Wait"


def test_multiple_business_scenarios_produce_finite_auditable_outputs(monkeypatch):
    import json

    stub_agents(monkeypatch)
    cases = [
        base_scenario(
            scenario_name="Phone distributor", description="A shipping delay may affect a phone distributor's order.",
            sku_name="PHONE", starting_cash=9000, unit_cost=240, unit_price=390,
            order_quantity=14, deadline_days=5, simulation_horizon_days=12,
        ),
        base_scenario(
            scenario_name="Medical supplies", description="A supplier disruption may affect medical supply deliveries.",
            sku_name="MEDICAL_SUPPLY", starting_cash=3500, starting_inventory_qty=3,
            unit_cost=200, unit_price=320, order_quantity=10, deadline_days=8,
            primary_supplier_lead_time_days=3, alternate_supplier_lead_time_days=9,
            simulation_horizon_days=14, objective="protect_cash",
        ),
        base_scenario(
            scenario_name="Tight cash", description="A cash shortage may prevent replenishment before an order deadline.",
            starting_cash=500, customer_advance_amount=1000, unit_cost=500, unit_price=700,
            order_quantity=8, deadline_days=3, simulation_horizon_days=10,
        ),
    ]
    for scenario in cases:
        payload = run_custom_simulation(scenario, {})
        assert payload["scenario"]["sku_name"] == scenario.sku_name
        assert payload["strategies"]
        assert payload["best_strategy_data"]["feasible"] is True
        assert payload["funding_diagnosis"]["uncovered_quantity"] == max(0, scenario.order_quantity - scenario.starting_inventory_qty)
        assert all(math.isfinite(float(item["expected_profit"])) for item in payload["strategies"])
        assert all(0 <= float(item["sla_success_probability"]) <= 100 for item in payload["strategies"])
        # The production serializer uses the same strict non-NaN contract as this check.
        json.dumps(payload, allow_nan=False)


def test_research_scenario_uses_multi_query_and_extracts_tavily_sources(monkeypatch):
    queries = []
    monkeypatch.setenv("TAVILY_API_KEY", "test-key")

    class FakeTavilyClient:
        def __init__(self, api_key):
            assert api_key == "test-key"

        def search(self, **kwargs):
            queries.append(kwargs["query"])
            assert kwargs["topic"] == "news"
            assert kwargs["search_depth"] == "advanced"
            return {"request_id": f"request-{len(queries)}", "results": [
                {"title": "Port disruption report", "url": "https://example.com/disruption",
                 "content": "A reported port disruption may affect cargo movement.", "score": 0.8, "published_date": "2026-10-25"},
                {"title": "Backup route guidance", "url": "https://example.org/routes",
                 "content": "Rerouting may be an option.", "score": 0.6},
            ]}

        def extract(self, urls, extract_depth, format):
            assert extract_depth == "advanced"
            assert format == "text"
            return {"results": [{"url": urls[0], "raw_content": "Full extracted article content for the port disruption report."}]}

    monkeypatch.setitem(sys.modules, "tavily", SimpleNamespace(TavilyClient=FakeTavilyClient))
    result = workflow.research_scenario(
        "A port disruption could delay an urgent electronics shipment.",
        "Port of Singapore cargo disruption alternate routes", max_sources=6,
    )
    assert result["status"] == "live_success"
    assert len(queries) == 3 and len(set(queries)) == 3
    assert len(result["sources"]) == 2  # shared URLs are deduplicated across search angles
    first = next(row for row in result["sources"] if row["url"] == "https://example.com/disruption")
    assert first["extracted"] is True
    assert "Full extracted article content" in first["content"]
    assert result["evidence_used"] is True


def test_untrusted_source_nonfinite_score_is_sanitized_before_serialization(monkeypatch):
    stub_agents(monkeypatch)
    payload = run_custom_simulation(base_scenario(), {
        "evidence_used": True, "status": "live_success",
        "sources": [{"title": "Evidence", "url": "https://example.com/evidence", "score": float("nan"), "content": "Some context."}],
    })
    assert payload["evidence"]["sources"][0]["score"] == 0.0
    import json
    json.dumps(payload, allow_nan=False)
