---
title: "Sprint Plan: Spiral SDLC for Tier 1 Prototype"
type: deep-dive
domains: [supply-chain, project-management, hackathon, sdlc]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Product-Recap]]", "[[Supply-Chain-Agent-Spec-Coordinator]]", "[[Supply-Chain-Agent-Spec-Classifier]]", "[[Supply-Chain-Agent-Spec-Impact]]", "[[Supply-Chain-Firestore-Schema-Tier1]]"]
---

# Sprint Plan: Spiral SDLC for Tier 1 Prototype

> [!abstract] The Plan
> 7-sprint Spiral SDLC execution plan for Tier 1 prototype (Apr 10-24). Each sprint is one full Spiral iteration (Plan → Risk → Engineer → Evaluate) with strict TDD and 9 documentation artifacts. Sprint 0 may bleed to 2.5-3 days (foundation takes as long as needed). Apr 24 deadline is fixed; Should-Have scope is flexible.

## Governing Principles

1. **Spiral SDLC model** — each sprint cycles through Plan → Risk → Engineer → Evaluate phases
2. **Strict TDD** — failing tests first, implementation second, refactor third
3. **Security-first** — every sprint has a security deliverable, not bolted on
4. **Document everything** — 9 artifacts per sprint for future developer onboarding
5. **Research-first PRDs** — web research + notes review + synthesis BEFORE writing each PRD
6. **AI + Human review gates** — superpowers:code-reviewer after each sprint + user review
7. **Per-sprint PRDs via superpowers:writing-plans** skill
8. **Apr 24 deadline is fixed** — Should-Have scope trims if sprints delay

## Spiral SDLC Cycle (Per Sprint)

```
    ┌─────────────────────────────────────────────┐
    │                                               │
    │     PLAN                        RISK          │
    │     - Research (notes + web)    - Pre-mortem  │
    │     - Write PRD                 - ADRs        │
    │     - Write Test Plan           - Threat      │
    │                                   model       │
    │              ↘               ↙                │
    │                 [DOCS]                        │
    │              ↗               ↘                │
    │                                               │
    │     EVALUATE                    ENGINEER      │
    │     - AI code review            - TDD cycle   │
    │     - User review               - Security    │
    │     - Retrospective               checks      │
    │                                 - Docs as     │
    │                                   code        │
    │                                               │
    └─────────────────────────────────────────────┘
```

## 7 Sprints Overview

| Sprint | Duration | Focus | PRD Topic | Gate |
|--------|----------|-------|-----------|------|
| **0** | Apr 10-12 (flexible) | Foundation + Security + Docs Infrastructure | "Secure Foundation PRD" | Everything set up, `adk web` hello_world works |
| **1** | Apr 12-13 | Classifier Agent | "Classifier Agent PRD" | NH-48 classified correctly via `adk web` |
| **2** | Apr 14-15 | Impact Agent + Firestore | "Impact Agent PRD" | Impact assessed correctly via `adk web` |
| **3** | Apr 16-17 | Coordinator + Full Pipeline | "Coordinator Integration PRD" | Full pipeline runs end-to-end via `adk web` |
| **4** | Apr 18-19 | API Layer + Streaming + Security Hardening | "API & Security PRD" | `/triage/stream` works with auth + rate limit |
| **5** | Apr 20-21 | Cloud Run Deploy + React Frontend | "Deployment & Frontend PRD" | Live URL responds correctly |
| **6** | Apr 22-23 | Submission Package + Final Review | "Submission PRD" | All 7 artifacts submitted |

**Apr 24:** Buffer day for final smoke test + submission portal upload.

## Per-Sprint Documentation (9 Artifacts)

Every sprint produces these in `docs/sprints/sprint-N/`:

| # | Artifact | Phase | Tool/Template |
|---|----------|-------|---------------|
| 1 | `prd.md` — Product Requirements Doc | Plan | superpowers:writing-plans skill |
| 2 | `test-plan.md` — Given/When/Then test cases | Plan | Test plan template |
| 3 | `risks.md` — Pre-mortem risk assessment | Risk | Pre-mortem format |
| 4 | `adr-*.md` — Architecture Decision Records | Risk/Engineer | ADR template |
| 5 | `security.md` — OWASP checklist + threat notes | Engineer | OWASP per-sprint |
| 6 | `impl-log.md` — What was built, in order, why | Engineer | Dev diary |
| 7 | `test-report.md` — Coverage + results | Engineer | pytest + notes |
| 8 | `review.md` — AI + user code review findings | Evaluate | code-reviewer output + user notes |
| 9 | `retro.md` — Start/Stop/Continue lessons | Evaluate | Retro template |

