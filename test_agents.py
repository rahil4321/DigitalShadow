"""Regression tests for normalizing structured model output at the AI boundary."""
import json
from types import SimpleNamespace

import agents
from api import create_base_state


def test_planner_normalizes_string_null_to_valid_noop_without_fallback_warning(monkeypatch, capsys):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    from test_hardening import state_factory
    state = state_factory(cash=10_000)
    payload = json.dumps([
        {"name": "Preserve Cash", "action": "null", "args": []},
        {"name": "Fast Order", "action": "place_supplier_order", "args": ["LAPTOP", 10, "FAST_SUPPLIER"]},
        {"name": "Unneeded Advance", "action": "request_customer_deposit_and_order", "args": ["LAPTOP", 10, "FAST_SUPPLIER"]},
    ])
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=payload))]
    )
    client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=lambda **kwargs: response)
        )
    )
    monkeypatch.setattr(agents, "get_client", lambda: client)

    result = agents.generate_strategies("crisis", "intel", state)

    assert result[0]["action"] is None
    assert result[0]["args"] == []
    assert any(item["action"] == "place_supplier_order" for item in result)
    assert not any(item["action"] == "request_customer_deposit_and_order" for item in result)
    status_result, status = agents.generate_strategies_with_status("crisis", "intel", state)
    assert len(status_result) == len(result)
    assert status["used_live_model"] is True
    assert status["status"] == "partial_live_with_fallback"
    assert status["rejected_candidate_count"] == 1
    assert "Planner fallback" not in capsys.readouterr().out


def test_status_api_marks_missing_nebius_key_as_demo(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    state = create_base_state(7, disruption=True)
    candidates, status = agents.generate_strategies_with_status("crisis", "intel", state)
    assert len(candidates) == 3
    assert status["status"] == "fallback_missing_key"
    assert status["used_live_model"] is False
    text, analyst_status = agents.analyze_results_with_status("crisis", "results", "Preserve Cash")
    assert "unavailable in demo mode" in text
    assert analyst_status["status"] == "fallback_missing_key"


def test_status_api_does_not_mislabel_transport_failure_as_invalid_output(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-not-used-for-network")
    def fail():
        raise TimeoutError("simulated provider timeout")
    monkeypatch.setattr(agents, "get_client", fail)
    state = create_base_state(7, disruption=True)
    candidates, status = agents.generate_strategies_with_status("crisis", "intel", state)
    assert len(candidates) == 3
    assert status["status"] == "fallback_after_error"
    assert status["error_type"] == "TimeoutError"
    _, analyst_status = agents.analyze_results_with_status("crisis", "results", "Preserve Cash")
    assert analyst_status["status"] == "fallback_after_error"
    assert analyst_status["error_type"] == "TimeoutError"


def test_planner_parses_wrapped_json_and_uses_canonical_display_names(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    state = create_base_state(scenario_delay_days=6, disruption=False)
    payload = "Planner output follows:\n```json\n" + json.dumps({"strategies": [
        {"name": "null", "action": "null", "args": []},
        {"name": "place_supplier_order", "action": "place_supplier_order", "args": ["LAPTOP", 10, "FAST_SUPPLIER"]},
        {"name": "nonsense label", "action": "place_supplier_order", "args": ["LAPTOP", 10, "SLOW_SUPPLIER"]},
    ]}) + "\n```\nEnd of response."
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    monkeypatch.setattr(agents, "get_client", lambda: client)

    result, status = agents.generate_strategies_with_status("baseline", "intel", state)

    names_by_signature = {(item["action"], tuple(item["args"])): item["name"] for item in result}
    assert names_by_signature[(None, ())] == "Preserve Cash"
    assert names_by_signature[("place_supplier_order", ("LAPTOP", 10, "FAST_SUPPLIER"))] == "Place Order · Fast Supplier"
    assert names_by_signature[("place_supplier_order", ("LAPTOP", 10, "SLOW_SUPPLIER"))] == "Place Order · Standard Supplier"
    assert status["used_live_model"] is True
    assert status["status"] in {"live_success", "live_success_with_fallback", "partial_live_with_fallback"}


def test_one_invalid_planner_candidate_does_not_discard_other_valid_candidates(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key")
    from test_hardening import state_factory
    state = state_factory(cash=10_000)
    payload = json.dumps([
        {"name": "broken", "action": "unsupported_action", "args": []},
        {"name": "valid", "action": "place_supplier_order", "args": ["LAPTOP", 10, "FAST_SUPPLIER"]},
    ])
    response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=payload))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    monkeypatch.setattr(agents, "get_client", lambda: client)

    result, status = agents.generate_strategies_with_status("baseline", "intel", state)

    assert any(item["action"] == "place_supplier_order" for item in result)
    assert any(item["name"] == "Preserve Cash" for item in result)
    assert status["used_live_model"] is True
    assert status["rejected_candidate_count"] == 1
