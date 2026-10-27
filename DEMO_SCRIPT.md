# Digital Shadow — three-minute judge demo

## Before recording

1. Install backend dependencies: `python -m pip install -r requirements.txt`.
2. Add your own `NEBIUS_API_KEY` and `TAVILY_API_KEY` to the root `.env` file. Never show or commit the file.
3. Run `python check_integrations.py` and resolve problems before recording. This makes billable live requests.
4. Terminal 1: `uvicorn api:app --reload --port 8000`.
5. Terminal 2: `cd frontend && npm ci && npm run dev`.
6. Open `http://localhost:5173` and confirm scenario drafting, Tavily research, simulation, links, and status badges work. Prepare a saved scenario description, but do not fake or edit provider status.

If the model or retrieval path falls back, disclose that and either fix it before recording or explicitly record a fallback/demo build. Do not claim a live integration if the status says otherwise.

## Timed sequence

### 0:00–0:25 — User-defined problem

Start in Scenario Studio. Explain: “A business describes the disruption in plain language. Digital Shadow converts that into an editable model; it does not silently make up missing facts.” Keep the sample small-distributor scenario or use a realistic local scenario you can explain.

### 0:25–0:55 — Live Tavily evidence

Click **Research with Tavily**. Open the query plan and at least one actual source. Point out the publication date when available, extracted-versus-snippet status, relevance score, and the clear evidence boundary. Say what the sources actually support; do not claim general shipping news proves a named supplier ETA.

### 0:55–1:20 — Confirm assumptions

Click **Interpret into editable fields** if the narrative needs parsing, then inspect cash, inventory, economics, lead times, per-attempt reliability assumptions, deadline, risk thresholds and objective. Change at least one value visibly. Point out the Nemotron/local-draft status honestly.

### 1:20–2:10 — Compare simulated futures

Click **Simulate and compare actions**. Show the recommended strategy, expected operating profit, deadline success with its 95% Wilson interval, non-negative ending cash, p05 cash and worst observed cash. Explain that Python—not the language model—computes the outcomes and applies the decision policy. Show the funding diagnosis and strategy comparison table.

### 2:10–2:35 — Change the decision

Change the alternate supplier lead time or cash reserve, rerun, and show how the policy or outcome changes. Use the lead-time tipping-point panel to explain when the alternate supplier stops meeting the chosen SLA guardrail. If no strategy passes a guardrail, say so clearly.

### 2:35–2:55 — Decision brief and audit trail

Export the Markdown decision brief. Record the simulated approval and show the audit trail. Make it explicit that this does not contact suppliers or customers and does not place a real order.

### Before recording: live integration check

Run `python check_integrations.py` with valid credentials. Only call Nebius/Nemotron or Tavily “live” if the preflight and current UI status confirm that path succeeded. If a provider fails, fix it before the final recording or explicitly disclose the fallback.

## Demo honesty checklist

- Call a provider “live” only if the UI says `live_success` or `live_partial` for that path in this run.
- Do not describe an assumed lead time or reliability probability as verified supplier data.
- Do not call a Wilson interval a guarantee of real-world outcomes.
- Do not claim that a real order or payment was executed.
- Do not show secrets, local `.env`, or private account data.
