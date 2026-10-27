# Digital Shadow — evidence-grounded business decision simulation

Digital Shadow is an operational decision workbench for small distributors and retailers. Describe a supplier, logistics, or cash-flow disruption in plain language; review the extracted business facts; research current context with Tavily; edit the assumptions; and simulate competing responses before approving a **simulated** plan. The default laptop scenario remains available as a reference demo, but Scenario Studio is the main entry point.

The Python engine is the source of truth for feasibility, Monte Carlo outcomes, accounting, and the recommendation rule. NVIDIA Nemotron can propose candidates and explain the selected outcome through Nebius Token Factory; it does **not** calculate the scores. Tavily can provide current general shipping-news context, but general news is never presented as verified evidence about a named supplier. The 95% Wilson interval describes Monte Carlo sampling uncertainty conditional on the chosen simulation assumptions; it does not prove that those assumptions match real supplier behavior.

## What is in this repo

- A React + Vite Scenario Studio with a natural-language intake, editable business parameters, evidence panel, strategy comparison, tipping-point view, and Markdown decision-brief export; the classic demo remains available.
- A FastAPI API with draft, research, simulation, health, and one-time simulation-bound approval endpoints, plus SQLite audit persistence.
- A seeded Monte Carlo engine, Wilson confidence intervals for success/liquidity guardrails, worst-observed and p05 cash reporting, explicitly defined accounting, an audit trail, and tests that run without calling external services.
- Scenario-specific tipping-point analysis across alternate-supplier lead times and minimum starting cash for the primary-supplier plan to meet the configured non-negative-ending-cash confidence guardrail.
- Distinct per-unit supplier expedite/handling premiums allow the faster supplier to cost more than the alternate; premiums affect affordability and operating profit while remaining separate from inventory asset cost.
- An evidence-to-assumption map that displays what retrieved reports may inform, what they do not establish, and which numerical fields remain user-entered assumptions/defaults.
- An optional Nebius Token Factory/NVIDIA Nemotron integration and an optional Tavily search integration.
- Demo mode when API keys are absent. Fallback estimates are labelled as assumptions, not live evidence.

## The user-defined workflow

1. Enter a business problem in Scenario Studio and choose **Draft scenario**. With a Nebius Token Factory key, Nemotron can propose a structured draft; without it, a conservative local parser supplies editable fields and clearly disclosed defaults.
2. Review the extracted cash, item, stock, costs, prices, quantity, deadline, suppliers, reliability assumptions, objectives, and risk limits. Do not treat an auto-filled default as a fact.
3. Choose **Research scenario**. Tavily runs three searches tailored to status, operational impact, and mitigation. It then attempts page extraction for high-relevance results. Source URLs, snippets/extracted text, dates and relevance scores are surfaced. Retrieval can be partial or unavailable.
4. Read the evidence-to-assumption trace. News may inform what to investigate, but it does not silently change model numbers or prove a named supplier's actual ETA/reliability.
5. Run the scenario. The Python engine validates actions and compares feasible options using seeded Monte Carlo runs, Wilson intervals, a cash-risk guardrail, the user-selected objective, and an alternate lead-time sensitivity sweep. The chosen strategy is a conditional recommendation, not a guarantee.
6. Export the decision brief or use the one-time **simulated approval** to produce an audit entry. No real supplier/customer is contacted and no purchase or payment is made.

## What the product models

The current scope is deliberately focused on operational procurement and fulfilment disruptions with cash, inventory, supplier lead-time/reliability, order deadlines, and optional customer advances. It is configurable beyond the original 10-laptop demo, but it is not yet a universal model of every business process. If the natural-language parser cannot identify a field confidently, inspect and edit it before running the simulation.

## Quick start

### Backend

Python 3.11+ is recommended. From this repository's root:

```bash
python -m venv .venv
# macOS/Linux
source .venv/bin/activate
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
cp .env.example .env
pytest -q
uvicorn api:app --reload --port 8000
```

Health check: <http://localhost:8000/api/health>

### Frontend

Use Node.js 20.19+ (or a newer supported LTS release). In another terminal:

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Open <http://localhost:5173>. The production build is generated by `npm run build` inside `frontend/`.

### Optional live integrations

Put credentials in the root `.env` file. Never commit or share that file.

```dotenv
NEBIUS_API_KEY=your_token_factory_key
TAVILY_API_KEY=your_tavily_key
NEBIUS_BASE_URL=https://api.tokenfactory.us-central1.nebius.com/v1/
NEBIUS_MODEL_ID=nvidia/Nemotron-3-Ultra-550b-a55b
FRONTEND_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
DIGITAL_SHADOW_DB=digital_shadow.sqlite3
```

The actual availability of the requested model is subject to the Token Factory account's model catalog and access settings. You must test a live request with your own key before claiming a live inference run in a submission video. Without credentials, the service is designed to run in labelled demo mode. The dashboard shows whether each Nemotron and external-evidence path actually succeeded or used a fallback.

To test connectivity before recording a demo, run `python check_integrations.py` from the repository root. This makes one Nebius inference request and one Tavily search request and may consume provider credits. It reports statuses only; it never prints credential values.

