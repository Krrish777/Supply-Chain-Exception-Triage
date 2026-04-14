---
description: Guardrails-AI integration — Guard.for_pydantic, num_reasks, when to use vs ADK callbacks, severity-clamp pattern, fallback discipline
paths: ["src/supply_chain_triage/modules/*/guardrails/**", "src/supply_chain_triage/modules/*/agents/*/agent.py"]
---

# Guardrails rules

Two validation mechanisms coexist: **ADK's `after_model_callback`** (in-runtime transport) and **Guardrails-AI `Guard.for_pydantic()`** (LLM-recoverable re-ask with structured error feedback). Use them in layered composition — not as alternatives.

## 1. Decision rule — when Guardrails vs when callback vs when plain Pydantic

| Need | Pick |
|---|---|
| Schema-shape validation only (types, required fields) | Pydantic `model_validate_json` in `after_model_callback` |
| Deterministic domain invariant (severity never downgrades, confidence in [0, 1]) | Plain post-callback clamp or Pydantic `@field_validator` |
| LLM-recoverable format / content issue (malformed JSON, missing field) | Guardrails `Guard.for_pydantic()` + `num_reasks` |
| In-runtime mutation of `LlmResponse` before state write | ADK callback as the transport |
| Validator marketplace (toxicity, PII, regex bank) | Guardrails Hub validators |
| Input safety / jailbreak filtering | `before_model_callback` — NOT Guardrails (runs post-LLM) |

**Rule of composition:** the ADK callback is the **transport** (intercept `LlmResponse`, parse, write state). Guardrails runs **inside** that callback when re-ask is needed. Never run two re-ask loops at different layers (e.g. `LoopAgent(max_iterations=3)` wrapping an agent whose callback already uses `num_reasks=3` → up to 9 LLM calls per exception).

## 2. `Guard.for_pydantic()` usage

```python
from guardrails import Guard

guard = Guard.for_pydantic(ClassificationResult)

def after_model_cb(callback_context, llm_response):
    raw = llm_response.content.parts[0].text
    outcome = guard.parse(raw, num_reasks=2, llm_api=gemini_reask_fn)
    if outcome.validation_passed:
        callback_context.state["triage:classification"] = outcome.validated_output
    else:
        callback_context.state["triage:classification_error"] = outcome.error
    return None
```

**`Guard.parse()`** (not `guard()`) is the entry point when ADK already produced output — it takes the raw string and only re-asks on validation failure. `guard()` is for "generate from scratch" flows.

**`validation_passed`** gates the state write. **Never raise from a callback** — kills the agent run. Set state flags and let the Coordinator route.

## 3. `num_reasks` default

- **`num_reasks=2`** is the Sprint 1 PRD value and community consensus.
- Empirically: 1 catches ~85% of recoverable failures, 2 catches ~95%, 3 hits diminishing returns and 4× worst-case cost.
- Each re-ask is a **fresh LLM call** — linear token multiplier `(1 + num_reasks) × avg_tokens`. No batching.
- With Gemini 2.5 Flash pricing this is cheap; latency stacks.

Use `full_schema_reask=False` to re-ask only failing fields instead of regenerating the whole output.

## 4. The "severity never downgrades" invariant — NOT a Guardrails case

Sprint 1 PRD requires the severity validator to only **escalate**, never downgrade. This is a **deterministic clamp**, not an LLM-recoverable error. Re-asking the LLM to "stop downgrading" wastes tokens when you can clamp directly.

**Wrong** (over-uses Guardrails):
```python
@register_validator(name="severity-monotonic", data_type="string")
class SeverityMonotonic(Validator):
    ...  # re-asks LLM to not downgrade
```

**Right** (deterministic clamp in a callback after Guardrails validates shape):
```python
SEVERITY_ORDER = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

def clamp_severity(current: str, prior: str | None) -> str:
    if prior is None:
        return current
    return current if SEVERITY_ORDER[current] >= SEVERITY_ORDER[prior] else prior
```

**Reach for Guardrails custom validators only for things the LLM can plausibly fix on retry** — format errors, missing fields, out-of-vocab enum values, regex mismatches.

## 5. Validator chaining