## Sprint 0 Deliverables (Comprehensive)

Sprint 0 sets up EVERYTHING so every subsequent sprint focuses purely on feature delivery.

### Project Infrastructure
- GCP project + IAM roles + Secret Manager configured
- Python project structure (`src/`, `tests/`, `docs/`, `infra/`, `scripts/`)
- `pyproject.toml` with dependency groups (dev, test, docs, security)
- Virtual environment + dependency lock file
- Pre-commit hooks: ruff, black, mypy, bandit
- GitHub repo with branch protection

### Testing Infrastructure
- pytest + pytest-asyncio + pytest-cov
- Firestore emulator fixtures
- Mock/fake implementations for Gemini, Supermemory, Firestore
- `make test` and `make coverage` commands
- Test harness proving example test runs

### Security Foundation
- Firebase Auth + JWT validation middleware
- CORS policy + CSP headers defined
- Input sanitization utilities
- Audit logging framework
- Dependency scanning (bandit, safety)
- Threat model document (`docs/security/threat-model.md`)
- OWASP API Top 10 checklist

### Documentation Infrastructure
- `docs/` directory structure
- All document templates (PRD, ADR, test plan, retrospective, sprint layout)
- Main README with onboarding
- `CONTRIBUTING.md`
- Architecture overview document
- `docs/decisions/` directory for ADRs
- `docs/sprints/` directory for per-sprint docs

### CI/CD Foundation
- `.github/workflows/ci.yml` — tests on push
- `.github/workflows/security.yml` — dependency + SAST scanning
- Deployment scripts (`scripts/deploy.sh`)
- `.env.template` for environment variables

### Pydantic Schemas (Foundation for All Sprints)
- `schemas/exception_event.py` + tests
- `schemas/classification.py` + tests
- `schemas/impact.py` + tests
- `schemas/triage_result.py` + tests
- `schemas/user_context.py` + tests
- `schemas/company_profile.py` + tests

### ADK Baseline
- `hello_world_agent` responding via Gemini
- `adk web` verified to launch

### Initial Architecture Decision Records
- ADR-001: Framework choice (ADK over BeeAI) — documents rationale from earlier analysis
- ADR-002: Memory layer (Supermemory over Mem0)
- ADR-003: Prompt format (Markdown + XML hybrid)
- ADR-004: Streaming strategy (Hybrid SSE + Gemini text streaming)
- ADR-005: Testing strategy (Strict TDD)
- ADR-006: SDLC choice (Spiral)
- ADR-007: UI strategy (`adk web` for Sprints 1-3, custom React in Sprint 5)

### Sprint 0 Gate Criteria
You cannot start Sprint 1 until ALL of these are green:
- ✅ All tests pass
- ✅ `adk web` launches and hello_world_agent responds
- ✅ Firestore emulator runs locally
- ✅ Pre-commit hooks work
- ✅ CI pipeline passes
- ✅ Security scan shows no high-severity issues
- ✅ All documentation templates exist
- ✅ All 7 ADRs written
- ✅ Threat model drafted
- ✅ OWASP checklist exists

**Expected duration:** 2-3 days. Cannot be rushed.

## Directory Structure (Full)

```
supply_chain_triage/
├── README.md
├── CONTRIBUTING.md
├── pyproject.toml
├── Makefile
├── .env.template
├── .pre-commit-config.yaml
├── .github/workflows/
│   ├── ci.yml
│   └── security.yml
├── src/supply_chain_triage/
│   ├── agents/
│   │   ├── coordinator.py
│   │   ├── classifier.py
│   │   ├── impact.py
│   │   └── prompts/
│   ├── schemas/
│   ├── memory/
│   │   ├── provider.py
│   │   └── supermemory_adapter.py
│   ├── guardrails/
│   │   └── validators.py
│   ├── middleware/
│   │   ├── context_injection.py
│   │   ├── auth.py
│   │   ├── rate_limit.py
│   │   └── audit_log.py
│   ├── runners/
│   │   └── agent_runner.py
│   ├── api/
│   │   └── triage_endpoint.py
│   ├── tools/
│   └── main.py
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── contract/
│   └── e2e/
├── docs/
│   ├── architecture/
│   ├── decisions/       (ADRs)
│   ├── sprints/         (per-sprint docs, 9 files × 7 sprints = 63 files)
│   ├── security/
│   ├── api/
│   ├── templates/
│   └── onboarding/
├── infra/
│   ├── firestore.rules
│   ├── firestore.indexes.json
│   ├── firebase.json
│   └── cloudrun.yaml
└── scripts/
    ├── deploy.sh
    ├── seed_firestore.py
    └── setup_dev.sh
```

