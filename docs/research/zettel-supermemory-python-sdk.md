---
title: Supermemory Python SDK — scoping model, async shape, multi-tenant mapping
type: zettel
tags: [memory, supermemory, multi-tenant, sdk, zettel]
status: first-principles
last_updated: 2026-04-14
confidence: medium
sources:
  - https://docs.supermemory.ai/sdks/python
  - https://pypi.org/project/supermemory/
  - https://github.com/supermemoryai/supermemory
related:
  - "[[adr-002-memory-layer]]"
  - "[[zettel-firestore-multi-tenant]]"
  - "[[Supply-Chain-Agent-Spec-Coordinator]]"
---

# Supermemory Python SDK — scoping model, async shape, multi-tenant mapping

> **TL;DR.** Supermemory scopes memory with *container tags* (loose labels), not a first-class tenant primitive. For our multi-tenant project, we map `company_id → container_tag`. The Python SDK is `supermemory` on PyPI, built on `httpx`, sync + async clients, Python 3.9+.

## First principles

**Why memory scoping exists.** Agent memory is a shared pool of semantic embeddings. Without scoping, user A's sensitive exception history leaks into user B's retrieval. The scoping mechanism is the *physical boundary* that prevents leak.

**Two scoping mental models:**
1. **Namespace-based** (Firestore's `request.auth.token.tenantId` model) — tenant ID is a first-class index, queries automatically filter, storage-layer enforced.
2. **Tag-based** (Supermemory's model) — tenant ID is just a label you attach, and you filter on it at query time. Weaker: if you forget to pass the tag, you leak.

**Consequence for us:** Every single Supermemory call must pass `container_tags=[company_id]`. No exceptions. Enforcement has to live in *our adapter*, not the SDK — wrap the client so `company_id` is required on every method and silently appended.

## SDK shape (from docs)

```python
from supermemory import Supermemory  # sync
from supermemory import AsyncSupermemory  # async — httpx-backed

client = Supermemory(api_key=os.environ["SUPERMEMORY_API_KEY"])

# Writing memory
client.memories.create(
    content="Coordinator observed NH-48 stoppage on 2026-04-14",
    container_tags=["company_abc123"],         # ← our tenant boundary
    metadata={"exception_id": "ev_001"},
)

# Semantic search
results = client.memories.search(
    query="NH-48 disruptions last 30 days",
    container_tags=["company_abc123"],         # ← required, or we leak
    limit=5,
)
```

Both sync and async paths are available; pick async for ADK tool integration (tools are async in ADK).

## Project implications

1. **`MemoryProvider` abstraction (per ADR-002) hides Supermemory.** Agents never see `supermemory` imports. They call `self.memory.fetch_user_context(user_id, company_id)` — adapter handles container tag construction.
2. **`SupermemoryAdapter` signature enforces company_id.** Every method takes `company_id: str` as a required positional (not keyword-with-default) so forgetting it is a type error, not a silent leak.
3. **Rate-limit and retry policy unknown from public docs.** Check during Sprint 4 real-integration prep — add Risk 12 to `sprints/sprint-0/risks.md`.
4. **Sprint 0 uses `FakeSupermemoryClient`.** Same interface as real adapter. Lives in `tests/fixtures/fake_supermemory.py`. Sprints 1-3 run entirely against it.
5. **Firestore DIY fallback (ADR-002 "Should-Have trim")** — if Sprint 4 real integration stalls, we implement the same `MemoryProvider` interface over Firestore with Vertex AI `text-embedding-004`. Interface discipline from Day 1 is what makes this fallback possible without agent rewrites.

## Gotchas flagged for later

- **Client-side test mode.** The SDK is pure HTTPX — no environment-variable toggle like `FIREBASE_AUTH_EMULATOR_HOST`. Tests must use the `FakeSupermemoryClient`, never the real client with a "test mode" flag.
- **Container tags are not validated by the API.** Passing `"COMPANY_abc123"` (case mismatch) will silently create a separate bucket. Lowercase-and-strip at adapter boundary.
- **Supermemory was founded 2024** (young company). Pin SDK version in `pyproject.toml`. Don't float.

## Further research (first-principles-friendly)

- **Embedding model choice + drift.** Supermemory uses its own embedding model internally. If it changes, semantic-lookup recall for past exceptions may shift. Can we ask Supermemory to pin the embedding model? Open question.
- **Deletion semantics.** If a company offboards, how do we purge? Deleting by container tag? API support for `memories.delete(container_tags=[...])`? Not yet verified.
- **Multi-tenant at scale.** The tag model assumes small number of tenants. Does it scale to 10k+ tenants? Check with Supermemory team before Tier 2.
- **Cost envelope.** Free tier limits for a hackathon demo vs real usage. Need a rate budget for live demo (judge session = ~50 memory ops).
- **Compare: Mem0 `user_id` scoping** — does Mem0's first-class `user_id` scoping give us a cleaner adapter? Worth a re-evaluation gate at Sprint 4 if Supermemory integration is rocky.
- **LangChain's 3-layer memory model** (referenced in ADR-002) — working vs episodic vs semantic memory. Our current architecture treats Supermemory as a single layer. Is that right?
