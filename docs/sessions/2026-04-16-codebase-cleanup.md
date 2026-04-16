# 2026-04-16 — Codebase cleanup kickoff

## What changed

- Added shared triage type modules for severity, source channel, triage status, escalation priority, and the small request envelope used by the classifier and impact test endpoints.
- Extracted reusable classifier submodels into a shared module.
- Rewired the classifier and impact Tier 1 endpoints through one shared runner helper to remove duplicated orchestration.
- Trimmed noisy docstrings and comments in the audit logging middleware, hello-world agent, and impact agent.
- Removed the silent fallback from the impact priority-weight callback so parsing and shape errors now surface instead of being hidden.

## Decisions

1. **Centralize shared triage types.** Severity and other cross-agent enums belong in one shared module, not duplicated across model files.
2. **Preserve compatibility during consolidation.** The classifier and impact endpoint input types now alias a single shared envelope type so existing imports keep working.
3. **Use Python-native tooling for cleanup.** Knip and Madge do not apply to this repository; Vulture and Import Linter are the correct tools here.
4. **Do not hide callback failures.** The impact post-processing path should fail visibly rather than silently preserving stale ordering.
5. **Trim commentary, not useful intent.** Security and architecture comments stay; in-motion narrative comments were shortened or removed.

## Verification

- Pytest: 94 tests passed across the touched runner, model, and tool suites.
- Ruff: passed on the refactored model, runner, middleware, and agent files.
- Mypy: passed on `src` after updating the classifier agent import path to the shared severity module.
- Import Linter: all configured contracts kept.

## Files changed

- `src/supply_chain_triage/modules/triage/models/common_types.py`
- `src/supply_chain_triage/modules/triage/models/shared_models.py`
- `src/supply_chain_triage/modules/triage/models/api_envelopes.py`
- `src/supply_chain_triage/modules/triage/models/classification.py`
- `src/supply_chain_triage/modules/triage/models/exception_event.py`
- `src/supply_chain_triage/modules/triage/models/triage_result.py`
- `src/supply_chain_triage/modules/triage/models/impact.py`
- `src/supply_chain_triage/modules/triage/models/__init__.py`
- `src/supply_chain_triage/runners/_shared.py`
- `src/supply_chain_triage/runners/classifier_runner.py`
- `src/supply_chain_triage/runners/impact_runner.py`
- `src/supply_chain_triage/modules/triage/agents/classifier/schemas.py`
- `src/supply_chain_triage/modules/triage/agents/impact/schemas.py`
- `src/supply_chain_triage/modules/triage/agents/classifier/agent.py`
- `src/supply_chain_triage/modules/triage/agents/impact/agent.py`
- `src/supply_chain_triage/modules/triage/agents/hello_world/agent.py`
- `src/supply_chain_triage/middleware/audit_log.py`

## Remaining cleanup candidates

- Evaluate whether `FinancialBreakdown` should stay or be deleted once downstream consumers are confirmed.
- Decide whether the demo `hello_world` agent should remain as a bootstrap aid or be removed after the cleanup wave.
- Continue the broader dead-code pass with Vulture before deleting any other unused symbols.
