# Release notes — secured judging demo

## October 27, 2026

- Added optional server-side `DEMO_ACCESS_PASSWORD` protection for all `/api/*` endpoints except `/api/health`.
- Added a frontend request helper that asks for the access code after HTTP 401 and keeps it in browser `sessionStorage`; the code is not compiled into the public JavaScript.
- Added lightweight per-IP and service-wide in-memory quotas for provider/cost-bearing endpoints.
- Allowed `X-Demo-Access` in CORS request headers and ensured OPTIONS preflight is not blocked by the demo gate.
- Added test coverage for gate behavior, valid access, per-IP caps, service-wide caps, and CORS preflight.
- Added `PUBLIC_DEMO_SECURITY.md` and deployment guidance in `README.md`.
- Removed the local SQLite database from the release archive to avoid including local audit history.
- Validation: **102 Python tests passed**, Python compilation passed, and `node --check frontend/src/apiClient.js` passed. Full Vite build is still unverified because frontend dependencies are not installed in this environment; deploy only after the clean Docker build succeeds.
