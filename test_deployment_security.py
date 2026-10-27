"""Tests for optional public-demo API access control and lightweight quotas."""
from fastapi.testclient import TestClient
import api as api_module


def test_health_remains_public_when_demo_password_is_enabled(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_PASSWORD", "judge-test-secret")
    with TestClient(api_module.app) as client:
        response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_cost_bearing_api_requires_demo_access_code(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_PASSWORD", "judge-test-secret")
    with TestClient(api_module.app) as client:
        missing = client.post("/api/scenario/research", json={
            "description": "A shipping disruption is delaying our laptop shipment."
        })
        wrong = client.post("/api/scenario/research", headers={"X-Demo-Access": "wrong"}, json={
            "description": "A shipping disruption is delaying our laptop shipment."
        })
    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert "access code" in missing.json()["detail"].lower()


def test_correct_demo_access_code_reaches_research_route(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_PASSWORD", "judge-test-secret")
    monkeypatch.setattr(api_module, "research_scenario", lambda *args: {
        "status": "live_success", "sources": [{"title": "Test", "url": "https://example.com"}],
        "evidence_used": True,
    })
    headers = {"X-Demo-Access": "judge-test-secret", "X-Forwarded-For": "198.51.100.18"}
    with TestClient(api_module.app) as client:
        response = client.post("/api/scenario/research", headers=headers, json={
            "description": "A shipping disruption is delaying our laptop shipment."
        })
    assert response.status_code == 200
    assert response.json()["evidence_used"] is True


def test_research_route_rate_limited_for_password_holders(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_PASSWORD", "judge-test-secret")
    monkeypatch.setattr(api_module, "research_scenario", lambda *args: {
        "status": "no_results", "sources": [], "evidence_used": False,
    })
    api_module._DEMO_RATE_EVENTS.clear()
    headers = {"X-Demo-Access": "judge-test-secret", "X-Forwarded-For": "198.51.100.27"}
    with TestClient(api_module.app) as client:
        responses = [client.post("/api/scenario/research", headers=headers, json={
            "description": "A shipping disruption is delaying our laptop shipment."
        }) for _ in range(7)]
    assert [r.status_code for r in responses[:6]] == [200] * 6
    assert responses[6].status_code == 429
    assert responses[6].headers.get("retry-after")
    api_module._DEMO_RATE_EVENTS.clear()


def test_cors_preflight_is_not_blocked_by_demo_gate(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_PASSWORD", "judge-test-secret")
    with TestClient(api_module.app) as client:
        response = client.options("/api/scenario/research", headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type,x-demo-access",
        })
    assert response.status_code in (200, 204)


def test_service_wide_research_cap_applies_across_ips(monkeypatch):
    monkeypatch.setenv("DEMO_ACCESS_PASSWORD", "judge-test-secret")
    monkeypatch.setattr(api_module, "research_scenario", lambda *args: {
        "status": "no_results", "sources": [], "evidence_used": False,
    })
    api_module._DEMO_RATE_EVENTS.clear()
    with TestClient(api_module.app) as client:
        responses = []
        for index in range(9):
            responses.append(client.post(
                "/api/scenario/research",
                headers={
                    "X-Demo-Access": "judge-test-secret",
                    "X-Forwarded-For": f"198.51.100.{index + 30}",
                },
                json={"description": "A shipping disruption is delaying our laptop shipment."},
            ))
    assert [response.status_code for response in responses[:8]] == [200] * 8
    assert responses[8].status_code == 429
    api_module._DEMO_RATE_EVENTS.clear()
