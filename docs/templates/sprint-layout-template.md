# Sprint layout

Every sprint lives under `docs/sprints/sprint-N/` and produces **nine** artifacts per ADR-006's Spiral SDLC Plan / Risk / Engineer / Evaluate phases.

```
docs/sprints/sprint-N/
├── prd.md             Plan     — PRD (from prd-template.md)
├── test-plan.md       Plan     — Given/When/Then cases (from test-plan-template.md)
├── risks.md           Risk     — pre-mortem (probability × severity × mitigation)
├── adr-*.md           Risk     — one per non-trivial decision (from adr-template.md in docs/decisions/)
├── security.md        Engineer — OWASP checklist instance + threat deltas
├── impl-log.md        Engineer — dev diary of what was built in what order, surprises
├── test-report.md     Engineer — pytest + coverage + security scan outputs
├── review.md          Evaluate — AI code-review findings + user review
└── retro.md           Evaluate — Start/Stop/Continue (from retrospective-template.md)
```

## Phase → artifact mapping

| Phase | Artifacts | Gate |
|---|---|---|
| Plan | `prd.md` + `test-plan.md` | User approves PRD before coding starts |
| Risk | `risks.md` + `adr-*.md` | User approves ADRs for non-trivial decisions |
| Engineer | `security.md` + `impl-log.md` + `test-report.md` | §17 acceptance criteria green |
| Evaluate | `review.md` + `retro.md` | User confirms sprint closed |

## File naming

- `sprint-0` through `sprint-6` — the planned hackathon cycle.
- Post-hackathon continues as `sprint-7`, `sprint-8`, ...
- Within a sprint, ADRs that apply globally live in `docs/decisions/adr-NNN-<topic>.md` (not inside the sprint folder) because they outlive the sprint.
- Sprint-scoped ADRs (rare — e.g. a one-off decision that applies only within this sprint's work) can live at `docs/sprints/sprint-N/adr-local-<topic>.md`.

## Authoring order within a sprint

1. **Before coding:** `prd.md` → `test-plan.md` → `risks.md`.
2. **If risks.md surfaces non-trivial decisions:** one `adr-*.md` per decision.
3. **Gate 1:** user approval of PRD + ADRs.
4. **During coding (Engineer phase):** append to `impl-log.md` as you go; keep it terse (1-3 bullets per sub-phase).
5. **At gate:** run pytest / ruff / mypy / lint-imports / security scans. Capture output into `test-report.md`. Run OWASP checklist → `security.md`.
6. **Post-gate:** trigger `superpowers:code-reviewer` (or equivalent); capture findings in `review.md`.
7. **Sprint close:** `retro.md` with Start/Stop/Continue.

## Don't skip artifacts

If a sprint produces fewer than 9 artifacts, flag the missing ones in the retro — either the sprint was genuinely smaller (fine; note it) or we cut corners (not fine; fix next sprint).

The 9-artifact discipline is one of the hackathon credibility signals per ADR-006 §Consequences.
