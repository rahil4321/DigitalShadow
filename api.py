"""FastAPI interface for Digital Shadow's local simulation environment."""
import json
import os
import random
import sqlite3
import uuid
import hmac
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

from models import WorldState, SKU, Supplier, Order
from engine import advance_time, apply_strategy, validate_action
from simulator import find_minimum_advance_acceptance, simulate_strategy, wilson_interval
from agents import analyze_results_with_status, generate_strategies_with_status
from tavily_agent import fetch_external_reality
from scoring import evaluate_scenario
from scenario_workflow import (
    ScenarioDraftRequest, ScenarioResearchRequest, ScenarioSimulationRequest,
    draft_scenario, research_scenario, run_custom_simulation,
)

# Load local credentials/config before reading module-level settings. In production,
# platform environment variables take precedence and .env is not required.
load_dotenv()
DB_PATH = os.getenv("DIGITAL_SHADOW_DB") or "digital_shadow.sqlite3"
app = FastAPI(
    title="Digital Shadow",
    version="2.0.0",
    description="Explainable operational decision simulator; approval never places real orders.",
)
_origins = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "X-Demo-Access"],
)

# Optional public-demo protection. Enable by setting DEMO_ACCESS_PASSWORD in the
# host environment; never put that value in source control or frontend build args.
_DEMO_RATE_LIMITS = {
    "/api/scenario/draft": (12, 3600),
    "/api/scenario/research": (6, 3600),
    "/api/scenario/simulate": (18, 3600),
    "/api/simulate": (6, 3600),
    "/api/execute": (12, 3600),
}
# A service-wide cap also applies, so changing/spoofing a forwarded-IP header
# cannot by itself multiply the demo's allowed provider-triggering calls.
_DEMO_GLOBAL_LIMITS = {
    "/api/scenario/draft": (20, 3600),
    "/api/scenario/research": (8, 3600),
    "/api/scenario/simulate": (20, 3600),
    "/api/simulate": (8, 3600),
    "/api/execute": (20, 3600),
}
_DEMO_RATE_EVENTS: dict[tuple[str, str], list[float]] = {}


@app.middleware("http")
async def protect_public_demo(request: Request, call_next):
    """Guard cost-bearing API routes when a public demo password is configured.

    Local development stays convenient when DEMO_ACCESS_PASSWORD is unset. For a
    public deployment, configure it as a private host environment variable.
    Limits are in-memory and intended as a lightweight demo safeguard, not a
    substitute for a production API gateway or per-user quotas.
    """
    password = os.getenv("DEMO_ACCESS_PASSWORD", "").strip()
    path = request.url.path
    if password and request.method != "OPTIONS" and path.startswith("/api/") and path != "/api/health":
        supplied = request.headers.get("x-demo-access", "")
        if not supplied or not hmac.compare_digest(supplied, password):
            return JSONResponse(
                status_code=401,
                content={"detail": "Demo access code required or incorrect."},
                headers={"Cache-Control": "no-store"},
            )

        limit = _DEMO_RATE_LIMITS.get(path)
        if limit and request.method in {"POST", "GET"}:
            max_requests, window_seconds = limit
            # Render supplies the public client's address in X-Forwarded-For.
            # The shared access code is still required if a caller changes it.
            forwarded = request.headers.get("x-forwarded-for", "")
            client_ip = forwarded.split(",", 1)[0].strip() or (request.client.host if request.client else "unknown")
            now = time.monotonic()
            key = (client_ip, path)
            recent = [t for t in _DEMO_RATE_EVENTS.get(key, []) if now - t < window_seconds]
            if len(recent) >= max_requests:
                retry_after = max(1, int(window_seconds - (now - recent[0])))
                return JSONResponse(
                    status_code=429,
                    content={"detail": f"Demo limit reached for this action. Try again in about {retry_after // 60 + 1} minute(s)."},
                    headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
                )
            recent.append(now)
            _DEMO_RATE_EVENTS[key] = recent

            global_max, global_window = _DEMO_GLOBAL_LIMITS[path]
            global_key = ("__global__", path)
            global_recent = [t for t in _DEMO_RATE_EVENTS.get(global_key, []) if now - t < global_window]
            if len(global_recent) >= global_max:
                retry_after = max(1, int(global_window - (now - global_recent[0])))
                return JSONResponse(
                    status_code=429,
                    content={"detail": "The demo-wide usage cap has been reached. Please try again later."},
                    headers={"Retry-After": str(retry_after), "Cache-Control": "no-store"},
                )
            global_recent.append(now)
            _DEMO_RATE_EVENTS[global_key] = global_recent

            if len(_DEMO_RATE_EVENTS) > 2000:
                cutoff = now - max(window for _, window in _DEMO_RATE_LIMITS.values())
                for old_key in list(_DEMO_RATE_EVENTS):
                    _DEMO_RATE_EVENTS[old_key] = [t for t in _DEMO_RATE_EVENTS[old_key] if t >= cutoff]
                    if not _DEMO_RATE_EVENTS[old_key]:
                        _DEMO_RATE_EVENTS.pop(old_key, None)
    return await call_next(request)


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    simulation_id: str = Field(min_length=8, max_length=80)
    strategy_id: str = Field(min_length=1, max_length=80)


