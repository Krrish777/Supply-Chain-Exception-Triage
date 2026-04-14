---
description: Application-layer import direction — who may import from whom across runners/agents/tools/memory/models/core/utils
paths: ["src/**"]
---

# Architecture layer rules

Two rule files together control imports. `.claude/rules/imports.md` bans **vendor** imports (ADK, Firebase, Firestore) outside specific folders — that's about framework-swap resilience. This file controls **application-layer** direction — who in our own code may import from whom. Both are enforced: `TID251` for vendor bans, `import-linter` for application layers (run via `lint-imports` in pre-commit and CI).

## 1. Layers

Layers are listed top-down. Higher layers may import from lower layers; **the reverse is forbidden**.

```
runners/                  (top — FastAPI app, routes, ADK runner wiring)
middleware/               (auth, tracing, request logging)
modules/<mod>/agents/     (agent definitions)
modules/<mod>/tools/      (tools — both per-agent and module-shared)
modules/<mod>/memory/     (Firestore + ADK session/memory adapters)
modules/<mod>/models/     (module-shared Pydantic models)
modules/<mod>/guardrails/ (validators, pure)
core/                     (settings, config, constants)
utils/                    (bottom — pure helpers, no vendor imports)
```

## 2. Direction table

| Layer | May import from | Must not import from |
|---|---|---|
| `runners/` | `middleware`, `modules/*/agents`, `modules/*/memory`, `core`, `utils` | — (nothing imports `runners`) |
| `middleware/` | `core`, `utils`, Firebase Auth SDK | `runners`, agents, tools, memory, models |
| `modules/*/agents/` | own `schemas`/`tools`/`prompts`, shared `modules/*/tools`, `modules/*/models`, `modules/*/guardrails`, `core`, `utils` | `runners`, `middleware`, direct `memory`, direct Firestore/Firebase, **sibling modules' agents** |
| `modules/*/tools/` (per-agent or shared) | `modules/*/memory`, `modules/*/models`, `core`, `utils` | agents, runners, middleware, **other tools in different modules** |
| `modules/*/memory/` | `modules/*/models`, `core`, `utils`, Firestore/Firebase SDK | agents, tools, runners, middleware |
| `modules/*/models/` | `core`, `utils`, stdlib, Pydantic | agents, tools, memory, runners, middleware |
| `modules/*/guardrails/` | `modules/*/models`, `core`, `utils`, Pydantic | agents, tools, memory, runners, middleware |
| `core/` | stdlib, Pydantic, pydantic-settings | anything else in project |
| `utils/` | stdlib only | anything else in project |

Keep in mind: **`.claude/rules/imports.md`** also bans `google.adk.*` / `firebase_admin` / `google.cloud.firestore` outside their specific allowlist — that's orthogonal to this table.

## 3. What each layer does NOT do

- **Routes** (`runners/`) do NOT contain business logic, data transformation, or direct DB queries. They parse input, dispatch to the agent runner or a memory adapter, shape the response.
- **Agents** (`modules/*/agents/`) do NOT call Firestore or Firebase directly. They call tools. Always.
- **Tools** (`modules/*/tools/`) do NOT call other tools cross-module. Shared logic goes in `modules/<mod>/tools/<util>.py` as pure functions, or in `utils/` if truly generic.
- **Memory** (`modules/*/memory/`) does NOT call agents or tools. It is terminal — data in, data out.
- **Models / schemas / guardrails** do NOT contain side effects. Pydantic validators and pure transformations only.
- **Core** does NOT import from modules. It is the project-wide config / settings / constants pool.
- **Utils** do NOT import ADK, Firebase, or Firestore. Pure.

## 4. Cross-module rule (Tier 2+)

When `port_intel/` lands as a second module, it sits as a sibling of `triage/` under `modules/`. Direct imports between sibling modules (e.g. `modules.port_intel.agents` importing `modules.triage.tools`) are forbidden — cross-module coordination goes through the Meta-Coordinator in `runners/`. This is the contract that makes the Module-Ready Orchestrator architecture work.

## 5. Enforcement

Encoded in `pyproject.toml` as `[tool.importlinter]` contracts. Run via:
```bash
uv run lint-imports
```
Pre-commit runs it on every commit. CI runs it on every push/PR.

If you hit a contract violation, the fix is almost always one of:
1. **Move the offending code** to a lower layer (e.g. extract the query into a memory adapter, call it from the agent's tool instead of in the agent).
2. **Introduce a pure model** that both layers can depend on, rather than pulling one layer into another.
3. **Invert the dependency** — pass in a callable or value, don't import upward.

If none of those fit, the rule is probably wrong — flag it in a session note and discuss before adding an exception.
