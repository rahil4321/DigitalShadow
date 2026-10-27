import agents
import api
from simulator import find_minimum_advance_acceptance
from fastapi.testclient import TestClient


def configure_test_api(monkeypatch, tmp_path):
    monkeypatch.setattr(api, "DB_PATH", str(tmp_path / "simulations.sqlite3"))
    api.init_db()
    monkeypatch.setattr(api, "fetch_external_reality", lambda query: {
        "scenario_delay_days": 7,
        "provenance": "demo_fallback",
        "retrieved_at": "2026-10-11T00:00:00+00:00",
        "sources": [],
        "summary": "Test fixture: demo fallback, not live evidence.",
    })
    monkeypatch.setattr(api, "generate_strategies_with_status", lambda context, intel, state: (
        agents.fallback_strategies(state), {"provider": "test", "model": "test", "status": "test_stub", "used_live_model": False}
    ))
    monkeypatch.setattr(api, "analyze_results_with_status", lambda context, summary, winner: (
        f"Python selected {winner}.", {"provider": "test", "model": "test", "status": "test_stub", "used_live_model": False}
    ))
    return TestClient(api.app)


def test_health_endpoint():
    client = TestClient(api.app)
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_crisis_returns_distinct_decisions_and_recommends_recovery(monkeypatch, tmp_path):
    client = configure_test_api(monkeypatch, tmp_path)
    response = client.get("/api/simulate?disruption=true&num_runs=100")
    assert response.status_code == 200
    payload = response.json()
    strategies = payload["strategies"]
    signatures = {(s["action"], str(s["args"])) for s in strategies}
    assert len(signatures) == len(strategies) == 3
    assert payload["best_strategy_data"]["expected_profit"] > 0
    assert payload["best_strategy_data"]["sla_success_probability"] > 0
    assert payload["assumptions"]["customer_deposit_acceptance_probability"] == 0.8
    assert payload["integrations"]["planner"]["status"] == "test_stub"
    assert payload["integrations"]["analyst"]["status"] == "test_stub"
    assert payload["integrations"]["external_evidence"]["source_count"] == 0


def test_approval_is_bound_to_saved_simulation_and_one_time(monkeypatch, tmp_path):
    client = configure_test_api(monkeypatch, tmp_path)
    payload = client.get("/api/simulate?disruption=true&num_runs=100").json()
    sim_id = payload["simulation_id"]
    strategy_id = payload["best_strategy_data"]["strategy_id"]
    bad = client.post("/api/execute", json={"simulation_id": sim_id, "strategy_id": "not-this-strategy"})
    assert bad.status_code == 400
    good = client.post("/api/execute", json={"simulation_id": sim_id, "strategy_id": strategy_id})
    assert good.status_code == 200
    assert good.json()["status"] == "simulated_success"
    assert "no supplier was contacted" in " ".join(good.json()["audit_log"]).lower()
    repeat = client.post("/api/execute", json={"simulation_id": sim_id, "strategy_id": strategy_id})
    assert repeat.status_code == 409


def test_execution_cannot_mix_strategy_from_another_simulation(monkeypatch, tmp_path):
    client = configure_test_api(monkeypatch, tmp_path)
    first = client.get("/api/simulate?disruption=false&num_runs=100").json()
    second = client.get("/api/simulate?disruption=true&num_runs=100").json()
    response = client.post("/api/execute", json={
        "simulation_id": first["simulation_id"],
        "strategy_id": second["best_strategy_data"]["strategy_id"],
    })
    assert response.status_code == 400


def test_simulation_request_rejects_run_counts_outside_api_contract():
    client = TestClient(api.app)
    assert client.get("/api/simulate?num_runs=99").status_code == 422
    assert client.get("/api/simulate?num_runs=1001").status_code == 422


def test_execute_rejects_extra_fields(monkeypatch, tmp_path):
    client = configure_test_api(monkeypatch, tmp_path)
    response = client.post("/api/execute", json={
        "simulation_id": "12345678",
        "strategy_id": "strategy-1",
        "unexpected": "not accepted",
    })
    assert response.status_code == 422


