---
description: Seven-step checklist for adding a new agent or FastAPI route
paths: ["src/**"]
---

# New-feature checklist

This is the per-feature variant of the project's SDLC cycle (`Research → PRD → Build → Test → Push`). It assumes the PRD has been proposed and user-approved — if not, stop and go back to `CLAUDE.md` §SDLC.

Branches depending on what's being built:

## A. Adding an agent

1. **Research** — consult `docs/product_recap.md`, existing prompts, `adk-cheatsheet` / `adk-dev-guide` skills, `adk-docs` MCP. Confirm no existing agent already does what you need.
2. **PRD gate** — user-approved PRD. Before this line, no code.
3. **Schemas** — add `modules/<mod>/agents/<name>/schemas.py` (Pydantic, flat for Gemini 2.5 Flash structured-output reliability). Module-shared schemas go in `modules/<mod>/models/` instead — see placement table.
4. **Tools** — private tools in `modules/<mod>/agents/<name>/tools.py`; shared tools in `modules/<mod>/tools/`. Contract: return `{"status": "success"|"error"|"retry", ...}`, async for I/O. See `.claude/rules/tools.md`.
5. **Prompt(s)** — markdown in `modules/<mod>/agents/<name>/prompts/`. Co-located. Multiple files OK (system, few-shot, etc).
6. **Agent definition** — `modules/<mod>/agents/<name>/agent.py`. Apply:
   - Callback placement (`.claude/rules/agents.md` §1)
   - State namespacing (§2)
   - Structured-output two-agent pattern if combining schema with tools (§5)
   - Thinking-budget matching the agent's role (§8)
7. **Register with runner** — wire into `runners/` (Meta-Coordinator or direct FastAPI route).
8. **Tests** — pytest units for tools / callbacks / guardrails in `tests/unit/`. Integration tests against emulators in `tests/integration/` if the agent's tools hit Firestore.
9. **Evalset** — at least one scenario in `evals/<agent_name>/`. Not on Coordinators (ADK bug #3434). Required before merge.
10. **Verification report to user** — pytest results + ruff/mypy status + evalset results + concrete sample outputs for user to validate against domain expectations. Both sides — see CLAUDE.md §SDLC "Reporting done".

## B. Adding a FastAPI route

1-2. Research + PRD gate (same).
3. **Models** — if new domain, `modules/<mod>/models/`. Naming pyramid: `XxxBase → XxxCreate → XxxUpdate → XxxPublic → XxxsPublic` (list wrapper with `data: list[XxxPublic], count: int`).
4. **Firestore access** — if new domain, write a thin async helper in `modules/<mod>/memory/` that returns Pydantic models (never `DocumentSnapshot`). See `.claude/rules/firestore.md`.
5. **Route function** — `runners/routes/<domain>.py`. Apply:
   - Router `prefix` + `tags` convention (`.claude/rules/api-routes.md` §1)
   - Dependency parameter order (§3)
   - Keyword-only args with `*` when body present
   - Response envelope (§7)
   - Status codes + existence-before-permission (§8, §10)
   - Security-conscious error messages where relevant (§9)
6. **Register the router** — in `runners/app.py` (or wherever the app factory is).
7. **Tests** — `tests/api/routes/test_<domain>.py`, integration tests against the auth + Firestore emulators.
8. **Verification report** — same as A.

## Steps deliberately dropped (vs pasted rules)

- **Alembic migration** — no SQL, no Alembic. Firestore is schemaless.
- **Docker Compose** — we use Cloud Run + `adk web` locally.
- **`scripts/generate-client.sh`** — no frontend client until Tier 3.
- **DB migration step** — see above; Firestore composite indexes deployed via `firebase deploy --only firestore:indexes`, handled in deployment, not per-feature.
