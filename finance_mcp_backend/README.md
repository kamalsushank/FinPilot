# Finance MCP Backend

## Features
- SQLite transactions, summaries and bills
- Monthly recurring bill templates with idempotent occurrence generation
- Dashboard endpoints for upcoming bills
- MCP tools over the project's existing `MCPServer`/`Client` setup
- Investment catalogue covering government schemes, LIC/insurance, mutual funds, deposits, NPS, equities and gold-related options
- Gemini-powered finance request routing and Google Search-grounded investment research
- Financial profile storage for investment suitability context

## Setup (Windows PowerShell)
1. Copy these files into your existing project, keeping the `app/` package structure.
2. Activate your virtual environment.
3. Install requirements:
   ```powershell
   python -m pip install -r requirements.txt
   ```
4. Keep the MCP package/version that already works in your project; this code uses your existing `MCPServer` / `Client` API. Do not replace it blindly with a different MCP SDK.
5. Copy `.env.example` to `.env` and set `GEMINI_API_KEY`.
   The backend still starts without a key, but model-backed routing/research will use the clearly-labelled catalogue fallback.
6. Start FastAPI:
   ```powershell
   uvicorn app.main:app --reload
   ```
7. Open http://127.0.0.1:8000/docs.

## Useful API routes
- `GET /health`
- `POST /transactions`, `GET /transactions`, `GET /summary?month=2026-10`
- `POST /bills`, `GET /bills?status=pending`, `POST /bills/{id}/pay`
- `POST /bills/recurring`, `GET /bills/recurring`, `PATCH /bills/recurring/{id}?active=false`
- `GET /bills/upcoming?limit=2`
- `GET /investments/catalogue`
- `PUT /investments/profile/{user_id}`
- `POST /investments/recommend`
- `POST /chat`

## Recurring bill example
POST `/bills/recurring`:
```json
{
  "name": "Home Wi-Fi",
  "amount": 799,
  "day_of_month": 28,
  "start_date": "2026-10-26"
}
```
The API creates the monthly template and generates a rolling window of bill occurrences. Repeated calls do not duplicate occurrences. Day 29, 30 or 31 is clamped to the last valid day in shorter months. Marking one occurrence paid does not affect other months.

## Chat example
POST `/chat`:
```json
{
  "user_id": "default",
  "message": "Compare government savings schemes and mutual funds for a 5-year goal"
}
```
With `GEMINI_API_KEY`, Gemini chooses a manager action and investment research can use Google Search grounding. Without the key, the backend uses deterministic routing and returns a catalogue-only fallback. Never treat the fallback as a personalized recommendation.

## Important limitations before public deployment
This is a learning/prototype backend, not yet production-secure:
- `user_id` is a caller-supplied label, not authentication. Do not expose personal financial data publicly until real authentication and per-user authorization are implemented.
- Investment research is informational. Verify current rates, tax treatment, eligibility, risk, fees and product availability from official sources before acting.
- The local catalogue is starter context and may become stale; grounded research should be used for current details.
- SQLite is suitable for a local prototype. Review database persistence, backups, concurrency and deployment storage before production.
- No notification scheduler or push/email/SMS delivery is implemented.
