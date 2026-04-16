# Gemini Structured Output Gotchas

> Date: 2026-04-16
> Context: Discovered during Sprint 1 Classifier testing with `adk web`

## 1. `additionalProperties` not supported

**Error:** `ValueError: additionalProperties is not supported in the Gemini API`

**Cause:** Pydantic models with `dict[str, Any]` fields generate JSON Schema
containing `additionalProperties`, which the `google-genai` SDK rejects during
client-side validation.

**Fix:** Replace `dict[str, Any]` with either:
- `list[KeyValuePair]` where `KeyValuePair` is a flat Pydantic model with `key: str` and `value: str`
- A dedicated flat Pydantic model with named fields

**Applied to:** `ClassificationResult.key_facts` changed from `dict[str, Any]` to `list[KeyFact]`,
`safety_escalation` changed from `dict[str, Any] | None` to `SafetyEscalation | None`.

**Sources:**
- [googleapis/python-genai#1113](https://github.com/googleapis/python-genai/issues/1113)
- [googleapis/python-genai#1815](https://github.com/googleapis/python-genai/issues/1815)

## 2. `ToolContext` must be runtime import

**Error:** `NameError: name 'ToolContext' is not defined`

**Cause:** ADK uses `typing.get_type_hints()` at runtime to introspect tool function
signatures. If `ToolContext` is inside `TYPE_CHECKING`, it's not available at runtime.

**Fix:** Import at runtime: `from google.adk.tools import ToolContext  # noqa: TC002`

**Source:** [adk-python#3090](https://github.com/google/adk-python/issues/3090)

## 3. Callback parameters are keyword arguments

**Error:** `TypeError: _clear_history() got an unexpected keyword argument 'callback_context'`

**Cause:** ADK calls callbacks with `callback(callback_context=..., llm_request=...)`.
Renaming params with underscore prefix (`_callback_context`) breaks keyword matching.

**Fix:** Keep exact names (`callback_context`, `llm_request`, `llm_response`).
Use `# noqa: ARG001` to suppress unused-arg warnings instead of renaming.

## 4. Gemini 2.5 Flash nesting limits

- Max nesting depth: 5 levels
- Max properties: 100
- Short enum values only (~100 values max)
- `list[BaseModel]` works but deep nesting degrades reliability
- Put `reasoning` field last in schema (forces model to analyze before classifying)

## 5. `output_schema` + tools = infinite loop (ADK v1.18+)

**Error:** Agent repeatedly calls the same tool indefinitely instead of producing structured output.

**Cause:** When `LlmAgent` has both `output_schema` and `tools`, Gemini 2.5 Flash
enters a deterministic tool-call loop. The model generates tool calls instead of
producing the structured JSON response.

**Fix:** Use the **two-agent pattern** (fetcher + formatter via `SequentialAgent`).
Fetcher has tools but no `output_schema`. Formatter has `output_schema` but no tools.

**Sources:**
- [adk-python#3413](https://github.com/google/adk-python/issues/3413)
- [adk-python#3969](https://github.com/google/adk-python/issues/3969)

## 6. Tool calls in history break structured output on Gemini 2.5

**Error:** `Function calling with a response mime type: 'application/json' is unsupported`

**Cause:** When tool call events exist in the conversation history, Gemini 2.5
rejects structured output requests. Works fine on Gemini 2.0.

**Fix:** Clear conversation history before the formatter agent via
`before_model_callback` that sets `llm_request.contents = []`.
Also set `include_contents="none"` on the formatter.

**Source:** [googleapis/python-genai#706](https://github.com/googleapis/python-genai/issues/706)

## 7. `extra="forbid"` generates `additionalProperties: false` — also rejected

**Error:** `Unknown name "additional_properties" at 'generation_config.response_schema'`

**Cause:** Pydantic `ConfigDict(extra="forbid")` adds `additionalProperties: false`
to the JSON Schema. Gemini rejects ANY `additionalProperties` key — both `true` and `false`.

**Fix:** Remove `extra="forbid"` from ALL models used as `output_schema` or nested
within one. Use plain `ConfigDict()` instead. Validate at API boundaries separately.

**Applied to:** `ClassificationResult`, `KeyFact`, `SafetyEscalation` all had
`extra="forbid"` removed.

## 8. Schema complexity triggers 400 errors

**Error:** `InvalidArgument: 400`

**Cause:** Complex schemas with many optional properties, deep nesting, long
property names, or large enum sets. The Gemini SDK has undocumented limits.

**Fix:**
- Shorten property names
- Reduce nesting to <= 2 levels
- Limit enum values
- Mark fewer fields as optional
- Split schema across two agents if needed

**Source:** [Gemini structured outputs docs](https://ai.google.dev/gemini-api/docs/structured-output)

## 8. `output_schema` validation is strict — no partial output

ADK raises `pydantic.ValidationError` if the model's response doesn't match
the schema exactly. No partial credit.

**Fix:** Use `after_model_callback` to catch `ValidationError` and either:
- Return a fallback `LlmResponse` with safe defaults
- Set a state flag for the parent agent to handle
- Wrap in `LoopAgent(max_iterations=2)` for retry

**Source:** [adk-python Discussion #3759](https://github.com/google/adk-python/discussions/3759)

## 9. Pydantic `ConfigDict(extra="forbid")` and Gemini

Gemini may add unexpected fields to its JSON output. If your Pydantic model
uses `extra="forbid"`, these extra fields cause `ValidationError`.

**Recommendation:** For `output_schema` models, consider `extra="ignore"` on the
schema used at runtime, while keeping `extra="forbid"` on the API boundary models.

## 10. Streaming not supported with structured output

Gemini does not support streaming structured output. The entire JSON response
is returned at once, not chunk by chunk. Plan for this in latency budgets.

**Source:** [pydantic-ai#1237](https://github.com/pydantic/pydantic-ai/issues/1237)

## 12. `thinking_budget=0` + few-shot examples = hallucination

**Symptom:** Formatter ignores the actual input data and generates output based
on few-shot examples instead. Carrier names, locations, shipment counts all
come from examples, not the briefing.

**Cause:** `thinking_budget=0` skips reasoning entirely — the model pattern-matches
from examples. Combined with a long prompt where the actual data is appended
AFTER examples, the model gives more weight to examples than to the real input.

**Fix (two parts):**
1. Place actual input data BEFORE the instruction/examples:
   `instruction="Classify this:\n{briefing}\n" + taxonomy_and_examples`
2. Set `thinking_budget=1024` on the formatter so it reasons about the input

**Sources:**
- [Gemini prompting strategies](https://ai.google.dev/gemini-api/docs/prompting-strategies) — "too many examples → overfit"
- [Gemini 2.5 Flash Developer Guide](https://www.shareuhack.com/en/posts/gemini-2-5-flash-developer-guide-2026) — budget=0 skips reasoning
- [Gemini 2.5 Flash quality degradation](https://discuss.ai.google.dev/t/gemini-2-5-flash-quality-degradation/89619)

---

## Summary: Our mitigations in this project

| Bug | Our mitigation |
|-----|---------------|
| additionalProperties (#1) | `list[KeyFact]` instead of `dict[str, Any]` |
| ToolContext (#2) | Runtime import with `# noqa: TC002` |
| Callback naming (#3) | Exact names + `# noqa: ARG001` |
| output_schema + tools (#5) | Two-agent SequentialAgent pattern |
| Tool history breaks schema (#6) | `_clear_history` callback + `include_contents="none"` |
| Schema complexity (#7) | Flat models, short enums, <= 2 nesting |
| Validation strictness (#8) | Post-classification fallback in `_after_agent` |
