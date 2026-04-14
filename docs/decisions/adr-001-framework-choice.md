---
title: "ADR-001: Agent Framework — Google ADK"
type: deep-dive
domains: [supply-chain, agent-architecture]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Architecture-Decision-Analysis]]", "[[Supply-Chain-Research-Sources]]"]
---

# ADR-001: Agent Framework — Google ADK over BeeAI/LangGraph

## Status
Accepted

## Date
2026-04-10

## Context

The Supply Chain Exception Triage product requires a multi-agent orchestration framework to coordinate a Classifier, Impact Agent, and Module Coordinator. The framework choice drives every subsequent architectural decision (prompt format, memory layer, streaming, UI).

Forces at play:
1. **Submission constraint**: We are building for the Google Solution Challenge. Judges favor native Google Cloud integrations.
2. **Timeline**: Prototype due Apr 24, 2026 (14 days). Solo builder. Python-only skill set.
3. **Multi-agent needs**: Parent-child delegation, LLM-driven routing, session state handoff.
4. **Research depth**: 163 existing vault notes on ADK (see [[Supply-Chain-Research-Sources]]). BeeAI notes are thinner.
5. **Gemini alignment**: We use Gemini 2.5 Flash; a framework with first-class Gemini support is a clean fit.

## Decision

**Use Google ADK (Agent Development Kit) as the agent framework**, specifically `LlmAgent` + `sub_agents` AutoFlow for Coordinator → Classifier / Impact delegation.

## Alternatives Considered

- **BeeAI Framework (IBM)**: Open-source multi-agent framework. Rejected because workflows module is marked "under construction" per official docs, agent interop to Google ADK would require A2A protocol bridging (extra complexity), and no native Gemini integration. Judges for a Google Solution Challenge would view IBM tooling as odd.
- **LangGraph (LangChain)**: Mature, graph-based orchestration, production-ready. Rejected because it adds significant conceptual overhead (StateGraph + checkpointers + nodes) for what is fundamentally a 3-step delegation chain, doesn't differentiate us for a Google hackathon, and our ADK research base is deeper than our LangGraph base.
- **Custom FastAPI-only orchestration (no framework)**: Most flexible. Rejected because we'd hand-build session state, streaming, and delegation logic that ADK provides for free — a net time loss, not a save.
- **CrewAI**: Rejected because it is optimized for role-based collaborative teams, not deterministic coordinator-specialist delegation patterns.

## Consequences

### Positive
- Native Gemini integration — one less auth/SDK layer
- Built-in AutoFlow delegation means Coordinator doesn't need hand-written routing code
- `adk web` gives us a zero-code UI for Sprints 1–4 (see ADR-007)
- Strong Solution Challenge judging signal ("Google-native")
- Session state + callback hooks (`before_model_callback`) cleanly solve our dynamic context injection need from [[Supply-Chain-Agent-Spec-Coordinator]]

### Negative
- ADK is new (2025 release) — smaller community, fewer StackOverflow answers, potential undocumented bugs (tracked in `sprints/sprint-0/risks.md` Risk 4)
- Framework lock-in: the `MemoryProvider` and `agent_runner` abstractions in our file layout exist specifically to hedge this risk
- Some ADK primitives (e.g., `SequentialAgent`) are documented but unfamiliar; expect a learning curve in Sprint 3

### Neutral
- Team (solo builder) agrees to read `adk-samples` canonical hello-world before customizing
- All ADK version pins go in `pyproject.toml` with `==` (not `>=`) to avoid surprise breakage
- Framework-portability abstraction layer (`runners/agent_runner.py`) is mandatory — not optional

## References

- [Google ADK Multi-agent Docs](https://adk.dev/agents/multi-agents/)
- [Developers Guide to Multi-Agent Patterns in ADK](https://developers.googleblog.com/developers-guide-to-multi-agent-patterns-in-adk/)
- [BeeAI Framework Agents Module — status "under construction"](https://framework.beeai.dev/modules/agents)
- [IBM comparison: CrewAI vs LangGraph vs BeeAI](https://developer.ibm.com/articles/awb-comparing-ai-agent-frameworks-crewai-langgraph-and-beeai/)
- [[Supply-Chain-Architecture-Decision-Analysis]] — full 5-framework analysis
- [[Supply-Chain-Agent-Spec-Coordinator]] — framework choice assumptions baked into spec
- [[Supply-Chain-Research-Sources]] Topic 1 — essential ADK reading list
