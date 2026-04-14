---
title: "Sprint 0 PRD v2 — Secure Foundation + Test Harness + Docs Infrastructure"
type: deep-dive
domains: [supply-chain, hackathon, sdlc]
last_updated: 2026-04-14
status: active
version: v2
supersedes: ./prd-v1-archived.md
confidence: high
sources:
  - "[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]"
  - "[[Supply-Chain-Agent-Spec-Coordinator]]"
  - "[[Supply-Chain-Agent-Spec-Classifier]]"
  - "[[Supply-Chain-Agent-Spec-Impact]]"
  - "[[Supply-Chain-Firestore-Schema-Tier1]]"
  - "[[Supply-Chain-Architecture-Decision-Analysis]]"
  - "[[Supply-Chain-Deployment-Options-Research]]"
  - "[[Supply-Chain-Research-Sources]]"
  - docs/research/zettel-supermemory-python-sdk.md
  - docs/research/zettel-adk-before-model-callback.md
  - docs/research/zettel-fastapi-sse-cloud-run.md
  - docs/research/zettel-firestore-multi-tenant.md
  - docs/research/zettel-vault-coordinator-inconsistency.md
---

# Sprint 0 PRD v2 — Secure Foundation (Execution Guide)

> **Sprint window:** 2026-04-14 (single-day compressed — see §15).
> **Feature code produced:** **Zero.** This sprint is pure foundation.
> **Audience:** Executable verbatim. A new contributor can follow this PRD + `.claude/rules/*` and ship Sprint 0's gate criteria.

---

## Changes from v1 (prd-v1-archived.md)

1. **Directory tree rewritten to modular (Proposal B).** All paths now under `src/supply_chain_triage/modules/triage/...` — matches `.claude/rules/placement.md` (hook-enforced).
2. **Schema paths** — 6 schemas land at `src/supply_chain_triage/modules/triage/models/` (not top-level `schemas/`), since they are shared across Classifier, Impact, and Coordinator.
3. **`CompanyProfile.to_markdown()` added** + `render_learned_preferences()` free helper. PRD v1 omitted both; vault Coordinator spec requires them for `<company_context>` and `<learned_behaviors>` XML blocks (see `docs/research/zettel-vault-coordinator-inconsistency.md`). Test count 30 → **32**.
4. **`scripts/set_custom_claims.py` added.** PRD v1 omitted. Needed because Firebase custom claims require Admin SDK server-side (see `docs/research/zettel-firestore-multi-tenant.md`); without this, Test 2.5 has no positive-case counterpart.
5. **ADR-008 (A2A protocol) added to Sprint 0 docs scope.** Captures our 2026-04-14 A2A commitment orthogonal to ADR-001.
6. **Coverage threshold flipped to advisory through Tier 1** per CLAUDE.md. ADR-005 amended with one-line note. Acceptance criterion #2 no longer a blocker.
7. **Risk 12 + Risk 13 appended to risks.md** (Supermemory container-tag contract, Cloud Run SSE buffering).
8. **Timeline rebased Apr 10-12 → Apr 14.** Compressed Sprints 1-3 to 1 day each; 4-6 keep 2 days; Sprint 5 React becomes Should-Have trim with `adk web` fallback.
9. **Schemas, middleware, config shown as signatures, not full bodies.** Rationale: strict TDD means tests (test-plan.md) are the behavioral spec; the PRD shows intent. Cuts ~1500 lines vs v1.
10. **Import rules, folder placement, testing split, observability, deployment patterns all moved out of the PRD** — they're in `.claude/rules/*` now. PRD v2 references those files rather than restating.

---

## 1. Objective

Stand up **everything** a feature-sprint engineer needs before touching business logic:

- Secure GCP foundation (billing, IAM, Secret Manager, Firebase, Firestore Mumbai)
- Python project skeleton conforming to `.claude/rules/placement.md`
- Test harness with emulators, fakes, session-scoped fixtures
- Security middleware (Firebase Auth, CORS, audit logging, input sanitization)
- Pydantic schemas + `to_markdown()` helpers
- ADK `hello_world` baseline + evalset
- Full documentation skeleton: 8 ADRs (7 existing + ADR-008), 5 templates, security docs, READMEs, Sprint 0's 9 Spiral artifacts

**One-sentence goal:** Sprints 1-6 can focus 100% on feature delivery without touching infrastructure.

---

## 2. Scope (IN)

### 2.1 GCP + security foundation
- GCP project + billing active (Risk 1 pre-check)
- Least-privilege IAM: dev SA gets only `roles/secretmanager.secretAccessor` + `roles/datastore.user`
- Secret Manager: `GEMINI_API_KEY`, `SUPERMEMORY_API_KEY`, `FIREBASE_SERVICE_ACCOUNT`
- Firebase project with Google Sign-In OAuth enabled
- Firestore Native mode, **`asia-south1`** (Mumbai — India-first assumption)

### 2.2 Python skeleton
- `src/` layout, Python **3.13**, `uv` package manager, `uv.lock` committed
- Dependency groups `test`, `dev`, `security`, `docs` per pyproject
- Directory tree per §5 (matches `.claude/rules/placement.md`)

### 2.3 Test harness
- `pytest>=7.3.2` + `pytest-asyncio>=0.21.0` + `pytest-cov` + `pytest-mock`
- `asyncio_mode = "auto"` (no `@pytest.mark.asyncio` boilerplate)
- Session-scoped `firestore_emulator` autouse fixture per `.claude/rules/testing.md` §5
- Fakes: `FakeGeminiClient`, `FakeFirestoreClient` (mockfirestore-backed), `FakeSupermemoryClient`
- `make test` + `make coverage` (user-owned Makefile)

