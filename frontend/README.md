# Digital Shadow frontend

React + Vite interface. The default view is **Scenario Studio**; the original fixed baseline/budget-shock demo remains accessible from the navigation.

## Local development

1. Start the Python API from the repository root: `uvicorn api:app --reload --port 8000`.
2. In this directory, run `cp .env.example .env.local` (optional if using the default API URL), `npm ci`, then `npm run dev`.
3. Open `http://localhost:5173`.

For local dev, `VITE_API_URL` defaults to `http://localhost:8000`. In a same-origin production container, leave it blank so the frontend calls `/api` on the current origin. Do not put provider API keys in frontend env variables; secrets belong only in the backend environment.

`npm run build` produces `dist/`; the root FastAPI app serves that directory when it exists or when `FRONTEND_DIST` points to it.
