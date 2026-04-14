---
description: Anti-bloat limits, no god functions, docstring scope, comments why-not-what
paths: ["src/**"]
---

# Code quality rules

Calibrated to this project's shape (ADK multi-agent, not FastAPI CRUD). These are **strong guidelines** — deviate only with a code comment explaining why.

## 1. Anti-bloat limits

| File | Soft limit | If exceeded |
|---|---|---|
| `agent.py` | ~150 lines | Extract sub-agents into their own subpackage; push orchestration logic up to the Coordinator or a SequentialAgent |
| `schemas.py` (per agent) | ~100 lines | Promote shared types to `modules/<mod>/models/` |
| `tools.py` (per agent) | ~200 lines | Move shared helpers to `modules/<mod>/tools/`; split by concern |
| `prompts/*.md` | ~500 lines per file | Split into multiple prompt files (`system.md`, `fewshot.md`, `edge_cases.md`) |
| `modules/<mod>/tools/*.py` | ~300 lines | Split by concern within the module |
| `modules/<mod>/memory/*.py` | ~200 lines | One adapter concern per file |
| `runners/routes/*.py` | ~200 lines | Split into subpackage (one file per resource) |
| `middleware/*.py` | ~150 lines | One middleware concern per file |
| `utils/logging.py` | ~500 lines | Narrow exception — the canonical logging entry point (see `architecture-layers.md` §2). One file by design; splitting fragments the processor/handler/helper chain |
| `utils/*.py` (other) | ~200 lines | Pure helpers — extract concerns into separate files |
| Any function | ~40 lines | Extract helpers |

A well-structured 210-line file is better than a poorly-structured 50-line one — but both run past 500 is a smell. File length is enforced by `.claude/hooks/check_file_size.py` via pre-commit; function-level complexity is enforced by ruff (`C901`, `PLR0915`, `PLR0912`, `PLR0913`, `PLR0911`, `PLR0914`) with research-default thresholds in `pyproject.toml`.

## 2. No god functions

Signs of a god function — if any two are true, split:

- More than 3 distinct operations (fetch, transform, validate, save, notify, emit event, ...)
- Multiple levels of nested `if/else` or `try/except`
- You wrote paragraph-level comments to explain sections within the function
- The function touches more than one layer (route + CRUD + external API + formatting in one body)
- Over ~40 lines of actual code (excluding docstring)

Ruff `C901` (cyclomatic complexity) and `PLR0915` / `PLR0912` catch many — but not all. Visual review of long functions still matters.

## 3. Docstrings — scope

**Required** (ruff `D1*` + `interrogate --fail-under=80` enforce):

- Public route handlers in `runners/`
- Public tools — both `modules/*/agents/*/tools.py` and `modules/*/tools/**`
- Public functions in `modules/*/memory/`
- Public callbacks (`before_*_callback`, `after_*_callback` definitions used by agents)
- Public functions in `middleware/`

**Not required** (ruff `D` silenced via per-file-ignores):

- `tests/**`
- `src/supply_chain_triage/utils/**` — internal helpers, self-documenting names
- `**/schemas.py` — pure Pydantic models, field descriptions serve the purpose
- `**/__init__.py` — re-exports
- `src/supply_chain_triage/core/**` — D2* style rules only, D1* (missing-docstring) silenced

**Style:** Google convention (`Args:` / `Returns:` / `Raises:` / `Yields:`). Matches adk-samples. Enforced by `[tool.ruff.lint.pydocstyle] convention = "google"` in `pyproject.toml`.

**Shape of a required docstring:**
```python
async def get_exception(exception_id: str, tool_context: ToolContext) -> dict:
    """Retrieve an exception by ID.

    Args:
        exception_id: Firestore doc ID for the exception (ULID, 26 chars).
        tool_context: ADK tool context (provides state + actions).

    Returns:
        ``{"status": "success", "data": ExceptionRecord dict}`` on hit,
        ``{"status": "error", "error_message": str}`` on miss.
    """
```

## 4. Comments — WHY not WHAT

**Add comments only when the "why" is non-obvious from the code:**
```python
# Timing-attack prevention: run hash even if user doesn't exist.
verify_password(password, DUMMY_HASH)
```

**Do NOT write comments that restate what the code already says:**
```python
# BAD — the identifier already tells the story
user = get_user_by_email(session=session, email=email)
```

**Do NOT**:
- Write comments explaining the current task, fix, or callers ("used by X", "added for the Y flow", "handles the case from issue #123") — those belong in the PR description and rot fast.
- Leave stale comments pointing at code that moved.
- Add TODO / FIXME without an owner + a tracking entry. Use `docs/sessions/` for "open questions".

## 5. One component per file (frontend — Tier 3)

When the Tier 3 React dashboard lands, `.claude/rules/frontend.md` will add:
- One exported component per file
- Feature folders mirror backend modules
- Shared components in `components/Common/`
- Reusable logic → hooks in `src/hooks/`
- `@/` path alias, never relative-to-root imports
- Component line limit ~250, route file ~100, hook file ~120

Deferred. Not in scope until Tier 3 work begins.

## 6. Enforcement summary

| Concern | Tool | Where |
|---|---|---|
| Function statements / branches / args / returns / locals | ruff `PLR09**` | `pyproject.toml` `[tool.ruff.lint.pylint]` |
| Cyclomatic complexity | ruff `C901` | `[tool.ruff.lint.mccabe]` |
| Docstring presence + style | ruff `D` + `pydocstyle convention = google` | `pyproject.toml` |
| Docstring coverage ≥80% on boundary folders | `interrogate --fail-under=80` | `.pre-commit-config.yaml` + CI |
| File length per path type | `.claude/hooks/check_file_size.py` | `.pre-commit-config.yaml` |
| God functions | `C901` + human review | ruff + PR review |

If a rule is binding here, it's encoded in `pyproject.toml` or `.pre-commit-config.yaml`. If it's advisory, this file is the record.
