# 2026-04-16 — Sprint 1 Classifier Agent

## What was built

Classifier agent — two-agent pattern (fetcher + formatter) via SequentialAgent.
Accepts raw exception text OR Firestore event IDs, classifies into 6 exception
types with severity, key facts, confidence, and safety escalation.

### Files created/modified

**New agent package:**
- `modules/triage/agents/classifier/__init__.py`
- `modules/triage/agents/classifier/agent.py` — `create_classifier()` factory
- `modules/triage/agents/classifier/schemas.py` — `ClassifierInput`
- `modules/triage/agents/classifier/tools.py` — `get_exception_event`, `get_company_profile`
- `modules/triage/agents/classifier/prompts/system_fetcher.md` — v3, two-mode (event ID or raw text)
- `modules/triage/agents/classifier/prompts/system_formatter.md` — v1, taxonomy + 4 few-shot examples

**Infrastructure:**
- `runners/classifier_runner.py` — standalone `POST /api/v1/classify` endpoint
- `scripts/seed_classifier_demo.py` — 5 exception events + 1 company profile
- `docs/research/sprint1-classifier-research.md` — 8 research decisions
- `docs/research/gemini-structured-output-gotchas.md` — 12 documented bugs with mitigations
- `docs/research/adk-best-practices.md` — comprehensive patterns guide

**Tests:** 24 new (86 total), all passing

**Config changes:**
- `pyproject.toml` — added `TID251` ignore for `agents/*/tools.py`, added `E501` + `PLC0415` to global ignore
- `.pre-commit-config.yaml` — removed file-size hook, wrapped uv commands in `bash -c` for Windows PATH
- `.github/workflows/ci.yml` — auto-fix ruff lint/format + auto-commit, `contents: write` permission
- `.claude/rules/models.md` — added `dict[str, Any]` prohibition for output_schema models

## Key decisions

1. **Two-agent pattern** (fetcher + formatter) — Gemini Flash can't combine output_schema + tools
2. **English only** for Tier 1 — multilingual in Tier 2
3. **Manual entry only** — no email/carrier API parsing yet
4. **Confidence threshold 0.7** — below triggers `requires_human_approval`
5. **Hybrid severity** — LLM proposes + deterministic clamps (safety→CRITICAL, regulatory→≥HIGH)
6. **Iterative dev** — demo first, polish later
7. **15 evalset cases** target (capture-then-edit from adk web)
8. **5 seed exceptions** — truck breakdown, monsoon, customer escalation, hazmat, customs hold

## Bugs discovered and fixed

| Bug | Root cause | Fix |
|-----|-----------|-----|
| `additionalProperties not supported` | `dict[str, Any]` in Pydantic generates banned JSON Schema | Replace with `list[KeyFact]` / `SafetyEscalation` models |
| `extra="forbid"` rejected | Pydantic adds `additionalProperties: false` | Remove from all output_schema models |
| `ToolContext is not defined` | ADK introspects tool signatures at runtime | Runtime import with `# noqa: TC002` |
| `unexpected keyword argument 'callback_context'` | ADK uses kwargs, underscore prefix breaks matching | Keep exact param names, use `# noqa: ARG001` |
| `{triage:raw_exception_data}` not resolved | Colons in state keys break ADK template injection | Changed to `raw_exception_data` (no colon) |
| Formatter hallucinating (Gati instead of BlueDart) | `thinking_budget=0` + briefing after examples | Briefing first + `thinking_budget=1024` |
| `uv` not found in pre-commit | Windows PATH not inherited by `language: system` hooks | Wrapped with `bash -c` |

## Open questions for next session

- Evalset not yet created (need more adk web test sessions, then capture-then-edit)
- Mode A (Firestore event_id lookup) not tested live yet
- REST endpoint not tested live yet
- Need to run all 7 test scenarios and verify classifications
