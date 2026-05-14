# Local smoke check

You are defining a **fast local sanity check** after changes to AlphaListar (`backend/` FastAPI + LangGraph, `frontend/` React, PostgreSQL, Neo4j). Goal: confirm the app **starts** and **core plumbing works**—not full QA.

Adapt steps to what the user changed (backend-only, frontend-only, or both). Omit irrelevant steps.

## 1. Preconditions

Note assumptions explicitly:

- Dependencies installed (`pip install -r requirements.txt` under `backend/` where applicable; `npm install` under `frontend/` where applicable).
- Optional: Postgres and Neo4j reachable if the change touches connectors, orchestration, or queries—otherwise state “requires DB/graph” or “smoke without DB” if `/health` allows partial checks.

Never instruct pasting secrets into commands or chat.

## 2. Backend smoke

From the project root `CLAUDE.md` (backend dev commands):

1. Start API (typical): `cd backend/` then `uvicorn app.hybrid_api:app --reload --host 0.0.0.0 --port 8000`.
2. **GET** `/health` — confirm HTTP 200 and note whether response reflects database/graph connectivity (interpret fields if present).
3. If query path changed: **POST** `/query` with a **minimal safe body** per existing API schema (use project types or OpenAPI if available). Expect a structured response or a controlled error—not a 500 without diagnosis.

If the server fails to start, capture the **first** traceback line and module path—do not guess dozens of fixes at once.

## 3. Frontend smoke (if UI changed or full-stack verification requested)

1. `cd frontend/` then `npm start` (or project’s documented dev command).
2. Load the app in the browser; confirm main query or home view renders without console errors **related to this change**.
3. If the UI calls the API, confirm proxy/base URL points at the local backend (e.g. port **8000** per common setup).

## 4. Output for the user

Deliver a **numbered checklist** the user can tick:

- Commands in full (copy-paste friendly).
- **Pass criteria** per step (what “good” looks like).
- **If fail**: one subsection “Likely next checks” tied to AlphaListar layers (API route → orchestrator → SQL vs Cypher path → connectors).

Keep the whole smoke path short enough to run in a few minutes.
