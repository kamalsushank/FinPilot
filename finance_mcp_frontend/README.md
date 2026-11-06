# FinPilot React frontend

React + Vite UI for the Finance MCP FastAPI backend.

## Start
1. Keep the FastAPI backend running at `http://127.0.0.1:8000`.
2. Install Node.js (18+ recommended).
3. In this folder run:
   ```bash
   npm install
   ```
4. Copy `.env.example` to `.env` if your backend is not at the default URL. Set:
   ```env
   VITE_API_BASE_URL=http://127.0.0.1:8000
   ```
5. Run:
   ```bash
   npm run dev
   ```
6. Open the Vite URL printed in the terminal (`http://localhost:3000`).

## Backend contract
The UI calls `/health`, `/summary`, `/transactions`, `/bills`, `/bills/upcoming?limit=2`, `/bills/recurring`, `/investments/catalogue`, `/investments/profile/{user_id}`, `/investments/recommend`, and `/chat`.

The UI uses a demo user ID (`demo`) because the backend prototype does not implement authentication. Update `USER_ID` in `src/App.jsx` when your backend supports real user identities.

## Important integration notes
- FastAPI must allow CORS from the Vite origin (`http://localhost:3000`). The supplied backend package described in the project setup includes CORS middleware; if your backend does not, add it.
- Pydantic request schemas vary by implementation. This frontend sends intuitive JSON fields for transactions, bills, recurring bills, profiles, and chat. If a specific request returns HTTP 422, compare the field names in FastAPI `/docs` with the request body in `src/App.jsx` and align them.
- This is a prototype, not a production finance app. Add authentication, authorization, per-user database isolation, input validation, and proper error handling before real use.
- Investment information is educational; verify official terms and consider qualified advice before acting.
