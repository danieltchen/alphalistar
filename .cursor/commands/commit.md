# Commit helper

You are preparing a **single, reviewable Git commit** for this repo (AlphaListar: hybrid RAG stack with `backend/` FastAPI + LangGraph, `frontend/` React). Follow these steps in order.

## 1. Inspect the working tree

Run (or use equivalent visibility into the repo):

- `git status`
- `git diff` for unstaged changes
- `git diff --staged` if anything is already staged

Summarize **what** changed and **where**, using real paths (e.g. `backend/`, `frontend/`, orchestrator modules, API, connectors). Group by logical area (API, orchestration, UI, config, dependencies).

## 2. Safety and scope

- **Do not** commit secrets, API keys, tokens, `.env` files, credentials, or large generated artifacts. If the diff includes any of these, say so clearly and stop short of recommending `git add` for those paths.
- Prefer **one logical change** per commit. If the working tree mixes unrelated concerns (e.g. backend feature + unrelated frontend formatting), recommend **splitting** into two commits and outline what belongs in each.

## 3. Proportional checks

Match verification to the change:

- **Docs / comments only**: no need to mandate tests.
- **Python backend**: note whether tests or lint were run in this session; if not, suggest what the author should run before pushing (e.g. targeted test module or `pytest` if the project uses it). Do not insist on a full CI-equivalent run for small edits.
- **Frontend**: same idea—e.g. `npm test` or smoke-check only when the change warrants it.

## 4. Commit message rules

- **Subject**: imperative mood, concise (aim for ~50 characters; slightly longer is fine if necessary). Example: `Fix trace serialization when Neo4j returns empty paths`.
- **Optional prefix** (conventional style): `feat:`, `fix:`, `chore:`, `docs:`, `refactor:`, `test:`—use when it clarifies intent.
- **Body**: include only when it helps (motivation, behavior change, risk, or how to verify). Use complete sentences; keep it proportional.

## 5. Output for the user

Deliver:

1. **Staging suggestion**: which paths or files to `git add` (or explicit note if everything should be staged).
2. **Final commit message** ready to paste (subject + optional body).
3. If splitting is better: **Commit A** / **Commit B** messages and what goes in each.

Do not run destructive git commands (`reset --hard`, `clean`, force-push) unless the user explicitly asks.