## Public judging deployment (Render)

The repository includes `render.yaml` and a multi-stage `Dockerfile`; one Render Web Service serves both the built React app and FastAPI on the same origin. In Render, create a Blueprint from the GitHub repository and set `NEBIUS_API_KEY`, `TAVILY_API_KEY`, and `DEMO_ACCESS_PASSWORD` as private environment variables. Never put provider keys in a `VITE_*` variable or frontend file. Generate a long, unique access code (for example `openssl rand -hex 24`) and distribute it only to intended evaluators. The frontend asks for it when the first protected API request receives HTTP 401; it is kept in that browser tab's session storage and sent in `X-Demo-Access` headers.

When `DEMO_ACCESS_PASSWORD` is set, all API endpoints except `/api/health` require that code. The server also applies lightweight in-memory per-IP limits: 6 research calls/hour, 12 scenario-draft calls/hour, 18 scenario simulations/hour, 6 classic-demo simulations/hour, and 12 simulated approvals/hour. Service-wide hourly caps further limit spend exposure to 8 researches, 20 drafts, 20 custom simulations, 8 classic simulations, and 20 simulated approvals. These are demo safeguards, not a hardened abuse-prevention service: limits reset on restart, may be bypassed by distributed clients, and do not replace provider-side quotas/billing alerts. Keep the judging code private where possible, monitor usage, and rotate/revoke the provider keys after evaluation if needed.

The current Render Blueprint uses a free instance and stores SQLite in `/tmp`. Free instances may spin down after inactivity and local filesystem writes are ephemeral, so wake-up latency is possible and audit history is not durable across restarts. This setup is for a hackathon demo, not production customer data. See `PUBLIC_DEMO_SECURITY.md` before exposing it.

### Render deployment steps

1. Push the complete project root to a public GitHub repository. Verify `.env`, `.env.local`, API keys, `node_modules`, `.venv`, and SQLite files are not tracked.
2. In Render, select **New → Blueprint**, connect the repository, and let it read `render.yaml`. Review the proposed `digital-shadow` web service.
3. Supply `NEBIUS_API_KEY`, `TAVILY_API_KEY`, and a newly generated `DEMO_ACCESS_PASSWORD` when requested. If not prompted, open the service's **Environment** tab and add them there. Keep all three as secret environment variables.
4. Deploy. Wait for the build to complete, then open `https://<your-service>.onrender.com/api/health`. Expect `{"status":"ok","service":"digital-shadow","version":"2.0.0"}`.
5. Open the root service URL, try one draft, one Tavily research run, one simulation, and one simulated approval. On the first API action, enter the access code. In the audit panel, confirm provider statuses are real successes rather than fallbacks.
6. If the `Dockerfile` build fails at `npm ci` or `npm run build`, fix that before submitting; do not treat Python-only test success as a production frontend build.
7. Keep a tested local fallback and a copy of the final three-minute video. To end the public exposure window, remove `NEBIUS_API_KEY` and `TAVILY_API_KEY` or suspend the service; rotate keys if you suspect they were used unexpectedly.

## Custom scenario studio

The default landing view opens the Scenario Studio. Describe a disruption in plain language, use **Interpret into editable fields** (Nebius/Nemotron when configured, deterministic extraction otherwise), review all assumptions, research the scenario with Tavily, and run the Monte Carlo comparison. The source ledger shows retrieved content and safe links. Web evidence never silently changes supplier reliability, cash, pricing, or lead-time inputs. The funding diagnosis explicitly flags when none of the modeled procurement choices can be funded, and suggests next steps outside the simulator rather than pretending a plan is feasible. Results can be exported as a Markdown decision brief. **Classic demo** retains the original fixed laptop scenario.

## Scenario and exact model assumptions

| Quantity | Value | Meaning |
|---|---:|---|
| Baseline starting cash | $10,000 | Hypothetical initial cash |
| Budget-shock starting cash | $4,000 | Hypothetical crisis state |
| Order quantity | 10 laptops | One VIP order |
| Unit purchase cost | $500 | $5,000 procurement cash outflow |
| Unit sale price | $1,000 | $10,000 sale revenue if fulfilled |
| Deadline | Day 4 inclusive | Fulfilment on Day 4 counts as on time |
| Customer advance | $2,000 | Hypothetical funding option, not a real payment |
| Advance acceptance | 80% | Uncalibrated scenario assumption |
| Late cancellation penalty | $500 per elapsed late day at cancellation | The default loop cancels on Day 5, so the usual charge is $500 |
| Horizon | 7 days | Outcomes after the horizon are not forecast |
| Candidate guardrails | 70% SLA success and 95% non-negative-cash probability | Uses lower bounds of 95% Wilson intervals; if none passes, use the declared best-effort ranking |
| Supplier fees | $0 per unit by default for both suppliers | Each supplier can have a different incremental expedite/handling fee; it is paid upfront and expensed immediately. |

**Shipment assumptions:** supplier reliability is the probability that an individual delivery attempt succeeds, not the probability of on-time arrival. A failed attempt has a 10% conditional chance of permanent loss; otherwise the shipment is delayed and retried. These parameters are illustrative rather than calibrated logistics probabilities. General shipping news is context only and is not a supplier-specific ETA.