### 2.4 Security middleware
- **Firebase Auth** via `firebase-admin.auth.verify_id_token` (ADR-004 decision #4). Canonical middleware stack ordering documented inline in `main.py` `create_app()` (Risk 11 regression guard).
- **CORS allowlist** — env-based; reject wildcards at startup (`ValueError` on `*`)
- **Input sanitization** — XSS strip + control-char strip; **must preserve Hindi/Hinglish unicode** (India-first assumption)
- **Audit logging** — structured JSON via `structlog` with `correlation_id`, `user_id`, `company_id`; module-level `audit_event(event, **kwargs)` helper usable outside HTTP context
- **Rate-limit middleware** — stub only (`TODO(sprint-4)`)

### 2.4b Runtime helpers (Sprint 1 dependency backfill)
Implemented in Sprint 0; Sprint 1+ agents depend on them:
- `core.config.get_secret(key)` — runtime Secret Manager fetch; in-process cache; test-mode fallback to env var; raises `SecretNotFoundError`
- `core.config.get_firestore_client()` — cached async Firestore client (real or emulator, switched by `FIRESTORE_EMULATOR_HOST`)
- `middleware.audit_log.audit_event(event, **kwargs)` — structured audit emitter usable outside HTTP middleware context

### 2.5 Pre-commit + CI (templates only — user populates)
PRD v2 does NOT author `.pre-commit-config.yaml`, `.github/workflows/*.yml`, or `Makefile`. These are user-owned per the 2026-04-14 agreement. Suggested content lives in §11/§12 as reference; user reviews and populates.

### 2.6 Pydantic schemas (6 types + 2 helpers)
All schemas land in `src/supply_chain_triage/modules/triage/models/`:
- `exception_event.py` — `ExceptionEvent`
- `classification.py` — `ClassificationResult` + `ExceptionType` + `Severity`
- `impact.py` — `ShipmentImpact` + `ImpactResult`
- `triage_result.py` — `TriageResult` + `TriageStatus` + `EscalationPriority`
- `user_context.py` — `UserContext` (+ `to_markdown()` covering 3 sections: Identity, Volume & Workload, Communication Preferences)
- `company_profile.py` — `CompanyProfile` (+ `to_markdown()` covering Business Context including `avg_daily_revenue_inr`)
- `learned_preferences.py` — free function `render_learned_preferences(user_context) -> str` for `<learned_behaviors>` XML block

All use Pydantic v2. Signatures in §8. Strict TDD per ADR-005: tests in `tests/unit/schemas/` are written first.

### 2.7 ADK baseline
- `hello_world` agent at `src/supply_chain_triage/modules/triage/agents/hello_world/`
  - `agent.py` → `root_agent = LlmAgent(model="gemini-2.5-flash", name="hello_world")`
  - `prompts/hello_world.md` → minimal greeter prompt
- `adk web` launches; agent responds to "hello"
- **Evalset** at `evals/hello_world/greeting.evalset.json` (1 scenario, `response_match_score`) — per `.claude/rules/testing.md` §3

### 2.8 Documentation infrastructure
- `docs/` skeleton: `architecture/`, `decisions/`, `sprints/`, `security/`, `api/`, `templates/`, `onboarding/`, `research/`, `sessions/`
- Templates: PRD, ADR (Michael Nygard format), test-plan, retrospective, sprint-layout
- Top-level: `README.md`, `CONTRIBUTING.md`, `SECURITY.md`
- **8 ADRs**: ADR-001 (Framework), ADR-002 (Memory), ADR-003 (Prompt format), ADR-004 (Streaming), ADR-005 (TDD) — all pre-authored and committed; **ADR-008 (A2A protocol) — new, authored in Phase B.**
- `docs/security/threat-model.md` + `docs/security/owasp-checklist.md`
- **Research bundle** (already written in Phase A, visible at `docs/research/`): 5 vault copies, 1 ADA digest, 5 web Zettels

### 2.9 Sprint 0's 9 Spiral artifacts
Per `docs/research/Supply-Chain-Sprint-Plan-Spiral-SDLC.md`:
1. ✅ `prd.md` (this file)
2. ✅ `test-plan.md`
3. ✅ `risks.md`
4. ADR files at `docs/decisions/*.md` (7 done + ADR-008 Phase B)
5. `security.md` (OWASP instance for Sprint 0) — Phase D
6. `impl-log.md` — Phase D (dev diary appended during Phase C)
7. `test-report.md` — Phase D
8. `review.md` — Phase D (AI code review)
9. `retro.md` — Phase D (Start/Stop/Continue)

---

## 3. Out of Scope (deferred)

| Item | Deferred to | Reason |
|---|---|---|
| Classifier Agent business logic | Sprint 1 | Feature sprint |
| Impact Agent business logic | Sprint 2 | Feature sprint |
| Coordinator delegation rules A–F | Sprint 3 | Feature sprint |
| `/triage/stream` endpoint | Sprint 4 | Feature sprint |
| **Real Supermemory integration** | **Sprint 4 Should-Have** | Sprint 0 uses `FakeSupermemoryClient` with identical interface |
| Real deployment (Cloud Run etc.) | Sprint 5 | 4 options in `[[Supply-Chain-Deployment-Options-Research]]`; choice deferred |
| Dockerfile / docker-compose | Sprint 5 | User directive: "Docker is the last type of setup" |
| React frontend | Sprint 5 (Should-Have trim; `adk web` fallback) | ADR-007 |
| Guardrails AI validators | Sprint 1 | Interface stub only here |
| Rate-limit enforcement | Sprint 4 | Stub only |
| NH-48 seed data population | Sprint 2 | Firestore schema ready; data later |
| Festival + monsoon seed data | Sprint 1 | Classifier tool data |
| `.pre-commit-config.yaml` / `ci.yml` / `Makefile` / `.env.template` population | User territory | PRD suggests content; user writes files |

---

## 4. Resolved Decisions (v1 carryovers + v2 additions)

| # | Decision | Value | Source |
|---|---|---|---|
| 1 | Python version | **3.13** | Carried from v1 |
| 2 | Package manager | **uv** | Carried from v1 |
| 3 | Firestore region | **asia-south1 (Mumbai)** — India-first assumption | Carried from v1 |
| 4 | Auth library | **firebase-admin SDK** (`verify_id_token` pattern) | Carried from v1 |
| 5 | Local dev secrets | Personal `.env` + each dev's GCP free-tier project | Carried from v1 |
| 6 | Test framework | **pytest** (asyncio_mode=auto) | Carried from v1 |
| 7 | Deployment target | Deferred to Sprint 5 | Carried from v1 |
| 8 | CI/CD framework | **GitHub Actions** (stub `deploy.yml` until Sprint 5) | Carried from v1 |
| 9 | Dockerfile in Sprint 0 | **No** | Carried from v1 |
| 10 | **Structure** | **Proposal B modular** — `modules/triage/...` hook-enforced | **v2 — CLAUDE.md 2026-04-14** |
| 11 | **TDD mode** | **Strict TDD** per ADR-005 (red → green → refactor) | **v2 — user choice 2026-04-14** |
| 12 | **Memory layer** | **Supermemory stays** per ADR-002; Sprint 0 fake; real Sprint 4 Should-Have | **v2 — user choice 2026-04-14** |
| 13 | **Coverage** | **Advisory through Tier 1** (2026-04-24); hardens to 90% pure-logic at Tier 2 | **v2 — user choice 2026-04-14** |
| 14 | **A2A protocol** | Captured in ADR-008 (new); always scaffold via `--agent adk_a2a`, never hand-write | **v2 — user choice 2026-04-14** |
| 15 | **Vendor-lock-free** | ADK imports only in agent.py / runners / memory adapters; enforced by ruff `TID251` | **v2 — CLAUDE.md 2026-04-14** |
| 16 | **UserContext rendering** | 3 sections in `UserContext.to_markdown()`; new `CompanyProfile.to_markdown()` + `render_learned_preferences()` cover the rest | **v2 — vault inconsistency resolution** |
| 17 | **Timeline** | Sprints 0-3 compressed to 1 day each; 4-6 keep 2 days; Sprint 5 React = Should-Have | **v2 — user choice 2026-04-14** |

---

## 5. Project directory tree (exact)

Matches `.claude/rules/placement.md` verbatim. Placement hook rejects writes outside this tree.

```
supply_chain_triage/
├── README.md
├── CONTRIBUTING.md
├── SECURITY.md
├── LICENSE                              # MIT (present)
├── pyproject.toml                       # ruff TID251 already configured (present)
├── uv.lock                              # uv lock --check in CI
├── Makefile                             # USER-OWNED
├── .env.template                        # USER-OWNED
├── .env                                 # gitignored
├── .gitignore                           # present
├── .pre-commit-config.yaml              # USER-OWNED
├── .python-version                      # 3.13 (present)
├── .secrets.baseline                    # detect-secrets empty baseline
├── .claude/                             # CLAUDE.md, rules/, hooks/, settings.json (present)
├── .github/workflows/
│   ├── ci.yml                           # USER-OWNED
│   ├── security.yml                     # USER-OWNED
│   └── deploy.yml                       # USER-OWNED (stub until Sprint 5)
├── infra/
│   ├── firestore.rules                  # multi-tenant rules per vault Firestore-Schema-Tier1
│   ├── firestore.indexes.json           # composite indexes per vault
│   └── firebase.json                    # emulator config (firestore + auth)
├── src/supply_chain_triage/
│   ├── __init__.py                      # present
│   ├── main.py                          # FastAPI create_app + CLI entry
│   ├── core/
│   │   ├── __init__.py                  # present
│   │   └── config.py                    # Pydantic Settings + get_secret + get_firestore_client + SecretNotFoundError
│   ├── middleware/
│   │   ├── __init__.py                  # present
│   │   ├── firebase_auth.py
│   │   ├── cors.py
│   │   ├── audit_log.py                 # + module-level audit_event() helper
│   │   ├── input_sanitization.py
│   │   └── rate_limit.py                # stub (TODO(sprint-4))
│   ├── runners/
│   │   ├── __init__.py                  # present
│   │   └── agent_runner.py              # framework-portability shim per ADR-001
│   ├── utils/
│   │   └── __init__.py                  # present
│   └── modules/
│       ├── __init__.py                  # present
│       └── triage/
│           ├── __init__.py              # present
│           ├── agents/
│           │   ├── __init__.py          # present
│           │   └── hello_world/         # present (placeholder)
│           │       ├── __init__.py
│           │       ├── agent.py         # LlmAgent(gemini-2.5-flash)
│           │       └── prompts/
│           │           └── hello_world.md
│           ├── tools/
│           │   └── __init__.py          # present (Sprint 1+ populates)
│           ├── memory/
│           │   ├── __init__.py          # present
│           │   ├── provider.py          # MemoryProvider ABC (ADR-002)
│           │   └── supermemory_adapter.py   # stub, raises NotImplementedError, real Sprint 4
│           ├── models/
│           │   ├── __init__.py          # present
│           │   ├── exception_event.py
│           │   ├── classification.py
│           │   ├── impact.py
│           │   ├── triage_result.py
│           │   ├── user_context.py
│           │   ├── company_profile.py
│           │   └── learned_preferences.py
│           └── guardrails/
│               └── __init__.py          # present (Sprint 1+ populates)
├── tests/
│   ├── __init__.py                      # present
│   ├── conftest.py                      # session-scoped firestore_emulator fixture
│   ├── fixtures/
│   │   ├── __init__.py
│   │   ├── fake_gemini.py
│   │   ├── fake_firestore.py            # mockfirestore-backed
│   │   └── fake_supermemory.py
│   ├── unit/
│   │   ├── __init__.py                  # present
│   │   ├── schemas/
│   │   ├── middleware/
│   │   ├── agents/
│   │   └── config/
│   ├── integration/
│   │   ├── __init__.py                  # present
│   │   └── firestore/
│   └── e2e/
│       └── __init__.py                  # present (Tier 3+)
├── evals/
│   └── hello_world/
│       └── greeting.evalset.json
├── docs/
│   ├── product_recap.md                 # present
│   ├── decisions/                       # 7 ADRs present + ADR-008 added Phase B
│   ├── sprints/sprint-0/
│   │   ├── prd.md                       # THIS FILE
│   │   ├── prd-v1-archived.md
│   │   ├── test-plan.md                 # 32 tests
│   │   ├── risks.md                     # 13 risks
│   │   ├── security.md                  # Phase D
│   │   ├── impl-log.md                  # Phase D
│   │   ├── test-report.md               # Phase D
│   │   ├── review.md                    # Phase D
│   │   └── retro.md                     # Phase D
│   ├── research/                        # Phase A output (5 vault + 1 ADA + 5 Zettels)
│   ├── sessions/                        # session handoff notes
│   ├── security/
│   │   ├── threat-model.md
│   │   └── owasp-checklist.md
│   └── templates/
│       ├── prd-template.md
│       ├── adr-template.md
│       ├── test-plan-template.md
│       ├── retrospective-template.md
│       └── sprint-layout-template.md
└── scripts/
    ├── setup.sh                         # idempotent dev setup
    ├── gcp_bootstrap.sh                 # one-time GCP setup
    ├── seed_firestore.py                # stub + skeleton files per §15
    ├── set_custom_claims.py             # NEW — sets company_id custom claim for test users
    └── deploy.sh                        # stub (Sprint 5)
```

**Placement-hook allowlist must be extended** before Phase C for: `scripts/*.{sh,py}`, `infra/*.{rules,json}`, `firebase.json`, `tests/fixtures/**/*.py`. One change, atomic with `.claude/rules/placement.md` placement-table update.

---

## 6. pyproject.toml (status)

Already configured on 2026-04-14 with:
- Python 3.13 requirement, uv-managed
- `test`, `dev`, `security`, `docs` extras
- Ruff with `E,F,W,I,B,UP,SIM,S,C90,ASYNC,RUF,PT,TID,PL,N,ARG,PTH,TCH,ERA`
- **`TID251` banned-api** enforces vendor-lock-free:
  - `google.adk` only in `modules/*/agents/**/agent.py`, `runners/`, `**/memory/**`, `**/tools/**`, `middleware/`
  - `firebase_admin`, `google.cloud.firestore` same allowlist
- Mypy strict + scoped `ignore_missing_imports` for ADK/firebase_admin/mockfirestore
- Pytest `asyncio_mode=auto`, `--strict-markers --strict-config`, coverage reports but **no `--cov-fail-under`** (advisory through Tier 1)
- Coverage source narrowed to `core/`, `utils/`, `middleware/`, `modules/triage/{models,tools,guardrails,memory}/`

No changes needed to pyproject.toml in Sprint 0.

---

## 7. Runtime entry points

### 7.1 `main.py` — FastAPI create_app factory

```python
from fastapi import FastAPI
from supply_chain_triage.core.config import get_settings
from supply_chain_triage.middleware.firebase_auth import FirebaseAuthMiddleware
from supply_chain_triage.middleware.cors import add_cors_middleware
from supply_chain_triage.middleware.audit_log import AuditLogMiddleware
from supply_chain_triage.middleware.input_sanitization import InputSanitizationMiddleware

def create_app() -> FastAPI:
    app = FastAPI(title="Supply Chain Exception Triage")
    # LIFO ordering — LAST add_middleware = OUTERMOST on request.
    # Canonical order OUTER → INNER: AuditLog → FirebaseAuth → InputSanitization → CORS
    # Risk 11: reversing these makes auth failures skip audit logging.
    add_cors_middleware(app, allowed_origins=get_settings().cors_allowed_origins)
    app.add_middleware(InputSanitizationMiddleware)
    app.add_middleware(FirebaseAuthMiddleware, public_paths={"/health", "/docs", "/openapi.json"})
    app.add_middleware(AuditLogMiddleware)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}
    return app

def cli() -> None:
    """Console script entry: `supply-chain-triage`."""
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=8000)
```

### 7.2 `hello_world` agent — `modules/triage/agents/hello_world/agent.py`

```python
from google.adk.agents import LlmAgent
from pathlib import Path

_PROMPT = (Path(__file__).parent / "prompts" / "hello_world.md").read_text()
root_agent = LlmAgent(
    model="gemini-2.5-flash",
    name="hello_world",
    instruction=_PROMPT,
)
```

Prompt: minimal greeter — "Respond warmly to greetings; keep responses ≤ 2 sentences."

---

## 8. Pydantic schemas — signatures + critical constraints

Test-plan.md is the behavioral specification (32 tests). This section shows intent.

### 8.1 `ExceptionEvent` (`modules/triage/models/exception_event.py`)
```python
SourceChannel = Literal[
    "whatsapp_voice", "whatsapp_text", "email",
    "phone_call_transcript", "carrier_portal_alert",
    "customer_escalation", "manual_entry",
]

class ExceptionEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(..., min_length=1)
    timestamp: datetime
    source_channel: SourceChannel
    sender: dict[str, Any]
    raw_content: str = Field(..., min_length=1, max_length=50_000)
    original_language: str | None = None
    english_translation: str | None = None
    media_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 8.2 `ClassificationResult` (`modules/triage/models/classification.py`)
- `ExceptionType` enum: 6 values (see `docs/research/Supply-Chain-Agent-Spec-Classifier.md` §28-63)
- `Severity` enum: LOW | MEDIUM | HIGH | CRITICAL
- `confidence: float` ∈ [0.0, 1.0]
- `exception_type: ExceptionType`, `subtype: str`, `severity: Severity`
- `urgency_hours: int | None` (≥0)
- `key_facts: dict`, `reasoning: str` (≤2000), `requires_human_approval: bool`, `tools_used: list[str]`, `safety_escalation: dict | None`

### 8.3 `ImpactResult` + `ShipmentImpact` (`modules/triage/models/impact.py`)
- `ShipmentImpact`: shipment_id, customer_id, customer_tier (`Literal["high_value", "repeat_standard", "new", "b2b_enterprise"]`), customer_type (`Literal["d2c", "b2b", "marketplace"]`), product_description, value_inr (≥0), destination, deadline (ISO-8601), hours_until_deadline, sla_breach_risk, churn_risk, penalty_amount_inr (≥0 or None), **public_facing_deadline: bool** (Rule E), **reputation_risk_note: str | None** (Rule E), **reputation_risk_source: Literal["metadata_flag", "llm_inference"] | None**
- `ImpactResult`: event_id, affected_shipments: list, total_value_at_risk_inr, total_penalty_exposure_inr, estimated_churn_impact_inr, critical_path_shipment_id, recommended_priority_order, priority_reasoning, **impact_weights_used: dict** (LLM-reasoned per-exception per Impact spec §198-221), has_reputation_risks, reputation_risk_shipments, tools_used, summary

### 8.4 `TriageResult` (`modules/triage/models/triage_result.py`)
```python
TriageStatus = Literal["complete", "partial", "escalated_to_human", "escalated_to_human_safety"]
EscalationPriority = Literal["standard", "reputation_risk", "safety", "regulatory"]

class TriageResult(BaseModel):
    event_id: str
    status: TriageStatus
    coordinator_trace: list[dict] = Field(default_factory=list)
    classification: ClassificationResult | None = None
    impact: ImpactResult | None = None           # None on Rule F skip
    summary: str
    processing_time_ms: int = Field(..., ge=0)
    errors: list[str] = Field(default_factory=list)
    escalation_priority: EscalationPriority | None = None
```

### 8.5 `UserContext` (`modules/triage/models/user_context.py`)
3-section `to_markdown()` covering Identity, Volume & Workload, Communication Preferences. Required field: `preferred_language` (Test 1.9). Contains `override_patterns: list[str]` + `learned_priorities: dict` consumed by `render_learned_preferences()` (separate helper, §8.7).

### 8.6 `CompanyProfile` (`modules/triage/models/company_profile.py`)
**Gains `to_markdown()` method** (net-new from PRD v1). Renders `## Business Context` section including company name, num_trucks, num_employees, regions, carriers, customer_portfolio summary, top_customers, and `avg_daily_revenue_inr` (required for Classifier Rule 3 per Classifier spec lines 200-209). Feeds `<company_context>` XML block.

### 8.7 `render_learned_preferences` (`modules/triage/models/learned_preferences.py`)
```python
def render_learned_preferences(user_context: UserContext) -> str:
    """Render learned preferences as markdown for <learned_behaviors> XML block."""
```
Produces `## Learned Preferences` section from `user_context.override_patterns` + `user_context.learned_priorities`. Net-new helper.

### Key rules embedded in schemas
- **`ExceptionEvent.source_channel`** is a Literal enum → ValidationError on unknown channel (Test 1.2)
- **`ClassificationResult.confidence`** ≤ 1.0 enforced (Test 1.4)
- **`ShipmentImpact.deadline`** required (Test 1.6)
- **`TriageResult.status`** enum enforced (Test 1.7); `impact=None` allowed (Test 1.8 — Rule F skip)
- **`UserContext.preferred_language`** required (Test 1.9)
- **`CompanyProfile.avg_daily_revenue_inr`** required (Test 1.11 — Classifier Rule 3)

---

## 9. Middleware — signatures + critical constraints

Full bodies written test-first in Phase C4. Signatures below.

### 9.1 `FirebaseAuthMiddleware` (`middleware/firebase_auth.py`)
```python
class FirebaseAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, public_paths: frozenset[str]): ...
    async def dispatch(self, request, call_next) -> Response:
        # Returns 401 on: missing header, expired token, invalid signature, generic ValueError
        # Returns 403 on: missing company_id custom claim
        # Attaches to request.state: user_id, company_id, email
```
- Mocks `firebase_admin.auth.verify_id_token` in tests per `.claude/rules/testing.md`
- 6 unit tests: valid | expired | tampered | missing credentials | missing company_id claim | generic ValueError → 401

### 9.2 `add_cors_middleware` (`middleware/cors.py`)
- Rejects wildcard origin `"*"` with ValueError at startup
- 2 unit tests: allowed origin preflight → 200 + correct headers; disallowed → no `Access-Control-Allow-Origin`

### 9.3 `AuditLogMiddleware` + `audit_event` (`middleware/audit_log.py`)
- Emits JSON with `correlation_id`, `user_id`, `company_id`, `timestamp`, event name
- Module-level `audit_event(event, **kwargs)` callable outside HTTP context (tools, runners)
- 2 unit tests: log shape + correlation_id present on auth-401 responses (Risk 11 regression guard)

### 9.4 `InputSanitizationMiddleware` (`middleware/input_sanitization.py`)
- Strips `<script>` tags and control chars < 0x20 except `\n \r \t`
- **Preserves unicode including Hindi/Hinglish** (critical for India market)
- 3 unit tests: XSS stripped | control chars stripped | Hindi preserved byte-for-byte

### 9.5 `rate_limit.py` — stub with `TODO(sprint-4)`

---

## 10. Config & environment

### 10.1 `core/config.py`
```python
from pydantic_settings import BaseSettings

class SecretNotFoundError(Exception): pass

class Settings(BaseSettings):
    gcp_project_id: str
    firebase_project_id: str
    cors_allowed_origins: list[str]
    firestore_emulator_host: str | None = None
    firebase_auth_emulator_host: str | None = None
    # ... (full list in .env.template, user-owned)

@lru_cache
def get_settings() -> Settings: ...

def get_secret(key: str) -> str: ...
def get_firestore_client() -> firestore.AsyncClient: ...
```

### 10.2 `.env.template` (user writes)
Suggested env vars:
```
GCP_PROJECT_ID=
FIREBASE_PROJECT_ID=
CORS_ALLOWED_ORIGINS=["http://localhost:3000"]
GEMINI_API_KEY=              # fallback for local dev; prod uses Secret Manager
SUPERMEMORY_API_KEY=         # same
FIRESTORE_EMULATOR_HOST=     # localhost:8080 for local
FIREBASE_AUTH_EMULATOR_HOST= # localhost:9099 for local — NEVER set in prod
```

---

## 11-13. Tooling files, CI/CD, documentation templates

All user-owned. Suggested content:

**`.pre-commit-config.yaml`** — ruff (check + format), mypy, bandit, detect-secrets, gitleaks. Pin all hook versions.

**`.github/workflows/ci.yml`** — `uv sync --locked`, `uv run ruff check .`, `uv run mypy src`, `uv run pytest -m "not integration"`.

**`.github/workflows/security.yml`** — nightly: bandit, safety, pip-audit.

**`.github/workflows/deploy.yml`** — stub exiting 0 with `TODO(sprint-5)` referencing `docs/research/Supply-Chain-Deployment-Options-Research.md` (via vault wiki-link).

**`Makefile`** — targets: `setup`, `test`, `coverage`, `lint`, `adk-web`, `eval`, `emulator`, `clean`.

---

## 14. Scripts

### 14.1 `scripts/setup.sh`
Idempotent dev setup: Python 3.13 check → `uv sync --all-extras` → `.secrets.baseline` → `pre-commit install` → gcloud/firebase/java checks → package import smoke test. Preserved from PRD v1 §14.1.

### 14.2 `scripts/gcp_bootstrap.sh`
Enables APIs (secretmanager, firestore, aiplatform), creates Firestore in `asia-south1`, creates 3 secrets (**GEMINI_API_KEY, SUPERMEMORY_API_KEY, FIREBASE_SERVICE_ACCOUNT**), creates dev SA, grants `secretmanager.secretAccessor` + `datastore.user`. Preserved from PRD v1 §14.2.

### 14.3 `scripts/seed_firestore.py`
Skeleton files + loader stub per PRD v1 §14.3. Sprint 0 creates empty JSONs: `festival_calendar.json`, `monsoon_regions.json`, `shipments.json`, `customers.json`, `companies.json`, `users.json`.

### 14.4 `scripts/set_custom_claims.py` — NEW
```python
"""Set `company_id` custom claim on a Firebase Auth test user via Admin SDK.

Used for Test 2.5 positive-case counterpart — protected endpoint returns 200
when token carries valid company_id claim.
"""
from firebase_admin import auth
def set_company_claim(uid: str, company_id: str) -> None:
    auth.set_custom_user_claims(uid, {"company_id": company_id})

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--uid", required=True)
    parser.add_argument("--company-id", required=True)
    args = parser.parse_args()
    set_company_claim(args.uid, args.company_id)
    print(f"Set company_id={args.company_id} on user {args.uid}. Client must refresh ID token.")
```
Rationale: see `docs/research/zettel-firestore-multi-tenant.md`.

### 14.5 `scripts/deploy.sh`
Stub exiting 0 with `TODO(sprint-5)` message. Preserved from PRD v1 §14.4.

---

## 15. Day-by-day build sequence — rebased 2026-04-14

Compressed to single working day (v1 had 3-day spread Apr 10-12). Total budget ~12-14 focused hours. Any task blowing 2× → raise flag per Rollback Plan §18.

### Today — 2026-04-14

| Block | Focus | DoD |
|---|---|---|
| **Block 1** (~2h) | Phase A: PRD v2 + research docs (5 vault copies + 1 ADA digest + 5 Zettels) | All files present at `docs/research/` and `docs/sprints/sprint-0/` |
| **Block 2** (~1h) | Phase B: ADR-008 + ADR-005 amendment + risks.md extensions | `docs/decisions/adr-008-a2a-protocol.md` exists; risks.md has 13 risks |
| **Block 3** (~0.5h) | Phase C prep: extend placement allowlist for scripts/, infra/, firebase.json, tests/fixtures/ | `.claude/rules/placement.md` + `.claude/hooks/check_placement.py` updated atomically |
| **Block 4** (~1h) | C1 scripts + C2 core/config | All 5 scripts in `scripts/`; `core/config.py` with tests green |
| **Block 5** (~2h) | C3 schemas + 14 schema tests (test-first) | `uv run pytest tests/unit/schemas -v` → 14 pass |
| **Block 6** (~2h) | C4 middleware + 13 middleware tests (test-first) | `uv run pytest tests/unit/middleware -v` → 13 pass |
| **Block 7** (~1h) | C5 memory stub + C6 hello_world + evalset + C7 main.py bootstrap | `adk web` responds to "hello" |
| **Block 8** (~1h) | C8 Firestore emulator + integration test | `firebase emulators:start --only firestore,auth`; integration test passes |
| **Block 9** (~0.5h) | C9 fakes | fake_gemini, fake_firestore, fake_supermemory present |
| **Block 10** (~1h) | C10 docs (README, CONTRIBUTING, SECURITY, threat-model, OWASP, 5 templates) | All files render correctly |
| **Block 11** (~1h) | Phase D: 5 Spiral artifacts + session note + gate verification | All §18 criteria ✅; tag v0.1.0-sprint-0 |

If blocks 4-10 overrun, apply Rollback Plan §18 trim levels.

---

## 16. Definition of Done per sub-scope

### 2.1 GCP + security foundation
- [ ] `gcloud billing projects describe <id>` → `billingEnabled: true`
- [ ] `gcloud secrets list` shows GEMINI_API_KEY, SUPERMEMORY_API_KEY, FIREBASE_SERVICE_ACCOUNT
- [ ] `gcloud firestore databases list` shows `asia-south1` DB
- [ ] Firebase project exists with Google Sign-In OAuth enabled
- [ ] Dev SA has only `secretmanager.secretAccessor` + `datastore.user`

### 2.2 Python skeleton
- [ ] `.python-version` = 3.13
- [ ] `uv sync --all-extras` exits 0
- [ ] Directory tree in §5 matches disk
- [ ] Placement hook silent (no writes rejected)

### 2.3 Test harness
- [ ] `uv run pytest` runs **≥32 tests**, all green
- [ ] Coverage reports but does NOT fail (advisory)
- [ ] 3 fakes present: `fake_gemini.py`, `fake_firestore.py`, `fake_supermemory.py`
- [ ] `FIRESTORE_EMULATOR_HOST` set by session-scoped fixture BEFORE Firestore client import

### 2.4 Security middleware
- [ ] FirebaseAuthMiddleware attached; 6 tests pass
- [ ] CORS rejects `*` at startup (ValueError)
- [ ] Input sanitizer strips XSS, preserves Hindi (Test 3.3)
- [ ] Audit log emits JSON with correlation_id; Test 4.2 regression guard passes
- [ ] Middleware LIFO order comment block in `main.py`

### 2.4b Runtime helpers
- [ ] `python -c "from supply_chain_triage.core.config import get_secret, get_firestore_client, SecretNotFoundError"` → 0
- [ ] `python -c "from supply_chain_triage.middleware.audit_log import audit_event"` → 0

### 2.6 Pydantic schemas
- [ ] 7 schema files in `modules/triage/models/` (6 + learned_preferences helper)
- [ ] `python -c "from supply_chain_triage.modules.triage.models import ExceptionEvent, ClassificationResult, ImpactResult, ShipmentImpact, TriageResult, UserContext, CompanyProfile"` → 0
- [ ] 14 schema tests pass (12 v1 + Test 1.10b + Test 1.12b)

### 2.7 ADK baseline
- [ ] `hello_world_agent` is `LlmAgent(model="gemini-2.5-flash")`
- [ ] `adk web` launches; agent responds in browser
- [ ] `evals/hello_world/greeting.evalset.json` runs green via `adk eval`
- [ ] 1 AgentEvaluator integration test passes with real Gemini

### 2.8 Documentation
- [ ] 8 ADRs in `docs/decisions/` (7 + ADR-008)
- [ ] 5 templates in `docs/templates/`
- [ ] `threat-model.md` + `owasp-checklist.md` present
- [ ] README + CONTRIBUTING + SECURITY render on GitHub

### 2.9 Spiral artifacts
- [ ] All 9 artifacts exist for Sprint 0

---

## 17. Acceptance Criteria (Sprint Gate)

All must be ✅ before Sprint 1 starts.

1. **Tests pass**: `uv run pytest` → 0 with **≥32 tests**.
2. **Coverage reports** (not a blocker): `uv run pytest --cov` emits term-missing + xml.
3. **`adk web` works**: launches on localhost:8000, hello_world responds to a typed message.
4. **Firestore emulator**: `firebase emulators:start --only firestore,auth` runs; integration test writes + reads via emulator.
5. **Pre-commit (user-configured)**: `pre-commit run --all-files` green on clean repo; fails on deliberately bad file.
6. **CI green (user-configured)** on main: ci.yml + security.yml pass; deploy.yml stub exits 0.
7. **Security scan clean**: `bandit -r src/` → 0 high; `safety check` → 0 vulns; `pip-audit` → 0 high.
8. **Docs present**: 8 ADRs + 5 templates + threat-model + OWASP + README/CONTRIBUTING/SECURITY + 5 Sprint 0 Spiral artifacts + 6 research vault copies + 5 Zettels + 1 ADA digest.
9. **Schema import smoke**: all 7 models importable (see §16 2.6).
10. **Auth middleware**: 6 Firebase Auth unit tests green with mocked `verify_id_token`.
11. **`.env.template`** (user-written) documents every env var with a comment.
12. **Directory tree** matches §5 and `.claude/rules/placement.md`; placement hook never rejects a legitimate write.
13. **Sprint 1 backfill helpers importable**: §16 2.4b.
14. **NEW — Import-rule check**: `uv run ruff check .` includes zero `TID251` violations.
15. **NEW — Session note**: `docs/sessions/2026-04-14-sprint-0-complete.md` written.
16. **NEW — Custom claims**: `scripts/set_custom_claims.py` runs against the Firebase test project and sets `company_id`; Test 2.5 positive-case counterpart passes.
17. **NEW — Evalset**: `adk eval src/supply_chain_triage/modules/triage/agents/hello_world evals/hello_world/greeting.evalset.json` → green.

---

## 18. Rollback Plan

If Phase C runs long, trim in order:

### Trim Level 1 — drop nice-to-haves (~1h saved)
- Delete `deploy.yml` workflow (defer Sprint 5)
- Keep only `prd-template.md` + `adr-template.md`
- Defer `owasp-checklist.md` to Sprint 4 (Risk 11 middleware test covers OWASP API2)
- Skip `pip-audit` locally (kept in CI nightly)

### Trim Level 2 — defer non-blocking infra (~1h saved)
- Use `mockfirestore` for integration tests (drop firebase emulator setup)
- Drop AgentEvaluator integration test (keep `adk web` smoke only)
- Drop `mypy` from pre-commit (kept in CI)
- Skip `detect-secrets` baseline

### Trim Level 3 — minimum viable Sprint 0 (~1h saved)
Must have: 14 schema tests, 6 auth middleware tests, ruff-only pre-commit, hello_world + `adk web` smoke, ci.yml running pytest, .env.template + README.

Must NOT be cut: schemas (Sprint 1-3 depend on them), Firebase Auth middleware (Sprint 4 depends), GCP secrets (Sprint 1+ needs Gemini key), `set_custom_claims.py` (Test 2.5 counterpart).

If Trim 3 still doesn't fit: escalate to user. Sprint 1 shift accepted; Should-Have trims in Sprint 5 (React) compressed first.

---

## 19. Security Considerations

Sprint 0 sets security precedent for all subsequent sprints.

1. **No secrets in code.** Secret Manager runtime; `.env` local only. Both gitignored.
2. **Least-privilege IAM.** Dev SA: `secretmanager.secretAccessor` + `datastore.user`. No `owner`/`editor`.
3. **JWT validation on every protected route.** `FirebaseAuthMiddleware` applied globally; public paths are an explicit allowlist.
4. **CORS allowlist.** Wildcards banned — ValueError at startup.
5. **Input sanitization at boundary.** Max body size + XSS + control-char strip. **Preserves Hindi unicode.**
6. **Audit logging every request.** Structured JSON with `correlation_id`, `user_id`, `company_id`.
7. **Dependency scanning every CI run.** bandit + safety + pip-audit. Nightly cron catches new CVEs.
8. **Pre-commit `detect-secrets` + `gitleaks`** catch accidental credential commits.
9. **Firebase custom claims required** — middleware returns 403 if `company_id` missing. Multi-tenant isolation anchor.
10. **`FIREBASE_AUTH_EMULATOR_HOST` discipline** — set in test fixtures and local dev only. **Never** in Cloud Run env (emulator accepts forged tokens).

OWASP API Top 10 coverage in `docs/security/owasp-checklist.md` (Phase D).

---

## 20. Dependencies

**External**: GCP account w/ billing; Firebase CLI; `gcloud` CLI; Python 3.13; Node 20 LTS; Java 17 JRE; `uv`.

**Internal (vault, now copied)**:
- `docs/research/Supply-Chain-Sprint-Plan-Spiral-SDLC.md` — parent sprint plan
- `docs/research/Supply-Chain-Agent-Spec-Coordinator.md` — schema sources
- `docs/research/Supply-Chain-Agent-Spec-Classifier.md` — Rule 3 source
- `docs/research/Supply-Chain-Agent-Spec-Impact.md` — Rule E source
- `docs/research/Supply-Chain-Firestore-Schema-Tier1.md` — data model + Firestore rules
- `docs/research/Architecture-Decision-Analysis-summary.md` — D+F rationale

**Blocking items BEFORE Phase C**:
- [ ] GCP billing confirmed active (Risk 1 pre-check)
- [ ] Gemini API key provisioned
- [ ] Python 3.13 installed locally

---

## 21. Risks (summary)

Full list in `risks.md` (13 risks). Top 3:

| # | Risk | Prob | Sev | Mitigation |
|---|---|---|---|---|
| 2 | IAM permission errors (SA hell) | High | High | `scripts/gcp_bootstrap.sh` version-controlled; `verify_iam.py` asserts roles at boot |
| 10 | Scope creep into Sprint 1 | High | Med | Zero agent logic beyond hello_world; strict discipline |
| 11 | Middleware LIFO ordering regression | Med | Med | Test 4.2 regression guard; `main.py` comment block |
| 12 (NEW) | Supermemory container-tag contract | Med | High | Adapter enforces `company_id` as required positional; `FakeSupermemoryClient` tests the contract |
| 13 (NEW) | Cloud Run SSE buffering (Sprint 4) | Med | High | `X-Accel-Buffering: no` + keep-alive pings; Cloud Run direct not API Gateway |

---

## 22. Success metrics

### Quantitative
- **Time to green CI**: first successful CI run < 4 hours from repo
- **Test count**: **≥32 tests** passing (14 schema + 6 Firebase auth + 3 sanitize + 2 audit + 2 CORS + 1 hello_world + 1 firestore emulator + 2 pre-commit meta + 1 Secret Manager)
- **Coverage**: reports (advisory — no fail gate through Tier 1)
- **Security findings**: 0 high, 0 medium
- **Docs count**: 8 ADRs + 5 templates + 2 security + README/CONTRIBUTING/SECURITY + 5 Spiral artifacts + 6 research vault + 5 Zettels + 1 ADA digest = **35 docs minimum**
- **File count**: ~95 files in the §5 tree

### Qualitative
- A new developer can clone, `make setup && make test`, green in < 15 minutes
- Sprint 1 Day 1 engineer spends **zero** time on infrastructure

---

## 23. Cross-references

- **This project**: `CLAUDE.md`, `.claude/rules/*`, `docs/decisions/adr-001..008.md`
- **Research (copied from vault)**: `docs/research/Supply-Chain-*.md`
- **Zettels** (Obsidian format, Phase A): `docs/research/zettel-*.md`
- **Sibling sprint PRDs**: `docs/sprints/sprint-{1..6}/prd.md` (live in repo, reference this file)
- **Test plan**: `./test-plan.md` (32 tests, Phase A rewrite)
- **Risks**: `./risks.md` (13 risks, Phase B extension)
- **v1 archived**: `./prd-v1-archived.md`
