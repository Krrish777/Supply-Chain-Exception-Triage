---
title: "ADR-007: UI Strategy — adk web Then React"
type: deep-dive
domains: [supply-chain, frontend, ui]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]", "[[Supply-Chain-Architecture-Decision-Analysis]]"]
---

# ADR-007: UI Strategy — `adk web` for Sprints 1–3, Custom React in Sprint 5

## Status
Accepted

## Date
2026-04-10

## Context

The prototype needs a UI for judges to interact with. Options range from "zero UI, CLI only" to "full custom React SPA with streaming chat interface". The solo builder has ~14 days and limited frontend bandwidth.

Forces:
- Must have SOMETHING judges can click on (per SDG scoring)
- Demo video needs visible agent activity
- Backend agent pipeline (Sprints 1–3) must be validated in isolation before wiring to a custom UI
- React/Next.js adds complexity: routing, state, SSE client, auth integration, deploy pipeline
- `adk web` is a zero-code UI that ships with Google ADK — it displays agent traces, tool calls, session state

## Decision

**Two-phase UI strategy:**

- **Sprints 1–3** (backend feature sprints): Use `adk web` as the developer-facing UI. Validate Classifier, Impact, and Coordinator by invoking the hello_world → full triage chain in `adk web` and inspecting the agent trace.
- **Sprint 5** (deployment + frontend): Build a minimal custom React frontend with an SSE client consuming `/triage/stream`, styled for the demo video. Deploy alongside the Cloud Run backend.

This is NOT a "defer UI to the end" decision — it's a "validate backend with ADK's built-in UI first, then build demo-worthy UI last" decision.

## Alternatives Considered

- **React from Day 1**: Rejected — front-loads the complexity before the backend even exists. Solo builder would context-switch constantly. `adk web` gives us a free UI for 3 sprints.
- **Never build React, demo via `adk web`**: Rejected — `adk web` looks like a developer tool, not a product. Judges reviewing 500 submissions will not be impressed by a trace viewer.
- **Streamlit**: Considered. Rejected because Streamlit's streaming story is weak compared to React + EventSource, and Streamlit apps look like Streamlit apps (judges notice).
- **Gradio**: Similar to Streamlit, slightly better for chat UIs. Rejected for the same streaming limitations.
- **Next.js + tRPC**: Overkill; adds framework complexity for a prototype that has one endpoint.
- **Vue / Svelte**: Rejected — builder has more React familiarity, and familiar tools ship faster in hackathons.

## Consequences

### Positive
- Sprints 1–3 engineering focus is pure backend — no frontend distraction
- `adk web` gives instant debugging feedback (visible tool calls, session state, agent trace) which accelerates TDD
- Sprint 5 builds React from a **known-good backend** — less debugging surface
- Demo video can include both "developer view" (adk web trace) and "user view" (React) for narrative variety
- If Sprint 5 runs out of time, we fall back to `adk web` for the demo — named Should-Have trim per sprint plan

### Negative
- Sprint 5 has 2 days to build React + deploy to Cloud Run — tight budget
- Two UIs means two auth integrations (Firebase Auth in React) — one more thing
- `adk web` may not look production-grade; if judges check the intermediate sprints' screenshots, they'll see a dev tool

### Neutral
- Sprint 5 PRD must name explicit React scope: single-page chat UI, Firebase Auth login, SSE client for `/triage/stream`, minimal styling (Tailwind + shadcn/ui pre-built components) — NO routing, NO state management library, NO animations beyond loading spinners
- Frontend code lives in a separate `frontend/` directory; not inside `src/` (which is Python backend only)
- Sprint 5 ADR (future) will refine deployment specifics (Firebase Hosting vs Cloud Run static, etc.)

## References

- [Google ADK `adk web` docs](https://google.github.io/adk-docs/) — zero-code UI for agent development
- [shadcn/ui](https://ui.shadcn.com/) — React component library for Sprint 5
- [FastAPI + EventSource React example](https://fastapi.tiangolo.com/advanced/custom-response/#streamingresponse)
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — Sprint 5 scope and Should-Have trims
- [[Supply-Chain-Architecture-Decision-Analysis]] — D+F architecture including demo impact weighting
- ADR-004 (Streaming) — the SSE contract that React will consume in Sprint 5
