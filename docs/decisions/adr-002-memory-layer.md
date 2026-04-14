---
title: "ADR-002: Memory Layer — Supermemory"
type: deep-dive
domains: [supply-chain, agent-architecture, memory]
last_updated: 2026-04-10
status: active
confidence: medium
sources: ["[[Supply-Chain-Architecture-Decision-Analysis]]", "[[Supply-Chain-Research-Sources]]"]
---

# ADR-002: Memory Layer — Supermemory over Mem0 / Zep

## Status
Accepted

## Date
2026-04-10

## Context

The Exception Triage product needs persistent memory for:
1. **User context** — persona, language preference, working hours, communication style (per [[Supply-Chain-Agent-Spec-Coordinator]] Section 2–4)
2. **Learned behaviors** — override patterns, preferred priority ordering (populates over time)
3. **Customer exception history** — semantic lookup of "similar past exceptions" for the Impact Agent
4. **Session recall** — what the user just triaged, for follow-up questions

This is memory/pattern data, not operational/transactional data. Per the [LangChain Context Engineering separation principle](https://docs.langchain.com/oss/python/langchain/context-engineering), it should live outside Firestore.

Forces at play:
- Latency budget: sub-300ms retrieval to keep triage processing under 3 seconds total
- Solo builder, 14-day window — integration cost matters
- Multi-tenant (company_id scoping) is required
- Semantic search (embedding + similarity) is required for "similar past exceptions"

## Decision

**Use Supermemory as the memory layer**, accessed via a `MemoryProvider` interface (`src/supply_chain_triage/memory/provider.py`) with a `SupermemoryAdapter` implementation.

The interface exists so we can swap to Mem0, Zep, or a Firestore DIY fallback without touching agent code.

## Alternatives Considered

- **Mem0**: Popular (~50k GitHub stars), Python-native, good docs. Rejected (narrowly) because 2026 benchmarks show Supermemory's sub-300ms retrieval beats Mem0 by ~2x on the stateful-recall use case, and Supermemory's native multi-tenant scoping is cleaner than Mem0's user_id-only model.
- **Zep**: Knowledge-graph-based memory with strong temporal reasoning. Rejected because the temporal graph model is overkill for our use case and the hosted service's free tier is too restrictive for a hackathon.
- **LangMem / LetterAI**: Newer, less documentation. Rejected for risk reasons in a 14-day sprint.
- **Firestore DIY with embeddings (Vertex AI text-embedding-004)**: Zero new dependency, full control, cheapest. Rejected as primary choice (we'd reimplement retrieval, scoring, and decay) but **retained as explicit Sprint 3 fallback** if Supermemory integration stalls. This is a named Should-Have trim per [[Supply-Chain-Sprint-Plan-Spiral-SDLC]].

## Consequences

### Positive
- Native connectors for email/docs (useful in Tier 2 when we ingest carrier emails)
- Sub-300ms retrieval fits latency budget
- Multi-tenant scoping built-in (no custom company_id filter code)
- Managed service — no infra burden on solo builder
- Offloads embedding model + vector storage complexity

### Negative
- Vendor dependency on a relatively young company (Supermemory founded 2024)
- Less community content than Mem0 → harder to debug obscure issues
- Possible API rate limits on free tier during demo
- Adds one more secret to manage (`SUPERMEMORY_API_KEY`)

### Neutral
- `MemoryProvider` interface is mandatory — enforces portability from Day 1
- Sprint 3 PRD must include a go/no-go checkpoint at end of Day 1: if Supermemory integration doesn't work, fall back to Firestore DIY immediately, don't burn Day 2 fighting
- Test fixtures use `FakeSupermemoryClient` — all Sprint 0–2 tests work without network

## References

- [Supermemory](https://supermemory.ai/)
- [Mem0 vs Zep vs LangMem vs MemoClaw 2026 comparison](https://dev.to/anajuliabit/mem0-vs-zep-vs-langmem-vs-memoclaw-ai-agent-memory-comparison-2026-1l1k)
- [Mem0 vs Supermemory — LogRocket](https://blog.logrocket.com/building-ai-apps-mem0-supermemory/)
- [Best Memory APIs for Stateful AI Agents 2026](https://blog.supermemory.ai/best-memory-apis-stateful-ai-agents/)
- [LangChain Context Engineering — the 3-layer memory model](https://docs.langchain.com/oss/python/langchain/context-engineering)
- [[Supply-Chain-Research-Sources]] Topic 4 — memory framework reading list
- [[Supply-Chain-Architecture-Decision-Analysis]] — 5-framework analysis that scored memory choices
- [[Supply-Chain-Firestore-Schema-Tier1]] — the operational data that lives OUTSIDE Supermemory
