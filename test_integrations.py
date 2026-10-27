"""External integrations tested with stubs; these tests never make network calls."""
import json
import sys
from types import SimpleNamespace

import agents
import tavily_agent
from api import create_base_state


def test_planner_uses_validated_fallback_when_token_factory_key_is_missing(monkeypatch):
    monkeypatch.delenv("NEBIUS_API_KEY", raising=False)
    state = create_base_state(7, disruption=True)
    candidates = agents.generate_strategies("test", "demo context", state)
    assert len(candidates) == 3
    signatures = {(item["action"], tuple(item["args"])) for item in candidates}
    assert len(signatures) == 3
    assert all(agents.validate_action(state, item["action"], item["args"])[0] for item in candidates)


def test_bad_nemotron_plan_cannot_bypass_rules_and_fallback_fills_candidates(monkeypatch):
    monkeypatch.setenv("NEBIUS_API_KEY", "test-key-not-used-for-network")
    text = json.dumps([
        {"name": "AI fast", "action": "place_supplier_order", "args": ["LAPTOP", 10, "FAST_SUPPLIER"]},
        {"name": "AI unsafe", "action": "place_supplier_order", "args": ["LAPTOP", -100, "FAST_SUPPLIER"]},
        {"name": "AI duplicate", "action": "place_supplier_order", "args": ["LAPTOP", 10, "FAST_SUPPLIER"]},
    ])
    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))]
    ))))
    monkeypatch.setattr(agents, "get_client", lambda: fake_client)
    state = create_base_state(7, disruption=False)
    candidates = agents.generate_strategies("test", "demo context", state)
    assert len(candidates) == 3
    signatures = {(item["action"], tuple(item["args"])) for item in candidates}
    assert len(signatures) == 3
    assert all(agents.validate_action(state, item["action"], item["args"])[0] for item in candidates)


def test_tavily_and_nebius_live_path_uses_token_factory_and_labels_general_news(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-nebius-key")
    monkeypatch.setattr(tavily_agent, "BASE_URL", "https://api.tokenfactory.us-central1.nebius.com/v1/")

    class FakeTavilyClient:
        def __init__(self, api_key):
            assert api_key == "test-tavily-key"

        def search(self, query, max_results, topic):
            assert query
            assert max_results == 3
            assert topic == "news"
            return {"results": [{"title": "Port backlog story", "url": "https://example.com/story", "content": "port delay context"}]}

    class FakeOpenAI:
        def __init__(self, *, base_url, api_key, timeout, max_retries):
            assert base_url == "https://api.tokenfactory.us-central1.nebius.com/v1/"
            assert api_key == "test-nebius-key"

        @property
        def chat(self):
            return SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"scenario_delay_days": 8}'))]
            )))

    monkeypatch.setitem(sys.modules, "tavily", SimpleNamespace(TavilyClient=FakeTavilyClient))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    result = tavily_agent.fetch_external_reality("shipping delay news")
    assert result["scenario_delay_days"] == 8
    assert result["provenance"] == "web_estimate"
    assert result["sources"][0]["url"] == "https://example.com/story"
    assert "not a verified supplier eta" in result["summary"].lower().lower()


def test_tavily_missing_key_falls_back_without_claiming_live_evidence(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    result = tavily_agent.fetch_external_reality("shipping delay news")
    assert result["provenance"] == "demo_fallback"
    assert result["sources"] == []
    assert "demo assumption" in result["summary"].lower()


def test_tavily_sources_are_preserved_when_nemotron_estimation_fails(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-nebius-key")

    class FakeTavilyClient:
        def __init__(self, api_key):
            assert api_key == "test-tavily-key"

        def search(self, query, max_results, topic):
            return {"results": [{"title": "Port delay report", "url": "https://example.com/port", "content": "General shipping delay context"}]}

    class FakeOpenAI:
        def __init__(self, **kwargs):
            pass

        @property
        def chat(self):
            def fail(**kwargs):
                raise TimeoutError("simulated timeout")
            return SimpleNamespace(completions=SimpleNamespace(create=fail))

    monkeypatch.setitem(sys.modules, "tavily", SimpleNamespace(TavilyClient=FakeTavilyClient))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    result = tavily_agent.fetch_external_reality("shipping delay news")

    assert result["scenario_delay_days"] == 6
    assert result["provenance"] == "sources_retrieved_estimate_unavailable"
    assert result["sources"][0]["url"] == "https://example.com/port"
    assert "Nemotron estimation failed" in result["summary"]
    assert "not a verified supplier eta" in result["summary"].lower()


def test_tavily_sources_are_preserved_when_nemotron_returns_invalid_json(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setenv("NEBIUS_API_KEY", "test-nebius-key")

    class FakeTavilyClient:
        def __init__(self, api_key):
            pass

        def search(self, query, max_results, topic):
            return {"results": [{"title": "Port delay report", "url": "https://example.com/port", "content": "Context"}]}

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content='{"scenario_delay_days":99}'))]
    ))))
    class FakeOpenAI:
        def __init__(self, **kwargs):
            pass
        @property
        def chat(self):
            return fake_client.chat

    monkeypatch.setitem(sys.modules, "tavily", SimpleNamespace(TavilyClient=FakeTavilyClient))
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    result = tavily_agent.fetch_external_reality("shipping delay news")

    assert result["provenance"] == "sources_retrieved_estimate_unavailable"
    assert result["scenario_delay_days"] == 6
    assert len(result["sources"]) == 1
    assert "invalid delay estimate" in result["summary"].lower()


def test_tavily_missing_package_has_actionable_fallback(monkeypatch):
    monkeypatch.setenv("TAVILY_API_KEY", "test-tavily-key")
    monkeypatch.setitem(sys.modules, "tavily", None)
    result = tavily_agent.fetch_external_reality("shipping delay news")
    assert result["provenance"] == "demo_fallback"
    assert result["sources"] == []
    assert "dependency is missing" in result["summary"].lower()
    assert "install requirements.txt" in result["summary"].lower()