Guardrails supports multiple validators per field. Execution is in **declaration order**; `on_fail` is per-validator: `"reask" | "fix" | "filter" | "refrain" | "exception" | "noop"`.

```python
from pydantic import Field
from guardrails.hub import ToxicLanguage, DetectPII

class ClassificationResult(BaseModel):
    rationale: str = Field(
        json_schema_extra={"validators": [
            DetectPII(on_fail="fix"),       # mutates + continues
            ToxicLanguage(on_fail="reask"), # triggers re-ask on fail
        ]}
    )
```

First non-`noop` failure short-circuits the chain for that field unless `on_fail="fix"` mutates and continues.

**Never `on_fail="exception"` in production callbacks** — crashes the run. Prefer `"fix"` or `"reask"`, then set a state flag.

## 6. Fallback discipline

When `num_reasks` is exhausted and validation still fails:

```python
callback_context.state["triage:classification"] = {
    "severity": "CRITICAL",          # safest default
    "confidence": 0.0,
    "requires_human": True,
    "failure_reason": str(outcome.error),
}
```

**Why `CRITICAL` as fallback** — unknown exception in logistics defaults to "human looks at it". Matches Sprint 1 PRD's escalation invariant. Never silently placeholder as `LOW` or `MEDIUM`.

Never raise from a callback — let the Coordinator's router react to the state flag.

## 7. Multi-language / Hindi-Hinglish content

Guardrails passes strings through unchanged (UTF-8). Re-ask prompts are English-templated but include the original (non-ASCII) value verbatim. Gemini 2.5 Flash handles the mixed prompt correctly.

**Gotcha:** `length` / `min_length` / `max_length` validators count **codepoints, not graphemes**. Devanagari conjuncts (क्ष, त्र) mis-count. For Hindi content, apply length caps on **token counts via Gemini tokenizer**, not codepoint counts.

## 8. When a lighter alternative beats Guardrails

Guardrails-AI adds ~40MB deps (litellm, lxml, jsonref). If you need only shape validation + re-ask, a lighter combo covers ~80% of the use cases:

```python
from pydantic import ValidationError

def after_model_cb(callback_context, llm_response):
    try:
        parsed = ClassificationResult.model_validate_json(llm_response.content.parts[0].text)
        callback_context.state["triage:classification"] = parsed.model_dump()
    except ValidationError as e:
        # signal LoopAgent to retry; max_iterations=2 in the parent
        callback_context.state["temp:retry_reason"] = str(e)
```

Pair with `LoopAgent(max_iterations=2)` wrapping the `LlmAgent`. No Guardrails dep.

**Pick Guardrails when** you genuinely need (a) the validator Hub (toxicity, PII, competitor-mention, custom regex banks) **and** (b) structured error feedback on re-ask. Otherwise stick with Pydantic + `LoopAgent`.

## 9. Placement

```
modules/<mod>/guardrails/
├── __init__.py
├── classifier_validators.py      # Guardrails custom validators + deterministic clamps
├── impact_validators.py
└── shared.py                     # validators reused across agents
```

Guardrails validators are pure (no ADK / Firebase / Firestore imports) — they pass `.claude/rules/imports.md`. Callbacks that invoke them live with the agent (`modules/<mod>/agents/<name>/agent.py`).

## 10. Anti-patterns

- **Guardrails for shape-only validation** — Pydantic suffices.
- **Guardrails for deterministic invariants** (severity clamp, confidence bounds) — plain function / `@field_validator`.
- **Guardrails for jailbreak / PII *input* filtering** — that belongs in `before_model_callback`; Guardrails runs post-LLM.
- **Stacked re-ask loops** — `LoopAgent(max_iterations=3)` around an agent with `num_reasks=3` → 9 LLM calls per exception.
- **`on_fail="exception"` in callbacks** — crashes the run. Use `"fix"` or `"reask"` then state-flag.
- **Silent low-severity fallback** — always fallback to `CRITICAL` + `requires_human=True`.
- **Raising from a callback** — kills the agent run. State-flag and let Coordinator route.
- **Using codepoint-length validators on Devanagari** — use token-count validators instead.
- **Guardrails version pinned to a Hub validator's minor version** — validators evolve; pin the library, declare Hub validators by name.