def test_simulation_persists_the_exact_id_and_declares_accounting_assumptions(monkeypatch, tmp_path):
    client = configure_test_api(monkeypatch, tmp_path)
    payload = client.get("/api/simulate?disruption=false&num_runs=100").json()
    with api.db() as conn:
        row = conn.execute("SELECT payload FROM simulations WHERE id=?", (payload["simulation_id"],)).fetchone()
    assert row is not None
    import json
    stored = json.loads(row["payload"])
    assert stored["simulation_id"] == payload["simulation_id"]
    assert stored["world_state"] == payload["world_state"]
    assert "unsold inventory remains an asset" in payload["assumptions"]["accounting_rule"]
    assert payload["assumptions"]["simulation_horizon_days"] == 7


def test_external_reality_is_sanitized_before_it_sets_scenario_parameters():
    normalized = api._normalize_reality({
        "scenario_delay_days": 999,
        "provenance": "web_estimate",
        "summary": "general news only",
        "sources": [{"title": "Safe title", "url": "javascript:alert(1)", "content": "x" * 5000}],
        "retrieved_at": "now",
    })
    assert normalized["scenario_delay_days"] == 6
    assert normalized["provenance"] == "demo_fallback"
    assert "outside the supported" in normalized["summary"].lower()
    assert len(normalized["sources"][0]["content"]) == 1200
    assert normalized["sources"][0]["url"] == ""  # the backend rejects non-HTTP(S) URLs as defense in depth
    assert normalized["retrieved_at"] != "now"  # malformed timestamps are replaced with valid UTC ISO time
    assert api.create_base_state(normalized["scenario_delay_days"], False).suppliers["SLOW_SUPPLIER"].lead_time_days == 6


def test_invalid_external_delay_uses_explicit_demo_assumption():
    normalized = api._normalize_reality({"scenario_delay_days": "not-a-number", "sources": []})
    assert normalized["scenario_delay_days"] == 6
    assert normalized["provenance"] == "demo_fallback"
    assert "invalid" in normalized["summary"].lower()


def test_external_sources_reject_credentials_and_normalize_valid_urls_and_timestamps():
    normalized = api._normalize_reality({
        "scenario_delay_days": 7,
        "provenance": "web_estimate",
        "summary": "general shipping context",
        "retrieved_at": "2026-10-11T15:00:00+05:30",
        "sources": [
            {"title": "Valid", "url": "https://example.com/story", "content": "ok"},
            {"title": "Credentials", "url": "https://user:secret@example.com/unsafe", "content": "no"},
        ],
    })
    assert normalized["sources"][0]["url"] == "https://example.com/story"
    assert normalized["sources"][1]["url"] == ""
    assert normalized["retrieved_at"].endswith("+00:00")


def test_default_simulation_uses_one_thousand_runs(monkeypatch, tmp_path):
    client = configure_test_api(monkeypatch, tmp_path)
    payload = client.get("/api/simulate").json()
    assert payload["assumptions"]["num_runs"] == 1000
    assert all(strategy["runs"] in (0, 1000) for strategy in payload["strategies"])
    assert "95% Wilson lower bounds" in payload["assumptions"]["decision_policy"]


def test_crisis_tipping_point_returns_a_displayed_threshold_that_passes_guardrails():
    state = api.create_base_state(6, True)
    result = find_minimum_advance_acceptance(state, num_runs=300, iterations=6)
    assert result["available"] is True
    assert result["passes_guardrails_at_threshold"] is True
    assert result["minimum_probability"] <= result["current_assumption_probability"]
    assert result["threshold_sla_success_ci95"]["lower"] >= result["guardrails"]["sla_lower_bound_minimum_pct"]
    assert result["threshold_nonnegative_cash_ci95"]["lower"] >= result["guardrails"]["nonnegative_cash_lower_bound_minimum_pct"]
