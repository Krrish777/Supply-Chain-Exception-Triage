---
title: "ADR-008: A2A Protocol — Always Scaffold, Never Hand-Write"
type: deep-dive
domains: [supply-chain, agent-architecture, interop]
last_updated: 2026-04-14
status: active
confidence: high
sources:
  - "[[Supply-Chain-Architecture-Decision-Analysis]]"
  - https://github.com/a2aproject/A2A
  - https://github.com/a2aproject/a2a-python
  - https://google.github.io/adk-docs/a2a/
  - https://google.github.io/adk-docs/a2a/intro/
  - https://codelabs.developers.google.com/intro-a2a-purchasing-concierge
  - memory/reference_a2a_protocol.md
---

# ADR-008: A2A Protocol — Always Scaffold via `agent-starter-pack`, Never Hand-Write

## Status
Accepted

## Date
2026-04-14

## Context

The product's long-term commitment (captured in `memory/project_architecture_a2a_vendor_free.md` and CLAUDE.md §Architecture commitments) is for agents to be exposable as network services via Google's Agent-to-Agent (A2A) protocol — JSON-RPC 2.0 over HTTP(S) with `AgentCard` discovery at `.well-known/agent.json`. Two concrete drivers:

1. **Module-Ready Orchestrator (ADR-001 + D+F architecture).** Post-hackathon, a Meta-Coordinator will compose multiple modules. That composition can be in-process (sub_agents list) OR cross-process (A2A). A2A keeps the door open for teams to deploy modules independently.
2. **Framework-swap tolerance (CLAUDE.md architecture commitment #3).** If we ever swap ADK for LangGraph / CrewAI / PydanticAI, A2A is the interop protocol between our new core and any remaining ADK-native modules (or vice versa).

A2A was **not** covered by ADR-001 (which is framework choice, ADK). This ADR captures A2A as an orthogonal protocol decision and the operational rule that flows from the Python SDK's instability.

The A2A Python SDK (spec 0.3 stable, 1.0 alpha as of 2026-04) has shifting API surface across versions — `AgentCard` schema, `to_a2a()` signature, `A2aAgentExecutor` import paths, the `A2AFastAPIApplication` mount pattern — all have moved between releases. Hand-written A2A plumbing has broken repeatedly in community projects during minor version upgrades.

## Decision

**When an A2A surface is required, we scaffold it — we do not hand-write it.** Operational rule:

```bash
uvx agent-starter-pack create <project-name> \
  --agent adk_a2a \
  --deployment-target <target> \
  --prototype \
  -y
```

Or to add A2A to an existing project:

```bash
uvx agent-starter-pack enhance . --agent adk_a2a -y
```

Then lift the generated A2A-specific files (`AgentCard` JSON, server executor glue, mount wiring) into our tree. Never edit the A2A-type imports or the `AgentCardBuilder` / `A2aAgentExecutor` / `A2AFastAPIApplication` boilerplate manually.

Sprint 0 does **not** build A2A surface. A2A becomes load-bearing at the earliest for:
- **Sprint 3 (Coordinator + full pipeline)** — IF sub-agents live in separate processes (current plan: in-process, so no A2A yet)
- **Post-hackathon Meta-Coordinator** — when Port Intelligence Module joins, A2A is the likely interop path

## Alternatives Considered

- **Hand-write A2A imports + AgentCard in our agent.py** — rejected. Minor-version drift has broken exactly this pattern in community projects. Saves no time, costs hours per ADK release.
- **Wrap agents with a custom HTTP/JSON-RPC layer of our own** — rejected. Reinvents A2A poorly, locks us out of the A2A ecosystem, doesn't satisfy the interop goal.
- **Defer A2A entirely to post-hackathon** — considered. The *surface* can be deferred. But the *rule* (when we do it, scaffold not hand-write) needs to be written down now so future-us doesn't reinvent the failure mode.
- **Use a different protocol (gRPC, tRPC, custom)** — rejected. A2A is the Google-native interop story; aligns with ADR-001 (ADK-native framework choice) and our Solution Challenge "Google-native" credibility signal.

## Consequences

### Positive
- A2A plumbing breakage during ADK upgrades becomes a re-scaffold, not a debug session.
- Agent framework portability goal (CLAUDE.md #3) has a concrete interop story on the table without implementation cost until needed.
- Solution Challenge "Google-native" signal strengthened — we're aligned with the A2A standard Google published.
- `memory/reference_a2a_protocol.md` already tracks the canonical URLs; Sprint 4+ lookup is cheap.

### Negative
- Tied to the `agent-starter-pack` CLI's quality. If ASP lags a new A2A version or misgenerates, we're blocked on ASP fixes.
- The `adk_a2a` template defaults may not match our folder layout — lifting files will require path rewrites (non-trivial but mechanical).
- If A2A Protocol v1.0 becomes the community default and differs materially from 0.3, our early scaffolds will need regeneration.

### Neutral
- `a2a-sdk` Python package is not added to `pyproject.toml` in Sprint 0. Added when (and only when) A2A surface is actually scaffolded.
- A2A surface will live in `runners/` — agent-facing exposure plumbing, not inside `modules/triage/agents/`. This matches CLAUDE.md import-rule: A2A is a boundary concern, not an agent concern.
- The `adk-scaffold` skill's Critical Rules section ("NEVER write A2A code from scratch") is the enforcement anchor for this ADR.

## When this ADR fires (operationally)

- Any PR that adds `from a2a.*` imports → require scaffold trace in PR description
- Any ADK upgrade → re-test A2A surface (if present) via smoke test, re-scaffold if broken
- Any new module that needs cross-process interop → scaffold first, port after

## References

- [a2aproject/A2A](https://github.com/a2aproject/A2A) — protocol spec + reference implementation
- [a2aproject/a2a-python](https://github.com/a2aproject/a2a-python) — Python SDK (spec 0.3 stable, 1.0 alpha)
- [ADK A2A integration docs](https://google.github.io/adk-docs/a2a/)
- [ADK A2A intro](https://google.github.io/adk-docs/a2a/intro/)
- [A2A Python tutorial](https://google-a2a.github.io/A2A/latest/tutorials/python/1-introduction/)
- [Purchasing Concierge codelab](https://codelabs.developers.google.com/intro-a2a-purchasing-concierge)
- [Google announcement](https://developers.googleblog.com/en/a2a-a-new-era-of-agent-interoperability/)
- `adk-scaffold` skill §Critical Rules (the "never hand-write" enforcement anchor)
- ADR-001 (Framework choice — ADK) — orthogonal; A2A applies inside and across ADK
- ADR-002 (Memory layer — Supermemory) — unaffected
- `memory/reference_a2a_protocol.md` (project memory)
