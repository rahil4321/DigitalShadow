# Digital Shadow — installation and test guide

This repository is self-contained: the Python API/simulator and the Vite/React dashboard are both included.

## 1. Prerequisites

- Python 3.11 or newer (the project has been tested in Python 3.13 in this build environment).
- Node.js 20.19 or newer (or a newer supported LTS release) and npm; Vite 8 requires a recent Node 20/22 build.
- API keys are optional for demo mode. For a live run, configure Nebius Token Factory and Tavily credentials as described below.

## 2. Backend

From the repository root:

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

Open `http://localhost:8000/api/health`; the response should contain `"status":"ok"`.

`NEBIUS_API_KEY` and `TAVILY_API_KEY` can remain blank for demo mode. To test live model use, supply your own keys in `.env`. Never commit `.env` or expose its contents in a screenshot/video.

## 3. Frontend

In a second terminal:

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Open `http://localhost:5173`. To build the static production bundle, run `npm run build` from `frontend/`; output is written to `frontend/dist/`.

If the API is hosted elsewhere, set `VITE_API_URL` in `frontend/.env.local` to the backend base URL, with no `/api` suffix. Configure `FRONTEND_ORIGINS` in the backend environment to the exact frontend origin(s).

## 4. Additional verification

```bash
# Python regression suite
pytest -q

# CLI simulation (prints both baseline and budget-crisis outcomes)
python main.py

# Production frontend build
cd frontend && npm run build
```

## 5. Model and accounting contract

- The Python engine validates every proposed action and owns all numeric scoring. Nemotron proposes candidate strategies and may explain the selected outcome; it does not calculate the result.
- The baseline starts with $10,000; the stress scenario starts with $4,000. Ten laptops cost $5,000 total and sell for $10,000 total; the order deadline is inclusive through Day 4.
- A hypothetical $2,000 customer advance has a scenario-assumed 80% acceptance probability. Advances affect cash but are not recognized as revenue; they are applied on a fulfilled sale or refunded after cancellation.
- Operating profit is recognized revenue minus COGS, cancellation penalties, permanent shipment losses, and supplier fees. Base unsold stock remains an inventory asset; a configured supplier premium is an upfront operating expense kept separate from the base inventory cost basis.
- Supplier reliability is the probability of success for an individual delivery attempt. A failed attempt has a 10% conditional chance of permanent loss; otherwise the shipment is delayed and retried. It is not a calibrated supplier forecast.
- Approval restores the saved scenario and runs one deterministic demonstration. **No supplier or customer is contacted and no real purchase is placed.**

See `README.md` and `SUBMISSION_CHECKLIST.md` for architecture and remaining event/submission checks.

Supplier premium input fields are per-unit fees. They let the scenario test whether a faster/high-fee supplier still passes the delivery guardrail and whether its incremental fee is justified by the modeled outcomes. The cash-reserve tipping point is a simulation-conditioned threshold for the primary supplier plan, not a lender or financial-advice recommendation.