@contextmanager
def db():
    """Open a bounded-wait SQLite connection and commit/rollback atomically."""
    if DB_PATH != ":memory:":
        Path(DB_PATH).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 10000")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS simulations (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                payload TEXT NOT NULL,
                executed INTEGER NOT NULL DEFAULT 0,
                execution_payload TEXT
            )"""
        )


# Keep the app usable with a single `uvicorn api:app` command.
init_db()


def _fallback_reality(summary: str = "Demo assumption only; live external evidence unavailable.") -> dict:
    return {
        "scenario_delay_days": 6,
        "provenance": "demo_fallback",
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "sources": [],
        "summary": summary,
    }


def _normalize_reality(value: Any) -> dict:
    """Validate external-tool output before it enters business logic or the UI."""
    if not isinstance(value, dict):
        return _fallback_reality("External intelligence returned an invalid payload; using the demo assumption.")
    raw_delay = value.get("scenario_delay_days", 6)
    if isinstance(raw_delay, bool) or not isinstance(raw_delay, int) or not 1 <= raw_delay <= 14:
        delay = 6
        provenance = "demo_fallback"
        summary = "External delay value was invalid or outside the supported 1–14 day range; using a six-day demo assumption."
    else:
        delay = raw_delay
        provenance = str(value.get("provenance") or "demo_fallback")[:80]
        summary = str(value.get("summary") or "No external summary was provided.")[:2000]
    sources = []
    raw_sources = value.get("sources")
    if isinstance(raw_sources, list):
        for source in raw_sources[:5]:
            if not isinstance(source, dict):
                continue
            raw_url = str(source.get("url") or "")[:2000].strip()
            safe_url = ""
            try:
                parsed_url = urlsplit(raw_url)
                if (
                    parsed_url.scheme.lower() in {"http", "https"}
                    and parsed_url.hostname
                    and parsed_url.username is None
                    and parsed_url.password is None
                ):
                    safe_url = raw_url
            except ValueError:
                safe_url = ""
            sources.append({
                "title": str(source.get("title") or "Untitled source")[:300],
                "url": safe_url,
                # Keep an excerpt for auditability; it is untrusted and never used for code execution.
                "content": str(source.get("content") or "")[:1200],
            })
    retrieved_at = value.get("retrieved_at")
    try:
        if not isinstance(retrieved_at, str):
            raise ValueError("missing timestamp")
        parsed_timestamp = datetime.fromisoformat(retrieved_at.replace("Z", "+00:00"))
        if parsed_timestamp.tzinfo is None:
            parsed_timestamp = parsed_timestamp.replace(tzinfo=timezone.utc)
        retrieved_at = parsed_timestamp.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError):
        retrieved_at = datetime.now(timezone.utc).isoformat()
    return {
        "scenario_delay_days": delay,
        "provenance": provenance,
        "retrieved_at": retrieved_at[:80],
        "sources": sources,
        "summary": summary,
    }


SLA_GUARDRAIL_PCT = 70.0
SOLVENCY_GUARDRAIL_PCT = 95.0


def select_recommendation(results: list[dict]) -> tuple[dict, str]:
    """Select a feasible plan using the documented guardrail-first policy."""
    feasible = [result for result in results if result.get("feasible") is True]
    if not feasible:
        raise ValueError("Cannot select a recommendation without a feasible strategy.")

    def conservative_probability(result: dict, ci_key: str, successes_key: str, percentage_key: str) -> float:
        # Guardrails use the lower 95% Wilson bound, not a noisy point estimate.
        ci = result.get(ci_key)
        if isinstance(ci, dict) and isinstance(ci.get("lower"), (int, float)):
            return float(ci["lower"])
        runs = result.get("runs")
        successes = result.get(successes_key)
        if (
            isinstance(runs, int) and not isinstance(runs, bool) and runs > 0
            and isinstance(successes, int) and not isinstance(successes, bool)
            and 0 <= successes <= runs
        ):
            interval = wilson_interval(successes, runs)
            return float(interval["lower"])
        return float(result[percentage_key])

    def policy_metrics(result: dict) -> tuple[float, float]:
        return (
            conservative_probability(result, "sla_success_ci95", "sla_success_runs", "sla_success_probability"),
            conservative_probability(result, "solvency_ci95", "solvent_runs", "solvency_probability"),
        )

    eligible = [
        result for result in feasible
        if policy_metrics(result)[0] >= SLA_GUARDRAIL_PCT
        and policy_metrics(result)[1] >= SOLVENCY_GUARDRAIL_PCT
    ]
    if eligible:
        winner = max(eligible, key=lambda result: (
            result["expected_profit"], *policy_metrics(result)
        ))
        note = (
            f"Among options whose 95% Wilson lower bounds meet the {SLA_GUARDRAIL_PCT:.0f}% SLA-success and "
            f"{SOLVENCY_GUARDRAIL_PCT:.0f}% non-negative-cash guardrails, maximize expected operating profit."
        )
    else:
        winner = max(feasible, key=lambda result: (
            *policy_metrics(result), result["expected_profit"]
        ))
        note = (
            "No candidate met both confidence-bound guardrails; rank by the 95% Wilson lower bound for SLA success, "
            "then the non-negative-cash Wilson lower bound, then expected operating profit. This is a best-effort fallback."
        )
    return winner, note


def create_base_state(scenario_delay_days: int, disruption: bool) -> WorldState:
    delay = max(1, min(14, int(scenario_delay_days)))
    return WorldState(
        cash=4000.0 if disruption else 10000.0,
        inventory={"LAPTOP": SKU(qty=0, unit_cost=500.0, unit_price=1000.0)},
        suppliers={
            "SLOW_SUPPLIER": Supplier(id="SLOW_SUPPLIER", lead_time_days=delay, reliability=0.80),
            "FAST_SUPPLIER": Supplier(id="FAST_SUPPLIER", lead_time_days=2, reliability=0.98),
        },
        active_orders=[Order(
            id="VIP-001", sku="LAPTOP", qty=10, priority="high",
            created_tick=0, deadline_tick=4, penalty_per_day=500.0,
        )],
        customer_deposit_amount=2000.0,
        customer_deposit_acceptance_probability=0.80,
    )


@app.get("/api/health")
def health():
    return {"status": "ok", "service": "digital-shadow", "version": app.version}


@app.post("/api/scenario/draft")
def create_scenario_draft(req: ScenarioDraftRequest):
    """Extract a user-entered scenario into an editable, validated parameter draft."""
    draft, status = draft_scenario(req.description, req.research_query)
    return {
        "draft": draft,
        "integration": status,
        "notice": "Review every field. Missing numerical details are defaults, not facts about your business.",
    }


@app.post("/api/scenario/research")
def research_business_scenario(req: ScenarioResearchRequest):
    """Run targeted Tavily searches and extract top pages for a user-authored scenario."""
    return research_scenario(req.description, req.research_query, req.max_sources)


@app.post("/api/scenario/simulate")
def simulate_business_scenario(req: ScenarioSimulationRequest):
    """Validate a scenario, compare actions, persist the result and return its evidence trail."""
    payload = run_custom_simulation(req.scenario, req.evidence)
    try:
        serialized = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Scenario produced a non-finite or unserializable result.") from exc
    with db() as conn:
        conn.execute(
            "INSERT INTO simulations(id, created_at, payload) VALUES(?,?,?)",
            (payload["simulation_id"], datetime.now(timezone.utc).isoformat(), serialized),
        )
    return payload


@app.get("/api/simulate")
def run_simulation(
    disruption: bool = False,
    num_runs: int = Query(default=1000, ge=100, le=1000),
):
    reality = _normalize_reality(fetch_external_reality("recent global shipping and port delays"))
    scenario_delay_days = reality["scenario_delay_days"]
    state = create_base_state(scenario_delay_days, disruption)
    crisis_desc = (
        f"VIP order for 10 laptops due Day 4; starting cash ${state.cash:.2f}; "
        "unit cost $500 per laptop; cancellation penalty $500 per late day. "
        f"Budget crisis is {'active' if disruption else 'inactive'}."
    )
    candidates, planner_status = generate_strategies_with_status(crisis_desc, reality["summary"], state)
    results = []
    for item in candidates:
        action, args = item.get("action"), item.get("args", [])
        result = simulate_strategy(state, item["name"], action, args, num_runs=num_runs)
        result.update({"action": action, "args": args, "strategy_id": str(uuid.uuid4())})
        results.append(result)

    try:
        winner, policy_note = select_recommendation(results)
    except ValueError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    summary = "\n".join(
        f"{result['name']}: feasible={result['feasible']}, "
        f"expected profit={result['expected_profit']}, "
        f"SLA success={result['sla_success_probability']}%, "
        f"non-negative ending cash={result['solvency_probability']}%, "
        f"5th-percentile cash=${result['p05_cash']}"
        for result in results
    )
    analysis, analyst_status = analyze_results_with_status(crisis_desc + " " + policy_note, summary, winner["name"])
    simulation_id = str(uuid.uuid4())
    decision_sensitivity = (
        find_minimum_advance_acceptance(
            state,
            num_runs=num_runs,
            sla_guardrail_pct=SLA_GUARDRAIL_PCT,
            cash_guardrail_pct=SOLVENCY_GUARDRAIL_PCT,
        )
        if disruption else None
    )
    payload = {
        "simulation_id": simulation_id,
        "decision_sensitivity": decision_sensitivity,
        "world_state": state.model_dump(mode="json"),
        "initial_state": {
            "cash": state.cash,
            "vip_order_due": 4,
            "scenario_slow_supplier_lead_time_days": scenario_delay_days,
            "is_disrupted": disruption,
        },
        "reality": reality,
        "assumptions": {
            "num_runs": num_runs,
            "simulation_horizon_days": 7,
            "customer_deposit_amount": state.customer_deposit_amount,
            "customer_deposit_acceptance_probability": state.customer_deposit_acceptance_probability,
            "guardrail_statistical_rule": (
                "The 70% SLA and 95% non-negative-cash guardrails use the lower bound of a 95% Wilson score interval; "
                "the selected probability estimates are empirical Monte Carlo frequencies, not guarantees."
            ),
            "supplier_reliability_definition": (
                "Probability a delivery attempt succeeds. Failed attempts may be retried; this is not a guaranteed on-time percentage."
            ),
            "shipment_loss_rule": "On a failed delivery attempt, there is a 10% conditional chance of permanent non-refundable loss; otherwise it is delayed and retried.",
            "decision_policy": policy_note,
            "sla_guardrail_pct": 70.0,
            "solvency_guardrail_pct": 95.0,
            "late_penalty": 500.0,
            "penalty_rule": "Order cancels at first tick past the deadline; penalty is $500 per elapsed late day at cancellation.",
            "deadline_rule": "Day 4 is inclusive; a delivery fulfilled on Day 4 meets the deadline.",
            "accounting_rule": "Customer advances affect cash but are liabilities until applied to a fulfilled sale or refunded; unsold inventory remains an asset, not a COGS expense.",
            "scenario_signal_rule": "General shipping news only informs an explicitly illustrative slow-supplier stress-case lead time; it is not a supplier-specific ETA or calibrated forecast.",
        },
        "strategies": results,
        "best_strategy": winner["name"],
        "best_strategy_data": winner,
        "analysis": analysis,
        "integrations": {
            "planner": planner_status,
            "analyst": analyst_status,
            "external_evidence": {
                "provider": "Tavily + Nebius Token Factory",
                "status": reality["provenance"],
                "source_count": len(reality["sources"]),
            },
        },
    }
    try:
        serialized = json.dumps(payload, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=500, detail="Simulation produced a non-finite or unserializable result.") from exc
    with db() as conn:
        conn.execute(
            "INSERT INTO simulations(id, created_at, payload) VALUES(?,?,?)",
            (simulation_id, datetime.now(timezone.utc).isoformat(), serialized),
        )
    return payload


@app.post("/api/execute")
def execute_strategy(req: ExecuteRequest):
    with db() as conn:
        # BEGIN IMMEDIATE serializes approvals so two simultaneous requests cannot both execute.
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT payload, executed FROM simulations WHERE id=?", (req.simulation_id,)
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unknown simulation_id.")
        if row["executed"]:
            raise HTTPException(status_code=409, detail="This simulation has already been executed.")

        payload = json.loads(row["payload"])
        selected = next(
            (strategy for strategy in payload["strategies"] if strategy["strategy_id"] == req.strategy_id),
            None,
        )
        if selected is None:
            raise HTTPException(status_code=400, detail="Strategy ID does not belong to this simulation.")
        if not selected.get("feasible"):
            raise HTTPException(status_code=400, detail="Cannot execute an infeasible strategy.")

        state = WorldState.model_validate(payload["world_state"])
        audit = [
            f"[Tick 0] Saved scenario restored; starting cash ${state.cash:.2f}.",
            f"[Approval] {selected['name']}. Fixed-seed demo run; no supplier was contacted and no customer was contacted.",
        ]
        action, args = selected.get("action"), selected.get("args", [])
        valid, reason = validate_action(state, action, args)
        if not valid:
            raise HTTPException(status_code=409, detail=f"Action rejected: {reason}")

        state = apply_strategy(state, action, args, random.Random(2026))
        if any(line.startswith("REJECTED:") for line in state.action_log):
            raise HTTPException(status_code=409, detail="Action was rejected by the simulation engine.")
        audit.extend(state.action_log)
        state = advance_time(state, ticks=7, seed=99)
        outcome = evaluate_scenario(state)
        audit.append(f"[Tick 7] Simulated SLA compliance: {outcome['sla_compliance_pct']}%.")
        audit.append(
            f"[Tick 7] Final cash ${outcome['final_cash']:.2f}; "
            f"operating profit ${outcome['operating_profit']:.2f}."
        )
        execution = {
            "status": "simulated_success",
            "audit_log": audit,
            "metrics": outcome,
            "note": "Simulated outcome only. Monte Carlo expectations are not a guarantee of this single seeded run.",
        }
        conn.execute(
            "UPDATE simulations SET executed=1, execution_payload=? WHERE id=?",
            (json.dumps(execution, allow_nan=False, separators=(",", ":")), req.simulation_id),
        )
        return execution


# In a container/release build the Vite app is served by the same FastAPI origin.
# During local development, run Vite separately and leave frontend/dist absent.
_FRONTEND_DIST = Path(os.getenv("FRONTEND_DIST", str(Path(__file__).resolve().parent / "frontend" / "dist")))
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
