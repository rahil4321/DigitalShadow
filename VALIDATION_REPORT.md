# Digital Shadow — validation report

Updated for the secured judging-demo release on October 27, 2026. This report lists checks run in the available build environment; it does not replace the user's final live-provider, frontend-build, browser, and deployment checks.

## Passed

- `python -m pytest -q`: **102 passed**. Coverage includes scenario validation/drafting, strategy feasibility/scoring, accounting invariants, API behavior, evidence sanitization, supplier premiums, funding-gap diagnosis, decision sensitivity, and the public demo gate/rate limits.
- `python -m compileall -q .`: passed.
- `python main.py`: passed in the previous source validation; it emits baseline and budget-crisis outcome summaries.
- JSX syntax parsing passed for the original frontend in the prior source validation. The access-code wrapper is new and `node --check frontend/src/apiClient.js` passes.
- Public-demo security tests verify protected routes return HTTP 401 without/wrong access code, valid access reaches the route, CORS preflight is not blocked, the per-IP research quota returns HTTP 429, and a service-wide research cap works across different forwarded IPs.
- Release hygiene: local SQLite run data, `.env` credentials, Python/Node environments, caches, and compiled frontend output are excluded from the ZIP.

## Not verified in this environment

- `npm run build` could not run because the checked-out `frontend/node_modules` directory is absent (`vite: not found`). The clean install/build must be run on a network-connected machine with Node 20.19+ or supported Node 22 before deployment. The Dockerfile installs frontend dependencies with `npm ci` during a remote Render build.
- Live Nebius Token Factory/Nemotron and Tavily provider calls with the user's credentials have not been re-run as part of this secured packaging pass. Run `python check_integrations.py` locally if needed; it sends real provider requests and can consume credits.
- A public Render deployment and final submission video have not been completed by this build process.

## Security notes

- Configure `NEBIUS_API_KEY`, `TAVILY_API_KEY`, and `DEMO_ACCESS_PASSWORD` in Render's server-side environment settings only; never set provider keys in any `VITE_*` variable or frontend source.
- With `DEMO_ACCESS_PASSWORD` configured, only `/api/health` remains publicly accessible without the code. Other `/api/*` endpoints require `X-Demo-Access`.
- In-memory demo limits are a lightweight cost guard, not production-grade auth or distributed rate limiting. They reset on restart and do not replace provider budget alerts/quotas. Disable/remove provider keys or suspend the service after evaluation.
- The SQLite location is `/tmp/digital_shadow.sqlite3` on Render. Audit history is ephemeral and may reset on restart/redeploy. This release is intended for a single-instance hackathon demo, not production customer data.
