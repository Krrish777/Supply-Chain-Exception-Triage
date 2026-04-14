---
description: Import boundaries — keep ADK/Firestore/Firebase at the edges so the framework stays swappable
paths: ["src/**"]
---

# Import rules

These are positive scopes — X is allowed *only* in the listed places. Everywhere else, it's a ruff `TID251` lint error backed by `[tool.ruff.lint.flake8-tidy-imports.banned-api]` in `pyproject.toml`.

## `google.adk.*`

Import only in:
- `modules/*/agents/*/agent.py` — agent definitions
- `runners/` — FastAPI app factory, ADK runner wiring, Meta-Coordinator
- `modules/*/memory/` — persistence adapters that wrap `FirestoreSessionService`

Use the precise form: `from google.adk.tools.<tool_name> import <tool_name>`, not `from google.adk.tools import <tool_name>` (adk-dev-guide requirement).

## `firebase_admin`

Import only in:
- `modules/*/memory/` — Firestore access from memory adapters
- `modules/*/tools/` — tools that wrap Firestore queries
- `middleware/` — Firebase Auth token verification

## `google.cloud.firestore`

Import only in:
- `modules/*/memory/`
- `modules/*/tools/`
- `middleware/`

Prefer `google.cloud.firestore.AsyncClient` (not `firebase_admin.firestore.client()` which returns sync).

## Consuming sides

- Agents call tools. Agents do NOT call Firestore or Firebase Auth directly.
- `utils/`, `core/`, `models/`, any `schemas.py`, `guardrails/`, `tools/` shared code: Pydantic-only boundaries. Receive dicts / Pydantic models, never SDK objects.

## Pydantic

Allowed everywhere. Preferred at every inter-layer boundary.

## Why these rules exist

If ADK imports leak into schemas or utils, swapping to LangGraph / CrewAI / PydanticAI becomes an ~80% rewrite instead of ~20%. If Firebase/Firestore SDK objects leak out of memory/tools, agent code becomes coupled to a vendor and tests have to mock a database.
