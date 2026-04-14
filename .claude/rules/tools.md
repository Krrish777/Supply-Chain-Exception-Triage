---
description: Tool design — return contract, signature, error classification, per-turn caching
paths: ["src/supply_chain_triage/modules/*/tools/**", "src/supply_chain_triage/modules/*/agents/*/tools.py"]
---

# Tool rules

A tool's docstring is its LLM-facing description. Its type hints are its parameter schema. Treat these as prompt engineering, not documentation — the model reads them to decide when and how to call the tool.

## 1. Return contract

Tools always return a JSON-serializable dict in one of these shapes:

```python
{"status": "success", "data": {...}}
{"status": "error", "error_message": "..."}
{"status": "retry", "retry_after_ms": 1500}
```

**Never** return `DocumentSnapshot`, `DocumentReference`, or raw SDK objects. `.to_dict()` + Pydantic `.model_dump()` at the boundary.

## 2. Signature

```python
async def get_exception(
    exception_id: str,
    tool_context: ToolContext,
) -> dict:
    """Retrieve an exception by ID.

    Args:
        exception_id: Firestore doc ID for the exception (ULID, 26 chars).

    Returns:
        {"status": "success", "data": ExceptionRecord dict} with keys
        id, status, severity, carrier_id, created_at — or
        {"status": "error", "error_message": "<reason>"} on failure.
    """
```

- **Name** in `verb_noun` form.
- **Docstring first line**: what it does and when to call it.
- **Args section**: semantic meaning, units, enums inline.
- **Returns section**: document the dict keys — LLMs reliably exploit this shape.
- **`ToolContext` as last arg** (optional but recommended) gives access to `state`, `actions` (`escalate`, `transfer_to_agent`), `save_artifact`.

## 3. Async for I/O

Any tool that hits Firestore, HTTP, Gemini, or any remote service uses `async def`. Sync I/O stalls `ParallelAgent` and blocks the event loop. Pure-compute tools may be sync.

## 4. No retry loops inside tools

Retries belong in `LoopAgent` or `before_tool_callback` with an explicit budget (max 2). A tool that loops internally fights the ADK runtime's visibility — ADK can't see the attempts.

## 5. Error classification at the boundary

Catch expected exceptions, classify, return the appropriate status:

| Class | Source | Return |
|---|---|---|
| Transient | 429, 503, Firestore contention, network timeout | `{"status": "retry", "retry_after_ms": N}` |
| Permanent | 4xx semantic (not found, schema mismatch, invalid arg) | `{"status": "error", "error_message": "..."}` |
| Unexpected | Anything else | Let it raise — ADK emits an error `Event` |

Never swallow exceptions silently. Never return partial data on error.

## 6. Per-turn cache for Firestore

Avoid N+1 inside `SequentialAgent` by caching reads in `tool_context.state`:

```python
cache_key = f"cache:exception:{exception_id}"
if cached := tool_context.state.get(cache_key):
    return {"status": "success", "data": cached}

doc = await db.collection("exceptions").document(exception_id).get()
if not doc.exists:
    return {"status": "error", "error_message": f"Exception {exception_id} not found"}

data = doc.to_dict() | {"id": doc.id}
tool_context.state[cache_key] = data
return {"status": "success", "data": data}
```

`cache:` is not in the prefix table because it's not a state *scope* — it's a convention within session scope. Prune with `temp:cache:...` if the cache must not persist across invocations.

## 7. What goes in the tool vs the agent prompt

- **Tool:** the mechanical "how" — fetch, query, transform.
- **Agent prompt:** the policy "when to call".
- **`before_tool_callback`:** policy guards (authz, cost cap, mock in tests).
- **`after_tool_callback`:** normalization, secret masking.

If a tool's docstring starts mentioning *when* to call it in terms of agent state, that logic probably belongs in the prompt.
