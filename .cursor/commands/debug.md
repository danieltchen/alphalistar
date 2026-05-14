# Debug helper

You are guiding **structured debugging** for AlphaListar (FastAPI backend, LangGraph hybrid orchestration, PostgreSQL, Neo4j, React frontend). Prefer narrowing the problem before proposing code changes.

## 1. Clarify the symptom

Establish quickly:

- **Where** it fails (backend API, orchestrator node, DB connector, Neo4j, frontend, build).
- **Expected vs actual** behavior in one sentence each.
- **Repro**: minimal steps (request payload, UI action, env). If unknown, list what information is still needed.

## 2. Gather evidence (use what exists)

Inspect relevant code paths—typically under `backend/` (e.g. `hybrid_api`, `hybrid_orchestrator`, `connector_database`, `connector_neo4j`, `trace_manager`, classifiers/generators). For UI issues, trace from React to API calls.

Suggest **targeted** checks, proportional to the bug:

- **Logs / traces** — trace IDs from responses if present; server logs around the failing request.
- **Health** — whether the service starts and `/health` reflects DB/graph connectivity when that endpoint exposes it.
- **Isolation** — SQL-only vs graph-only vs hybrid routing (`query_classifier`); failing subsystem (Postgres vs Neo4j vs LLM).
- **Config** — env vars and connection strings (without echoing secrets): confirm presence of required vars, not their values in chat.

Do not ask the user to paste API keys or passwords.

## 3. Hypotheses and order

List **2–4 ranked hypotheses** (most likely first). For each: short rationale, what would falsify it, and the **next single experiment** (one log line, one breakpoint location, one curl call, one isolated script).

Avoid shotgun edits; prefer one hypothesis at a time unless symptoms clearly implicate multiple layers.

## 4. Fix direction

When the cause is likely identified:

- Propose a **minimal** fix and where it lives (file/module).
- Note **regression prevention**: test, assertion, or guardrail worth adding.
- If the root cause is environmental (DB down, Neo4j unreachable), say so clearly and separate from code defects.

## 5. Output summary

End with:

1. **Most probable cause** (or “still unclear” + narrowest next step).
2. **Recommended fix** (or investigation step if not ready to fix).
3. **Verify** — how to confirm the fix (command or manual check), referencing project norms when helpful (e.g. local `uvicorn` for API smoke).
