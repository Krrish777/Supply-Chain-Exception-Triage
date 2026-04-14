---
title: "Architecture Decision Analysis — Summary Digest"
type: summary
source: "[[Supply-Chain-Architecture-Decision-Analysis]] (vault, 356 lines)"
last_updated: 2026-04-14
confidence: high
---

# Architecture Decision Analysis — Digest

Two-page condensation of the 5-framework vault analysis (SWOT + Pre-Mortem + Weighted Decision Matrix + Six Thinking Hats + MECE) that produced the **D + F Combined** architecture committed to in `docs/product_recap.md`. Keep this file as the reference; the full analysis is in the Obsidian vault.

## What was being decided

Two original approaches:

- **Approach B — Orchestrator with modular design.** 4-5 agents (Coordinator → Classifier → Strategy → Route Optimizer → Communication). Clean I/O schemas. Single coordinator. Ships fast; adding a second module later requires coordinator refactor.
- **Approach C — Full modular agent platform.** Meta-coordinator + per-cluster coordinators + specialists (5-7+ agents). Best long-term architecture. Highest hackathon risk.

## What the frameworks said

| Framework | Verdict | Load-bearing insight |
|---|---|---|
| SWOT | B wins | C inherits all of B's weaknesses and adds its own. C's unique strengths only pay off *if shipped complete*. |
| Pre-Mortem | B wins | C has 9 failure vectors vs B's 5. C-unique failures are high-probability, high-severity (meta-coordinator eats 2 weeks; half-built Module 2 worse than no Module 2; routing bugs cascade). |
| Weighted Decision Matrix | B wins 7.70 vs 6.74 combined | B wins hackathon decisively (8.00 vs 6.10). C wins product/startup by slim margin (7.70 vs 7.25). C's product advantage is not large enough to justify its hackathon risk. |
| Six Thinking Hats | **D emerged (new)** | Green Hat produced "Module-Ready Orchestrator" — C's design philosophy at B's complexity. Blue Hat: "architecture is internally important but externally invisible." |
| MECE | **Neither — shared blind spot** | Zero user interviews. More urgent than B-vs-C. |

## The discovered third option — Alternative D: Module-Ready Orchestrator

Build Exception Triage as a **self-contained module** with C's internal structure and clean boundaries, but **without** the meta-coordinator layer.

```
[Exception Triage Module]              ← C's module structure
    └── Module Coordinator             ← Just this module's brain, not meta
        ├── Classifier Agent
        ├── Impact Agent
        ├── Resolution Agent           ← Generator-Judge + Route Optimization
        └── Communication Agent

Post-hackathon:
[Meta-Coordinator]                     ← Added when Module 2 exists
    ├── [Exception Triage Module]      ← Already built; wrap it
    └── [Port Intelligence Module]     ← New module, same pattern
```

**Why D wins:**
- ✅ Clean module boundaries (C's strength)
- ✅ Achievable scope for solo 4-week build (B's strength)
- ✅ Migration path to full platform (C's goal preserved)
- ✅ 5 agents, not 7+ (B's feasibility)
- ✅ Route Optimization stays prominent inside Resolution Agent (B's demo asset)
- ❌ No "platform" demo at hackathon (C's sacrifice — explicit)
- ✅ "Platform-ready architecture" is still a pitchable talking point

## The second discovered option — Alternative F: Progressive Enhancement

Design in tiers where each tier is a complete, shippable product:

- **Tier 1** (Week 1-2): Classifier + Impact → "AI-powered exception classification" — shippable
- **Tier 2** (Week 2-3): + Resolution (Generator-Judge) → "AI-powered exception triage" — shippable
- **Tier 3** (Week 3-4): + Route Optimization + Communication + Dashboard → "autonomous exception response" — shippable

**Load-bearing property: you literally cannot fail to ship something.** Tier 1 alone is a submission. Tier 2 alone is a submission. This eliminates timeline risk by turning it into scope-cut decisions at known checkpoints.

## Final verdict — D + F Combined

**"Module-Ready Orchestrator with Progressive Enhancement."**

This is the committed architecture in `docs/product_recap.md` and the shape our `modules/triage/` folder structure physically implements.

Why it wins across all frameworks (as stated in the vault synthesis):
- SWOT: B's achievability + C's modularity
- Pre-Mortem: tiered delivery means we can't fail to ship
- Decision Matrix: would score ~8.5 hackathon (higher than both B and C)
- Six Hats: resolves Green Hat alternative with Yellow Hat optimism
- MECE: the parallel user-interview track (part of F's Week 1-2) fills the biggest blind spot

## Three critical blind spots surfaced by MECE (not resolved by architecture choice)

1. **Zero product-market validation** — 163 research notes, zero interviews with actual 3PL coordinators. Approach-independent. More urgent than B-vs-C. Product recap's "Deferred Blind Spots" captures this; goal is to address before May 29 Top 100 deadline.
2. **User acquisition unaddressed** — "small 3PL coordinators" is a segment description, not a channel. Possible channels: LinkedIn outreach, r/FreightBrokers / r/logistics, 3PL associations, cold email, trade shows.
3. **Email privacy / compliance** — product reads carrier emails, customer escalations. Hackathon: synthetic data, no concern. Product: needs compliance strategy before real data flows.

## Cross-references (vault)

- `[[Supply-Chain-Product-Recap]]` — living product overview incorporating this decision
- `[[Supply-Chain-Execution-Roadmap]]` — 4-week tiered build sequence
- `[[Supply-Chain-Judging-Strategy]]` — scoring criteria that fed the decision-matrix weights
- `[[Supply-Chain-Problem-First-Principles]]` — 5-layer problem model validating Exception Triage focus
