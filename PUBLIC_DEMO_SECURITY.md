# Public demo security and credit protection

## Before exposing the app

- Keep `NEBIUS_API_KEY` and `TAVILY_API_KEY` only in the Render service's server-side Environment settings. Never set provider credentials in `VITE_*`, frontend source, screenshots, videos, or a public repository.
- Set a strong unique `DEMO_ACCESS_PASSWORD` as a private Render environment variable. On a local machine, generate a value with `openssl rand -hex 24`; do not commit the generated value.
- In the protected release, `/api/health` remains public for the hosting health check. Other `/api/*` routes require `X-Demo-Access`, supplied by the frontend after asking the evaluator for the code. The code is stored in `sessionStorage` for that browser session, not embedded in the JS bundle.
- Protected cost-bearing endpoints have lightweight in-memory per-IP quotas: scenario research 6/hour; scenario draft 12/hour; custom simulation 18/hour; classic simulation 6/hour; simulated approval 12/hour. There are also service-wide hourly caps of 8 research calls, 20 drafts, 20 custom simulations, 8 classic simulations, and 20 simulated approvals.
- These safeguards reduce casual/unintended usage; they do not guarantee zero credit use. Shared codes can spread, clients can use different IP addresses, and in-memory counters reset on service restart. Keep provider-side budget/usage alerts or quotas where available, check usage during evaluation, and remove the provider keys or suspend the service afterward. Rotate keys if any exposure is suspected.

## Verify the gate after deploy

1. Open `https://YOUR-SERVICE.onrender.com/api/health`; it should return a small JSON health response.
2. Try `https://YOUR-SERVICE.onrender.com/api/scenario/research` directly without the header; it should return HTTP 405 for GET because the route is POST-only. To verify the access gate, use a POST request without `X-Demo-Access`; expect HTTP 401 with `Demo access code required or incorrect.`
3. Open the app and click an API action. The browser should prompt for the demo access code on the first HTTP 401. Enter it; the action should proceed. The next API actions in the same tab should reuse the session code.
4. A request beyond the configured endpoint quota should return HTTP 429 with a `Retry-After` header. Do not intentionally consume the Tavily quota just to test this in a live service; the automated tests cover it.

## End evaluation safely

- Remove `NEBIUS_API_KEY` and `TAVILY_API_KEY` from the Render service and redeploy, or suspend/delete the service if no longer needed.
- If unexpected provider usage appears, revoke the old keys in the provider dashboard and create replacements.
- Remember that Render's free service can spin down and its default filesystem is ephemeral. This release places SQLite at `/tmp`, so audit records are not durable across restarts.