## Sprint Workflow (Detail)

### Plan Phase (2-4 hours per sprint)
1. **Research** (1-2 hours)
   - Review relevant notes in `10 - Deep Dives/Supply-Chain/`
   - Web research on sprint-specific 2026 best practices
   - Synthesize combined knowledge
   - Document findings as input to PRD
2. **PRD** (1 hour)
   - Use superpowers:writing-plans skill
   - Focus: objective, scope, acceptance criteria, test cases, security, out-of-scope
   - NOT comprehensive — chunk-focused
3. **Test Plan** (30 min)
   - Given/When/Then test cases from acceptance criteria
4. **User review** of PRD + Test Plan (30 min)

### Risk Phase (1-2 hours per sprint)
1. **Pre-mortem** (30 min) — assume the sprint failed, why?
2. **ADRs** (30 min) — document significant decisions with reasoning
3. **Prototyping** (if needed) — sanity-check uncertain parts
4. **Threat model** (30 min) — security threats specific to this sprint

### Engineer Phase (10-12 hours per sprint)
1. **TDD cycle** for each unit:
   - Write failing test
   - Implement minimum code
   - Refactor
2. **Security checks** at every commit (bandit, safety)
3. **Documentation as code** (docstrings, READMEs)
4. **Integration tests** with real dependencies (Firestore emulator, etc.)
5. **Implementation log** updated as you go

### Evaluate Phase (2-3 hours per sprint)
1. Run all tests, collect Test Report
2. superpowers:code-reviewer skill reviews diff
3. User reviews code + AI feedback
4. Fix issues before sprint closure
5. Write Retrospective (Start/Stop/Continue)
6. Update main docs if architecture changed
7. Tag sprint complete in Git

## Priority Framework

### Must-Have for Apr 24 (non-negotiable)
- Working 3-agent pipeline tested via `adk web` (Sprints 1-3)
- Cloud Run deployment with live URL (Sprint 5)
- Basic security: auth, multi-tenant isolation, Secret Manager (Sprint 0)
- Core testing: unit + integration (throughout)
- Submission artifacts: demo video, README, problem statement, solution brief, deck (Sprint 6)
- Any UI (`adk web` at minimum, React if time permits)

### Should-Have for Apr 24 (cut if needed)
- Supermemory integration (Sprint 3)
- Hybrid SSE streaming (Sprint 4)
- Custom React frontend (Sprint 5)
- Full Guardrails AI validation (Sprint 1-2)
- Security hardening: rate limiting, audit logging (Sprint 4)

### Nice-to-Have (defer to Tier 2)
- E2E automated tests
- Perfect demo video
- Advanced security (CSRF, CSP, dependency scanning automation)
- Performance optimization

## Risks & Mitigations

| Risk | Probability | Severity | Mitigation |
|------|-------------|----------|-----------|
| Sprint 0 bleeds to 3+ days | High | Medium | Sprint 0 is flexible; later sprints compress or cut scope |
| Cloud Run cold start breaks demo | Medium | High | Set `min_instances=1` (~$5/month); pre-warm before demo |
| Gemini API rate limiting | Medium | Medium | Use Secret Manager quota; implement exponential backoff |
| Supermemory integration delays | Medium | Medium | Have Firestore DIY fallback ready as Should-Have trim |
| Streaming complexity blows up Sprint 4 | Medium | Medium | Fallback: non-streaming JSON response |
| User interviews missing (SDG scoring) | High | Medium | Deferred by design; acknowledged scoring cost |
| Formal code review gap | Low (mitigated) | Medium | superpowers:code-reviewer per sprint + user review |
| Documentation overhead delays sprints | Medium | Medium | Templates reduce overhead; time-box doc phases |

## Cross-References

- [[Supply-Chain-Product-Recap]] — Living product overview
- [[Supply-Chain-Architecture-Decision-Analysis]] — Why D+F architecture
- [[Supply-Chain-Agent-Spec-Coordinator]] — Coordinator agent spec
- [[Supply-Chain-Agent-Spec-Classifier]] — Classifier agent spec
- [[Supply-Chain-Agent-Spec-Impact]] — Impact agent spec
- [[Supply-Chain-Firestore-Schema-Tier1]] — Firestore data model
- [[Supply-Chain-Demo-Scenario-Tier1]] — NH-48 anchor scenario
- [[Supply-Chain-Research-Sources]] — Research bibliography
