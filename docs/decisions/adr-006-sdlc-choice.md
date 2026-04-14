---
title: "ADR-006: SDLC Model — Spiral"
type: deep-dive
domains: [supply-chain, sdlc, project-management]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]"]
---

# ADR-006: SDLC Model — Spiral (Boehm, 1986)

## Status
Accepted

## Date
2026-04-10

## Context

A 14-day hackathon project still benefits from a named, deliberate SDLC model. The alternatives are Waterfall, Agile/Scrum, Kanban, Lean, Incremental, or Spiral. Solo builders often default to "chaotic vibe coding" — this ADR picks a model intentionally.

Forces:
- High architectural uncertainty (ADK is new, Supermemory is young, streaming is unproven)
- Multiple risks that need explicit analysis per iteration
- Clear per-sprint deliverables (demo-able features)
- Documentation requirements for judges (9 artifacts per sprint)
- No external stakeholders requiring formal scope control
- User explicit requirement (captured in project memory): "Spiral SDLC"

## Decision

**Use the Spiral SDLC model** (Boehm, 1986). Each sprint is one full spiral iteration through four phases:

1. **Plan**: Research (vault + web), PRD, Test Plan, user review
2. **Risk**: Pre-mortem analysis, ADRs, threat model, prototyping uncertain bits
3. **Engineer**: Strict TDD cycles, security checks, documentation-as-code
4. **Evaluate**: Test report, AI code review, user review, retrospective

Seven sprints (0 through 6) plus a buffer day = 14 days total.

## Alternatives Considered

- **Agile Scrum**: Rejected — sprint ceremonies (standup, planning, retro) don't fit a solo builder, and Scrum assumes a backlog with grooming that we don't need.
- **Kanban**: Rejected — too loose; no natural breakpoints for the 9 artifacts per sprint and no explicit risk phase.
- **Waterfall**: Rejected — all the architectural uncertainty means we'd commit to decisions before learning they were wrong.
- **Lean Startup (Build-Measure-Learn)**: Rejected because user interviews are a parallel track, not the primary loop; we're in a hackathon with a fixed deadline, not validating a startup hypothesis.
- **Ad-hoc / no formal model**: Rejected — solo builders who don't pick a model end up in a debugging swamp by Day 10.

## Consequences

### Positive
- **Explicit risk phase per sprint** — Boehm's key insight: make risk analysis a named step, not an afterthought. Our Pre-Mortem + ADR + threat-model artifacts satisfy this.
- **Each iteration is shippable** — aligns with Progressive Enhancement (Tier 1 / 2 / 3) from [[Supply-Chain-Architecture-Decision-Analysis]]
- **Built-in review gates** — evaluate phase forces a stop-and-review checkpoint 7 times, catching drift early
- **Documentation follows automatically** — the 9 artifacts per sprint map 1:1 to spiral phases
- **Plays well with strict TDD** (ADR-005) — the Engineer phase is where TDD lives

### Negative
- **Phase overhead** — each sprint has ~20% of its time on non-coding activities (PRD, ADR, retro). On a 2-day sprint that's ~3 hours of documentation per sprint.
- **Can feel bureaucratic** — the ceremonial structure is valuable for judges and future-self, less for throughput
- **Requires discipline** — tempting to skip "Evaluate" when you're behind. The 9-artifact checklist is the forcing function.

### Neutral
- Sprint 0 is intentionally flexible (2.5–3 days) because foundation work has more risk and variable duration
- Sprints 1–6 are 2 days each — fixed budget, scope trims if sprint slips
- All per-sprint docs live in `docs/sprints/sprint-N/` (9 files × 7 sprints = 63 files)
- Retrospectives feed forward — each retro's "Start/Stop/Continue" informs the next sprint's PRD

## References

- Boehm, Barry (1986). "A Spiral Model of Software Development and Enhancement". ACM SIGSOFT Software Engineering Notes. [PDF](https://www.cs.unc.edu/techreports/86-017.pdf)
- [Wikipedia — Spiral model](https://en.wikipedia.org/wiki/Spiral_model)
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — the concrete 7-sprint instantiation of this model
- ADR-005 (Testing Strategy) — complements this ADR; strict TDD lives inside the Engineer phase
