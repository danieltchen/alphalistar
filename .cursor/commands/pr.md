# Pull request helper

You are drafting a **pull request description** for this repo (AlphaListar: hybrid RAG—PostgreSQL, Neo4j, LangGraph orchestration in `backend/`, React UI in `frontend/`). Produce something a reviewer can scan in two minutes.

## 1. Branch context

Determine (from git or ask once if unclear):

- Current branch name
- Merge base / target branch (`main`, `master`, or `develop`—whatever this repo uses)

State them briefly at the top of the PR body.

## 2. Content (use these sections in order)

Write in **complete sentences**. Prefer clarity over length.

1. **Summary** — What changed and **why**. Lead with user-visible behavior or API behavior; internal refactors second.
2. **Areas touched** — Bullets with real paths or modules (e.g. `hybrid_orchestrator`, `hybrid_api`, React components, connectors). Avoid vague labels only.
3. **Testing** — What was run in this work (commands or manual checks). If nothing was run, say **Not run** and list sensible verification steps for the reviewer (e.g. `uvicorn` smoke on `/health`, sample `POST /query`, `npm test` when UI changed). Stay honest.
4. **Risk / rollout** — Only if relevant: breaking API changes, new env vars, DB schema or migrations, Neo4j/Postgres connectivity assumptions, or deployment notes. Omit this section if there is no meaningful risk.

## 3. Title and description format

- **PR title**: Present tense, concise (like a good commit subject). Example: `Add citation filtering to hybrid trace response`.
- **PR body**: Markdown with the sections above. Include a short **Summary** paragraph first, then headings or bold labels for **Areas touched**, **Testing**, and **Risk / rollout** (omit Risk if N/A).

## 4. Optional GitHub CLI

If `gh` is available and the user uses GitHub, you may append one line suggesting they can paste the title/body into:

`gh pr create --title "..." --body "$(cat <<'EOF' ... EOF)"`

or `gh pr edit` for an existing PR. Do **not** require `gh`; many workflows use the web UI only.

## 5. Do not

- Invent testing that did not happen.
- Paste secrets or internal credentials into the PR text.
- Duplicate the entire contents of `CLAUDE.md`; only reference architecture when it helps the reviewer (e.g. “SQL + graph hybrid path”).
