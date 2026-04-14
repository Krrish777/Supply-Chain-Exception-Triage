---
title: "ADR-005: Testing Strategy — Strict TDD"
type: deep-dive
domains: [supply-chain, testing, sdlc]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]"]
---

# ADR-005: Testing Strategy — Strict Test-Driven Development

## Status
Accepted

## Date
2026-04-10

## Context

The Spiral SDLC plan ([[Supply-Chain-Sprint-Plan-Spiral-SDLC]]) mandates "strict TDD" as Governing Principle #2. This ADR makes the strict-TDD rule concrete, defines what "strict" means in practice, and names the exceptions.

Forces:
- 14-day timeline = zero margin for bug regressions
- Solo builder = no second pair of eyes during implementation
- Multi-agent system = failure modes are non-obvious; tests catch them earlier than inspection
- Hackathon judges review the repo — visible test coverage is a credibility signal
- Spiral's Evaluate phase requires a Test Report artifact per sprint; tests must exist to report on
- User explicit requirement (captured in project memory): "strict TDD, test-first for everything"

## Decision

**Strict TDD is the only accepted development workflow.** Every unit of new behavior follows the red-green-refactor cycle:

1. **Red**: Write a failing test that describes the behavior. Run it. Confirm it fails for the right reason.
2. **Green**: Write the minimum code to make the test pass. Nothing more.
3. **Refactor**: Clean up the implementation. Tests must still pass.
4. **Commit**: Commit test + implementation together with a descriptive message.

No code is committed without a test committed in the same or preceding commit. CI enforces this implicitly (all code paths must be covered ≥ 80%).

## Alternatives Considered

- **Test-After Development**: Write code, then write tests to cover it. Rejected because it leads to tests that rationalize the code rather than specify the behavior, and solo builders often skip the "then" step under time pressure.
- **Behavior-Driven Development (Gherkin / .feature files)**: Considered. Rejected because the infrastructure cost (behave, pytest-bdd) isn't worth it for a 14-day solo sprint; plain pytest with Given/When/Then comments captures the intent.
- **No formal testing policy**: Rejected — see Spiral SDLC governing principles. Named Must-Have in sprint plan.
- **100% coverage enforcement**: Rejected as perfectionism — we target ≥ 80% on core code with ≥ 95% on security-critical paths (middleware, sanitizers, schemas).

## Exceptions (Named Explicitly)

Strict TDD does NOT apply to:

1. **Exploratory prototyping in `scratch/` directories** — throw-away code that never enters `src/`. Must be deleted before PR.
2. **Prompt engineering iteration** — prompts in `agents/prompts/*.md` are tested via agent evaluator tests, not line-level tests.
3. **Infrastructure configuration** (`pyproject.toml`, `.github/workflows/*.yml`, `firestore.rules`) — verified via meta-tests (Area 8 in test-plan) or via CI running the config.
4. **Documentation files** — no tests.
5. **Generated code** (if any) — excluded from coverage, excluded from TDD.

Everything else — schemas, middleware, agents, tools, sanitizers, memory adapters, runners — is strict TDD.

## Consequences

### Positive
- Bugs caught at commit time, not Sprint 3 integration time
- Test suite becomes living documentation of expected behavior
- Refactoring is safe — tests are the safety net
- Credibility signal to judges (visible coverage badge on README)
- Sprint gate criteria include "all tests pass" — strict TDD makes this trivially achievable

### Negative
- Slower on Day 1 of each sprint — tests-first feels like drag when you "already know" what the code will do
- Requires discipline to not write "the implementation I want" in the test (tests should describe BEHAVIOR, not structure)
- Some ADK internals are hard to mock — integration tests must use real Gemini calls (marked slow, skipped in fast CI)

### Neutral
- `Makefile` provides `make test-fast` (unit only) and `make test-all` (unit + integration)
- CI runs fast tests on every push, integration tests nightly and on PR
- Coverage report published to `docs/sprints/sprint-N/test-report.md` per sprint
- When a test is hard to write, that's a signal the design is wrong — refactor the design, not the test

## Amendments

### 2026-04-14 — Coverage gating softened for Tier 1

Coverage enforcement is **advisory** through the Tier 1 hackathon boundary (2026-04-24) and **hardens to 90% on pure-logic paths** at the Tier 2 boundary (2026-05-29). Rationale captured in `CLAUDE.md` and `.claude/rules/testing.md` §2 — enforcing 80% on an empty Sprint 0 codebase incentivized tautological tests; the project's quality gate in this window is agent evalsets + test-first discipline, not coverage percentage. Once real business logic lands in Sprint 1-3, hard-gating makes sense. The strict-TDD rule (red → green → refactor) in this ADR is **unchanged** — it is coverage *enforcement via CI* that is softened, not the development discipline.

Operationally: `pyproject.toml` currently runs `--cov-report=term-missing --cov-report=xml` with no `--cov-fail-under`. `[tool.coverage.run] source = [...]` is already narrowed to pure-logic paths (`core/`, `utils/`, `middleware/`, `modules/triage/{models,tools,guardrails,memory}/`) so when the gate hardens, it scopes automatically.

## References

- [Kent Beck — Test-Driven Development By Example](https://www.oreilly.com/library/view/test-driven-development/0321146530/) (canonical TDD reference)
- [pytest-asyncio docs](https://pytest-asyncio.readthedocs.io/)
- [FutureAGI ADK Evaluation Guide](https://futureagi.com/docs/adk/evaluation) — AgentEvaluator patterns
- [adk-samples DeepWiki](https://deepwiki.com/google/adk-samples) — test structure reference
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — governing principles
- [[Supply-Chain-Research-Sources]] — broader research context
