---
title: "Sprint N PRD — <Feature Name>"
type: deep-dive
domains: [supply-chain, sdlc]
last_updated: YYYY-MM-DD
status: draft
confidence: medium
sources: []
---

# Sprint N PRD — <Feature Name>

> **Sprint window:** YYYY-MM-DD – YYYY-MM-DD
> **Audience:** A new contributor should be able to execute this sprint by following this PRD verbatim.

---

## 1. Objective

One paragraph. What will exist at the end of the sprint that doesn't exist now? How does this unblock the next sprint?

**One-sentence goal:** _Every subsequent sprint should be able to focus on feature delivery without revisiting the work in this sprint._

---

## 2. Scope (IN)

Bulleted sub-scopes, each small enough to be a 2-4 hour task:

### 2.1 <Sub-scope name>
- ...

### 2.2 <Sub-scope name>
- ...

---

## 3. Out-of-scope (deferred)

| Item | Deferred to | Reason |
|---|---|---|
| ... | Sprint N+1 | ... |

---

## 4. Resolved decisions

Any ambiguity in the scope that was resolved during PRD review. Cite the session note / ADR.

| # | Decision | Value | Rationale |
|---|---|---|---|
| 1 | ... | ... | ... |

---

## 5. Project directory tree

Only show the files this sprint adds or modifies.

```
supply_chain_triage/
├── ...
```

---

## 6. Implementation specs

Signatures + critical constraints (not full code bodies — strict TDD means tests are the spec).

---

## 7. Definition of Done per sub-scope

- [ ] 2.1: ...
- [ ] 2.2: ...

---

## 8. Acceptance criteria (sprint gate)

All must be ✅ before Sprint N+1 starts.

1. `uv run pytest` exits 0 with N tests passing.
2. `uv run ruff check .` green.
3. `uv run mypy src` green.
4. `uv run lint-imports` kept 5+ contracts.
5. ...

---

## 9. Rollback plan

If the sprint blows past its budget, cut scope in this order:

### Trim Level 1 — drop nice-to-haves
- ...

### Trim Level 2 — defer non-blocking infrastructure
- ...

### Trim Level 3 — minimum viable sprint
- ...

---

## 10. Risks

See `risks.md`. Top N:

| # | Risk | Prob | Severity | Mitigation |
|---|---|---|---|---|

---

## 11. Cross-references

- `./test-plan.md`
- `./risks.md`
- `../sprint-<N-1>/retro.md` — lessons from the previous sprint
- Relevant ADRs in `docs/decisions/`
- Relevant vault copies in `docs/research/`