**Accounting definitions:**

- Operating profit = recognized revenue − cost of goods sold (COGS) − cancellation penalties − permanent shipment losses − supplier premiums/fees.
- Customer advances affect cash immediately, remain outstanding liabilities until applied to a fulfilled order or refunded, and are never counted as revenue by themselves.
- Purchase of unsold stock moves the base unit cost from cash into an inventory asset; it is not an operating expense until the stock is sold or written off. Configured supplier expedite/handling premiums are modeled separately as upfront operating expenses.
- Inventory asset value is validated against on-hand and in-transit stock. Final cash, operating profit, remaining inventory assets, and solvency are separate measures and should not be conflated.
- Reconciliation invariant: change in (cash + inventory assets − outstanding customer advances) equals operating profit for the modeled transitions; automated seeded tests exercise this across both scenarios, accepted/refused advances, delays, and losses.
- `sla_success_probability` is the observed share of Monte Carlo runs in which all modeled orders are fulfilled by their deadline. The UI also reports a 95% Wilson interval. Recommendation guardrails use the interval lower bound, not just the observed percentage. These are scenario estimates, not guarantees.
- `solvency_probability` means the share of runs with non-negative ending cash; it is a narrow cash-liquidity proxy, not a full balance-sheet solvency assessment. Its 95% Wilson lower bound is used by the recommendation policy.
- Both supplier lead times, reliability assumptions, and incremental fees are illustrative scenario inputs unless the operator separately verifies them. When live Tavily search succeeds, general shipping news may inform which stress cases to test, but it is not the actual or predicted ETA of a named supplier.
- Cash p05 uses the **nearest-rank percentile**: sort the sample and select rank `ceil(0.05 × N)` (one-indexed). This is a sample percentile, not a guarantee or confidence interval.

## Architecture

1. **Tavily retrieval (optional):** the custom studio launches three scenario-specific search angles, deduplicates the results, preserves timestamps and relevance metadata, and extracts the top pages where possible.
2. **Nemotron planner (optional):** proposes up to three actions. The backend validates every candidate against scenario constraints; invalid JSON and invalid actions fall back to deterministic candidates. Asking for a customer advance is rejected as unnecessary when existing cash already covers procurement.
3. **Python simulation engine:** executes seeded Monte Carlo runs, validates cash and demand constraints, simulates delivery/late cancellation, and calculates cash, profit, SLA probability, solvency probability, and a nearest-rank lower cash percentile.
4. **Decision policy:** among options whose 95% Wilson lower bounds meet 70% SLA success and 95% non-negative-cash probability, select the highest expected operating profit. If no option qualifies, rank by the lower bound for SLA success, then non-negative-cash probability, then expected operating profit. The exact rule appears in the returned assumptions.
5. **Decision tipping points:** a deterministic lead-time sweep estimates the maximum alternate-supplier lead time meeting the delivery confidence guardrail; a fixed-seed cash sweep estimates the starting-cash level required for the primary supplier direct-purchase plan to meet the non-negative-ending-cash guardrail. Both are conditional on the model, and cash does not solve a delivery problem.
6. **Nemotron analyst (optional):** explains the numerical selection. It cannot override Python's choice.
7. **SQLite approval:** saves the scenario snapshot. `/api/execute` requires a strategy ID belonging to that exact snapshot, serializes concurrent approvals, and allows one approval. It then runs a fixed-seed simulation for the audit trail.

## Verification

```bash
pytest -q
python -m compileall -q .
python main.py
cd frontend && npm ci && npm run build
```

The Python suite includes seeded balance-sheet/profit reconciliation tests across many delivery and negotiation outcomes. Provider integration tests use mocks; they do not prove that live credentials have access to the configured model or that Tavily/Nebius is reachable from your network. Before tagging or submitting, run `npm ci` and `npm run build` from `frontend/` on a network-connected machine, then verify one live Nebius inference request and Tavily retrieval with valid credentials. Accurately disclose whether the demo video uses live inference or the demo fallback. See `SUBMISSION_CHECKLIST.md` for release gates and `DEMO_SCRIPT.md` for a timed, honest three-minute judge walkthrough.

## Scope and limitations

- A prototype for operational procurement/fulfilment stress tests and a pair of hypothetical suppliers; not an ERP, live supplier integration, or universal business simulator. Supplier per-unit premiums are modeled as upfront operating expenses, not part of inventory cost basis.
- No real supplier/customer messages or purchases are made by approval.
- Scenario probabilities and prices are demonstration assumptions, not professional logistics or financial advice.
- SQLite is suitable for a single-instance demo. A public multi-user deployment needs stronger authentication, durable/distributed rate limiting, privacy/retention policies, operational monitoring, and a managed database. The optional demo gate is only a hackathon safeguard.
- A passing test suite verifies only the behaviors covered by tests. `SUBMISSION_CHECKLIST.md` identifies remaining live-provider, UI, deployment, and competition requirements.

## License

MIT; see `LICENSE`.
