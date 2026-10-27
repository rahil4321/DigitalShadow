# Digital Shadow — submission readiness checklist

Do not mark an item complete until personally verified against the final source and running release candidate.

## Product and live integration

- [ ] Configure valid Nebius Token Factory and Tavily keys in the backend environment only; keep `.env` out of source control and the ZIP.
- [ ] Run `python check_integrations.py`; verify a successful live Nebius inference and Tavily search with returned source URLs.
- [ ] Test the live Nemotron scenario-draft path, strategy planner path and analyst explanation path; confirm the UI status reflects actual outcomes.
- [ ] Test Tavily search and extraction, partial retrieval, no-result behavior, malformed links, and provider timeouts. Ensure fallback is explicitly labelled.
- [ ] Enter a novel scenario in Scenario Studio; inspect every extracted/default value before running it.
- [ ] Run a normal business scenario, a cash-constrained scenario, and a partial-inventory scenario. Confirm that infeasible or unfunded actions are not recommended.
- [ ] Confirm evidence links can be opened, evidence is mapped to its limits, and numeric scenario inputs are not silently changed by web content.
- [ ] Confirm guardrail failures are surfaced as unresolved risk; strategy ranking must not imply an unsafe choice is safe.
- [ ] Inspect alternate lead-time sensitivity and export a decision brief.
- [ ] Run `pytest -q`, `python -m compileall -q .`, and `python main.py`; retain actual output.
- [ ] From `frontend/`, run `npm ci` and `npm run build` using the checked-in lockfile on a supported Node release.
- [ ] Test the finished UI at desktop and mobile sizes; verify keyboard form inputs, source links, status badges and report export.
- [ ] Confirm simulated approval is bound to the selected strategy and saved scenario, cannot be repeated, and sends no external action.

## Deployment and judging access

- [ ] Build and run the Docker image; confirm the frontend loads from the same origin and `/api/health` returns OK.
- [ ] Deploy a working demo and test the root page after reload, custom scenario, research, simulation and health route.
- [ ] Set server-side `DEMO_ACCESS_PASSWORD` in Render and share the code only with intended evaluators. Verify protected API requests return 401 without it.
- [ ] Verify per-IP demo limits (research 6/hour, draft 12/hour, custom simulation 18/hour, classic simulation 6/hour). Service-wide caps also apply, but these are in-memory safeguards only; configure provider quotas and monitor usage too.
- [ ] Keep credentials in server-side deployment environment variables; never use `VITE_*` for provider keys. Confirm `.env`, `.env.local`, `.sqlite3`, `.venv`, and `node_modules` are not in the public repository.
- [ ] Run a secret scan on tracked files and the final ZIP. Exclude `.env`, `.venv`, `node_modules`, frontend build outputs, caches and local SQLite databases.
- [ ] Publish a public source repository with MIT license and setup instructions.
- [ ] Record a public demonstration under three minutes following `DEMO_SCRIPT.md`; show live NVIDIA/Nebius inference only when it is genuinely working in the recording.
- [ ] Explain the business problem, why evidence-grounded simulation differs from generic AI advice, architecture, and assumptions/limitations.
- [ ] If required, document significant work completed during the hackathon period and accurately complete sponsor/tool feedback forms.
- [ ] Re-check event rules, deadline, track and award submission requirements on the official page before final submission.

## Current scope and limitations

Digital Shadow is a configurable prototype for procurement/fulfilment disruption stress tests with cash, inventory, suppliers, lead times, delivery-attempt reliability, deadlines and optional customer advances. It is not yet an ERP, a calibrated logistics forecast, a universal business-process simulator, or an integration that contacts suppliers/customers. Tavily evidence provides external context; it does not automatically establish a supplier-specific ETA or reliability. Monte Carlo probabilities are conditional on the values supplied by the operator. The current SQLite deployment configuration and in-memory demo rate limits are intended for a single-instance judging demo; they are not production-hardened user authentication, persistent audit storage, or distributed abuse protection.
