# FinPilot — complete backend and frontend

This bundle contains the FastAPI + SQLite + Gemini/MCP backend and the React/Vite frontend matching the supplied FinPilot screenshot.

## 1. Backend

Open a terminal in `finance_mcp_backend`:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Create `.env` from `.env.example` and add your Gemini API key if you want Gemini-powered intent routing and investment research. The app can still use deterministic routing without a key.

Start the API from the `finance_mcp_backend` directory:

```powershell
uvicorn app.main:app --reload
```

API: `http://127.0.0.1:8000`
Health check: `http://127.0.0.1:8000/health`
Swagger docs: `http://127.0.0.1:8000/docs`

Use Python 3.11 or 3.12 for the smoothest dependency compatibility. Do not copy a virtual environment from another machine.

## 2. Frontend

Open a second terminal in `finance_mcp_frontend`:

```powershell
npm install
```

Create `.env` from `.env.example` and set:

```env
VITE_API_BASE_URL=http://127.0.0.1:8000
```

Start:

```powershell
npm run dev
```

Open the local URL printed by Vite (normally `http://localhost:5173`).

## 3. Important

- Start the backend before using the frontend. The header shows `Backend offline` when the API cannot be reached.
- The frontend sends chat messages to `POST /chat` and refreshes the dashboard from `/summary`, `/transactions`, `/bills/upcoming`, and `/investments/holdings/{user_id}`.
- The SQLite database is created automatically by the backend on startup.
- This prototype uses a demo user ID in the frontend. It is not production multi-user authentication; do not deploy it with real financial or personal data until authentication, authorization, per-user database scoping, secrets management, and deployment security are implemented.
- Investment research is informational, not financial advice. Recommendations are not purchases.
