---
title: "Sprint 0 PRD v1 — ARCHIVED (superseded by prd.md v2)"
type: deep-dive
domains: [supply-chain, hackathon, sdlc]
last_updated: 2026-04-10
archived_on: 2026-04-14
status: superseded
superseded_by: ./prd.md
confidence: high
sources: ["[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]", "[[Supply-Chain-Agent-Spec-Coordinator]]", "[[Supply-Chain-Agent-Spec-Classifier]]", "[[Supply-Chain-Agent-Spec-Impact]]", "[[Supply-Chain-Firestore-Schema-Tier1]]", "[[Supply-Chain-Architecture-Decision-Analysis]]", "[[Supply-Chain-Deployment-Options-Research]]", "[[Supply-Chain-Research-Sources]]"]
---

> **⚠️ ARCHIVED — DO NOT EXECUTE.** This is PRD v1, dated 2026-04-10. On 2026-04-14 it was superseded by `./prd.md` (v2), which reconciles structure, schema, and timeline decisions with the rules in `CLAUDE.md` and `.claude/rules/*`. Differences enumerated in v2 §"Changes from v1". This file is historical reference only; active Sprint 0 execution happens against `prd.md`.

# Sprint 0 PRD v1 — ARCHIVED — Secure Foundation (Comprehensive Execution Guide)

> **Plan authored with:** `superpowers:writing-plans` skill
> **Sprint window:** Apr 10 – Apr 12, 2026 (flexible, max 3 days)
> **Deadline context:** Prototype due Apr 24, 2026 (14 days total)
> **Feature code produced this sprint:** **Zero.** This sprint is pure foundation.
> **Audience:** A new developer should be able to execute Sprint 0 by following this PRD verbatim.

---

## Table of Contents

1. [Objective](#1-objective)
2. [Scope IN](#2-scope-in)
3. [Out-of-Scope](#3-out-of-scope-deferred)
4. [Resolved Decisions](#4-resolved-decisions-formerly-open-assumptions)
5. [Project Directory Tree](#5-project-directory-tree-exact)
6. [pyproject.toml (Full)](#6-pyprojecttoml-full)
7. [Runtime Entry Points](#7-runtime-entry-points)
8. [Pydantic Schemas (Full Code)](#8-pydantic-schemas-full-code)
9. [Middleware (Full Code)](#9-middleware-full-code)
10. [Config & Environment](#10-config--environment)
11. [Tooling Files](#11-tooling-files)
12. [CI/CD Workflows](#12-cicd-workflows)
13. [Documentation Templates](#13-documentation-templates)
14. [Scripts](#14-scripts)
15. [Day-by-Day Build Sequence](#15-day-by-day-build-sequence)
16. [Definition of Done per Sub-Scope](#16-definition-of-done-per-sub-scope)
17. [Acceptance Criteria (Sprint Gate)](#17-acceptance-criteria-sprint-gate)
18. [Rollback Plan](#18-rollback-plan-if-sprint-0-blows-past-3-days)
19. [Security Considerations](#19-security-considerations)
20. [Dependencies](#20-dependencies)
21. [Risks](#21-risks-summary)
22. [Success Metrics](#22-success-metrics)
23. [Cross-References](#23-cross-references)

---

## 1. Objective

Stand up **everything** a feature-sprint engineer needs before touching business logic: secure GCP infrastructure, Python project skeleton, test harness with mocks, security middleware, pre-commit + CI pipelines, Pydantic schemas, ADK hello-world baseline, and all documentation templates + initial ADRs.

**One-sentence goal:** Every subsequent sprint (1–6) should be able to focus 100% on feature delivery without touching infrastructure.

**Why this sprint exists:** Spiral SDLC's Plan → Risk → Engineer → Evaluate cycle requires stable infrastructure to iterate on. Skipping foundation burns feature-sprint time on yak-shaving. [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] explicitly budgets 2–3 flexible days here so Sprints 1–6 can each ship a feature in ~2 days.

---

## 2. Scope (IN)

### 2.1 GCP + Security Foundation
- GCP project + billing enabled
- IAM roles with least-privilege (`roles/secretmanager.secretAccessor` to dev SA only; Cloud Run SA deferred to Sprint 5)
- Secret Manager configured for `GEMINI_API_KEY`, `SUPERMEMORY_API_KEY`, `FIREBASE_SERVICE_ACCOUNT`
- Firebase project + Auth enabled (Google Sign-In OAuth provider)
- Firestore instance (Native mode, `asia-south1` — Mumbai for India target market)

### 2.2 Python Project Skeleton
- `src/` layout per 2026 Python Packaging standards
- `pyproject.toml` with dependency groups: `dev`, `test`, `docs`, `security`
- **Python 3.13** (verified ADK compatible — Resolved Decision #1)
- **`uv`** as package manager / lockfile tool (Resolved Decision #2)

### 2.3 Test Harness
- `pytest >= 7.3.2` + `pytest-asyncio >= 0.21.0` + `pytest-cov`
- `@pytest.mark.asyncio` baseline config in `pyproject.toml`
- `InMemoryMemoryService` for fast unit tests
- Firestore emulator for integration tests
- Mock/fake implementations: `FakeGeminiClient`, `FakeSupermemoryClient`, `FakeFirestoreClient`
- `make test` and `make coverage` wired up

### 2.4 Security Middleware
- **Firebase Auth via `firebase-admin` SDK** + `verify_id_token()` pattern (Resolved Decision #4)
- CORS allowlist (env-based: dev vs prod)
- Input sanitization utilities (XSS, control-char stripping)
- Audit logging framework (structured JSON, correlation IDs) — **plus** a module-level `audit_event(event, **kwargs)` helper so agents/tools can emit structured audit events outside the HTTP middleware context (Sprint 1 dependency — see §10.4)
- Rate-limiter stub (real enforcement Sprint 4)

### 2.4b Runtime helpers (Sprint 1 dependency backfill)
- `config.get_secret(key)` — runtime Secret Manager fetch with in-process cache + test-mode fallback + `SecretNotFoundError`
- `config.get_firestore_client()` — cached async Firestore client factory (production + emulator)
- `middleware.audit_log.audit_event(event, **kwargs)` — structured audit logger usable outside HTTP middleware
- Full contracts in §10.4

### 2.5 Pre-commit + CI
- `.pre-commit-config.yaml` with `ruff` (replaces Black + Flake8 + isort + pyupgrade), `mypy`, `bandit`, `detect-secrets`
- `.github/workflows/ci.yml` — lint + test + coverage on push/PR
- `.github/workflows/security.yml` — `bandit`, `safety`, `pip-audit` nightly
- `.github/workflows/deploy.yml` — **stubbed** with TODO referencing `Supply-Chain-Deployment-Options-Research.md` (Resolved Decision #9)

### 2.6 Pydantic Schemas (all 6)
Per [[Supply-Chain-Agent-Spec-Coordinator]], [[Supply-Chain-Agent-Spec-Classifier]], [[Supply-Chain-Agent-Spec-Impact]], [[Supply-Chain-Firestore-Schema-Tier1]]:
- `schemas/exception_event.py` — `ExceptionEvent`
- `schemas/classification.py` — `ClassificationResult` + `ExceptionType` + `Severity`
- `schemas/impact.py` — `ImpactResult`, `ShipmentImpact`
- `schemas/triage_result.py` — `TriageResult`
- `schemas/user_context.py` — `UserContext`
- `schemas/company_profile.py` — `CompanyProfile`
- Each schema has a round-trip test (serialize → parse → equality)
- Pydantic v2 (50× faster per FastAPI Best Practices 2026)

### 2.7 ADK Baseline
- `hello_world_agent` as `LlmAgent(model="gemini-2.5-flash")`
- `adk web` launches and agent responds to "hello"
- One passing `AgentEvaluator.evaluate()` test

### 2.8 Documentation Infrastructure
- `docs/` skeleton: `architecture/`, `decisions/`, `sprints/`, `security/`, `api/`, `templates/`, `onboarding/`
- Templates: PRD, ADR, test plan, retrospective, sprint layout
- `README.md` + `CONTRIBUTING.md` + `SECURITY.md`
- 7 ADRs: ADR-001 (Framework) through ADR-007 (UI Strategy)
- Threat model: `docs/security/threat-model.md`
- OWASP API Top 10 checklist: `docs/security/owasp-checklist.md`

---

## 3. Out-of-Scope (Deferred)

| Item | Deferred to | Reason |
|------|-------------|--------|
| Classifier Agent business logic | Sprint 1 | Feature sprint |
| Impact Agent business logic | Sprint 2 | Feature sprint |
| Coordinator delegation rules A–F | Sprint 3 | Feature sprint |
| `/triage/stream` endpoint | Sprint 4 | Feature sprint |
| **Real deployment (Cloud Run / Render / other)** | **Sprint 5** | **4 options researched in `Supply-Chain-Deployment-Options-Research.md`; choice deferred** |
| **Dockerfile / docker-compose** | **Sprint 5** | **User directive: "Docker is the last type of setup"** |
| React frontend | Sprint 5 | Using `adk web` until then (ADR-007) |
| Supermemory real integration | Sprint 3 | Fake adapter only here |
| Guardrails AI validators | Sprint 1 | Only interface stub here |
| Rate limit enforcement | Sprint 4 | Stub only |
| NH-48 seed data | Sprint 2 | Firestore schema ready, data later |

---

## 4. Resolved Decisions (formerly Open Assumptions)

The 7 open assumptions from the previous PRD iteration have been resolved. This PRD applies them throughout.

| # | Decision | Value | Rationale |
|---|----------|-------|-----------|
| 1 | Python version | **3.13** | Verified ADK-compatible. Modern async, PEP 695 generics, improved error messages. |
| 2 | Package manager | **uv** | 10–100x faster resolver than pip, lockfile deterministic, Astral ecosystem matches ruff. |
| 3 | Firestore region | **asia-south1 (Mumbai)** | Target market is India; <50ms latency from Mumbai/Pune test users. |
| 4 | Auth library | **firebase-admin SDK** (NOT `fastapi-cloudauth`) | Google's first-party Python SDK, `verify_id_token()` canonical pattern, native Firestore custom-claims integration. Google Sign-In is the OAuth provider. |
| 5 | Local dev secrets | **Personal `.env` files only** | No Docker / docker-compose this sprint. Each dev uses their own GCP free-tier project. |
| 6 | Test framework | **pytest** | Standard, async-friendly, coverage plugin, ADK uses it. |
| 7 | Deployment target | **DEFERRED to Sprint 5** | 4 options fully researched in `Supply-Chain-Deployment-Options-Research.md` — choose post-prototype. |
| 8 | CI/CD framework | **GitHub Actions** | Free for public repos, matches hackathon workflow. Workflow skeleton in Sprint 0; deploy step **STUB** until Sprint 5. |
| 9 | Dockerfile in Sprint 0 | **NO** | User directive: "Docker is the last type of setup." Deferred to Sprint 5 production hardening. |

---

## 5. Project Directory Tree (Exact)

Every file below MUST be created by end of Sprint 0. Files marked `(stub)` contain a placeholder comment and a `TODO(sprint-N)` reference.

```
supply_chain_triage/
├── README.md
├── CONTRIBUTING.md
├── SECURITY.md
├── LICENSE                         # MIT
├── pyproject.toml
├── uv.lock                         # Generated by `uv lock`
├── Makefile
├── .env.template
├── .env                            # Gitignored
├── .gitignore
├── .pre-commit-config.yaml
├── .python-version                 # Contains: 3.13
├── .secrets.baseline               # Pre-generated empty baseline (committed)
├── .github/
│   └── workflows/
│       ├── ci.yml
│       ├── security.yml
│       └── deploy.yml              # (stub — deferred to Sprint 5)
├── src/
│   └── supply_chain_triage/
│       ├── __init__.py
│       ├── main.py                 # FastAPI + ADK bootstrap
│       ├── config.py               # Pydantic Settings
│       ├── agents/
│       │   ├── __init__.py
│       │   ├── hello_world.py      # LlmAgent(gemini-2.5-flash)
│       │   └── prompts/
│       │       └── hello_world.md
│       ├── schemas/
│       │   ├── __init__.py
│       │   ├── exception_event.py
│       │   ├── classification.py
│       │   ├── impact.py
│       │   ├── triage_result.py
│       │   ├── user_context.py
│       │   └── company_profile.py
│       ├── middleware/
│       │   ├── __init__.py
│       │   ├── firebase_auth.py
│       │   ├── cors.py
│       │   ├── audit_log.py
│       │   ├── rate_limit.py       # (stub)
│       │   └── input_sanitization.py
│       ├── memory/
│       │   ├── __init__.py
│       │   └── provider.py         # (stub — interface only)
│       ├── guardrails/
│       │   └── __init__.py         # (stub)
│       ├── tools/
│       │   └── __init__.py         # (empty, populated Sprint 1–3)
│       └── runners/
│           ├── __init__.py
│           └── agent_runner.py     # Framework-portability interface (ADR-001)
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── __init__.py
│   │   ├── fake_gemini.py
│   │   ├── fake_supermemory.py
│   │   └── fake_firestore.py
│   ├── unit/
│   │   ├── __init__.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── test_exception_event.py
│   │   │   ├── test_classification.py
│   │   │   ├── test_impact.py
│   │   │   ├── test_triage_result.py
│   │   │   ├── test_user_context.py
│   │   │   └── test_company_profile.py
│   │   ├── middleware/
│   │   │   ├── __init__.py
│   │   │   ├── test_firebase_auth.py
│   │   │   ├── test_cors.py
│   │   │   ├── test_audit_log.py
│   │   │   └── test_input_sanitization.py
│   │   └── agents/
│   │       ├── __init__.py
│   │       └── test_hello_world.py
│   ├── integration/
│   │   ├── __init__.py
│   │   ├── firestore/
│   │   │   ├── __init__.py
│   │   │   └── test_emulator_roundtrip.py
│   │   └── test_secret_manager.py
│   └── e2e/
│       └── __init__.py             # (empty for Sprint 0)
├── infra/
│   ├── firestore.rules
│   ├── firestore.indexes.json
│   └── firebase.json
├── scripts/
│   ├── setup.sh
│   ├── seed_firestore.py           # (stub — populated Sprint 2)
│   ├── gcp_bootstrap.sh
│   ├── deploy.sh                   # (stub — deferred to Sprint 5)
│   └── seed/
│       ├── festival_calendar.json  # `[]` (Sprint 1 populates)
│       ├── monsoon_regions.json    # `[]` (Sprint 1 populates)
│       ├── shipments.json          # `[]` (Sprint 2 populates)
│       ├── customers.json          # `[]` (Sprint 2 populates)
│       ├── companies.json          # `[]` (Sprint 2 populates)
│       └── users.json              # `[]` (Sprint 2 populates)
└── docs/
    ├── architecture/
    │   └── overview.md
    ├── decisions/
    │   ├── adr-001-framework-choice.md
    │   ├── adr-002-memory-layer.md
    │   ├── adr-003-prompt-format.md
    │   ├── adr-004-streaming-strategy.md
    │   ├── adr-005-testing-strategy.md
    │   ├── adr-006-sdlc-choice.md
    │   └── adr-007-ui-strategy.md
    ├── sprints/
    │   └── sprint-0/
    │       ├── impl-log.md
    │       ├── test-report.md
    │       ├── review.md           # Populated at sprint end
    │       └── retro.md            # Populated at sprint end
    ├── security/
    │   ├── threat-model.md
    │   └── owasp-checklist.md
    ├── api/
    │   └── openapi.json            # (stub)
    ├── templates/
    │   ├── prd-template.md
    │   ├── adr-template.md
    │   ├── test-plan-template.md
    │   ├── retrospective-template.md
    │   └── sprint-layout-template.md
    └── onboarding/
        ├── setup.md
        └── gcp-setup.md
```

**Total files created in Sprint 0: ~103 files** (includes `runners/agent_runner.py`, `.secrets.baseline`, and 6 `scripts/seed/*.json` skeletons).

---

## 6. pyproject.toml (Full)

```toml
[build-system]
requires = ["hatchling>=1.24.0"]
build-backend = "hatchling.build"

[project]
name = "supply-chain-triage"
version = "0.1.0"
description = "AI-powered exception triage for small 3PLs in India (ADK + Gemini + Firebase)"
readme = "README.md"
license = { file = "LICENSE" }
requires-python = ">=3.13,<3.14"
authors = [
  { name = "Krrish", email = "noreply@example.com" },
]
keywords = ["adk", "gemini", "supply-chain", "agents", "firebase"]
classifiers = [
  "Development Status :: 2 - Pre-Alpha",
  "Programming Language :: Python :: 3.13",
  "Framework :: FastAPI",
  "License :: OSI Approved :: MIT License",
]

dependencies = [
  # --- Agent framework ---
  "google-adk>=1.0.0",                 # Pin to exact version once verified
  "google-generativeai>=0.8.0",
  "google-cloud-secret-manager>=2.20.0",

  # --- Web framework ---
  "fastapi>=0.115.0",
  "uvicorn[standard]>=0.32.0",

  # --- Auth ---
  "firebase-admin>=6.5.0",             # Resolved Decision #4

  # --- Data layer ---
  "google-cloud-firestore>=2.18.0",

  # --- Validation ---
  "pydantic>=2.9.0",
  "pydantic-settings>=2.5.0",

  # --- Utilities ---
  "python-dotenv>=1.0.1",
  "structlog>=24.4.0",                 # Structured JSON logging
  "httpx>=0.27.0",
]

[project.optional-dependencies]
test = [
  "pytest>=7.3.2",
  "pytest-asyncio>=0.21.0",
  "pytest-cov>=5.0.0",
  "pytest-mock>=3.14.0",
  "httpx>=0.27.0",                     # Required by TestClient
  "mockfirestore>=0.11.0",             # Fallback if emulator unavailable
]

dev = [
  "ruff>=0.8.0",                       # Replaces black+flake8+isort+pyupgrade
  "mypy>=1.13.0",
  "pre-commit>=4.0.0",
  "types-requests",
]

security = [
  "bandit>=1.7.10",
  "safety>=3.2.0",
  "pip-audit>=2.7.0",
  "detect-secrets>=1.5.0",
]

docs = [
  "mkdocs>=1.6.0",
  "mkdocs-material>=9.5.0",
]

[project.scripts]
supply-chain-triage = "supply_chain_triage.main:cli"

# --- uv config ---
[tool.uv]
dev-dependencies = [
  "supply-chain-triage[test,dev,security]",
]

# --- ruff ---
[tool.ruff]
line-length = 100
target-version = "py313"
src = ["src", "tests"]

[tool.ruff.lint]
select = [
  "E", "F", "W",   # pycodestyle + pyflakes
  "I",             # isort
  "B",             # bugbear
  "UP",            # pyupgrade
  "SIM",           # simplify
  "S",             # bandit-lite
  "C90",           # mccabe complexity
]
ignore = [
  "S101",          # Allow `assert` in tests
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["S101", "S105", "S106"]  # Tests may use assert + fake credentials

[tool.ruff.format]
quote-style = "double"
indent-style = "space"

# --- mypy ---
[tool.mypy]
python_version = "3.13"
strict = true
warn_unused_configs = true
warn_redundant_casts = true
warn_unused_ignores = true
disallow_untyped_defs = true
disallow_incomplete_defs = true
check_untyped_defs = true
# NOTE: do NOT set `ignore_missing_imports = true` globally — it conflicts
# with `strict = true` (which enables `warn_unused_ignores`). Instead,
# scope `ignore_missing_imports` per-module below.

[[tool.mypy.overrides]]
module = ["google.adk.*", "firebase_admin.*", "mockfirestore.*"]
ignore_missing_imports = true

[[tool.mypy.overrides]]
module = "tests.*"
disallow_untyped_defs = false

# --- pytest ---
[tool.pytest.ini_options]
minversion = "7.3.2"
asyncio_mode = "auto"
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = [
  "-ra",
  "--strict-markers",
  "--strict-config",
  "--cov=src/supply_chain_triage",
  "--cov-report=term-missing",
  "--cov-report=xml",
  "--cov-fail-under=80",
]
markers = [
  "integration: marks tests requiring external services (emulator, Gemini)",
  "slow: slow tests (>2s)",
]

# --- coverage ---
[tool.coverage.run]
branch = true
source = ["src/supply_chain_triage"]
omit = [
  "*/main.py",
  "*/__init__.py",
]

[tool.coverage.report]
exclude_lines = [
  "pragma: no cover",
  "raise NotImplementedError",
  "if TYPE_CHECKING:",
]

# --- bandit ---
[tool.bandit]
exclude_dirs = ["tests", ".venv", ".git"]
skips = ["B101"]                       # Allow assert
```

---

## 7. Runtime Entry Points

### 7.1 `src/supply_chain_triage/main.py`

```python
"""
FastAPI + ADK bootstrap.

Wires up:
- Firebase Admin SDK initialization (for verify_id_token())
- CORS middleware
- Audit logging middleware
- Input sanitization middleware
- Firebase Auth middleware
- ADK FastAPI app via get_fast_api_app()
"""
from __future__ import annotations

import logging
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import firebase_admin
import structlog
from fastapi import FastAPI
from firebase_admin import credentials
from google.adk.cli.fast_api import get_fast_api_app

from supply_chain_triage.config import get_settings
from supply_chain_triage.middleware.audit_log import AuditLogMiddleware
from supply_chain_triage.middleware.cors import add_cors_middleware
from supply_chain_triage.middleware.firebase_auth import FirebaseAuthMiddleware
from supply_chain_triage.middleware.input_sanitization import (
    InputSanitizationMiddleware,
)

logger = structlog.get_logger(__name__)


def _init_firebase() -> None:
    """Initialize firebase-admin SDK once per process."""
    settings = get_settings()
    if firebase_admin._apps:  # type: ignore[attr-defined]
        return
    cred_path = Path(settings.firebase_service_account_path)
    if not cred_path.exists():
        raise FileNotFoundError(
            f"Firebase service account key not found at {cred_path}. "
            "Set FIREBASE_SERVICE_ACCOUNT_PATH in .env."
        )
    cred = credentials.Certificate(str(cred_path))
    firebase_admin.initialize_app(
        cred,
        {"projectId": settings.firebase_project_id},
    )
    logger.info("firebase_admin.initialized", project=settings.firebase_project_id)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    _init_firebase()
    yield


def create_app() -> FastAPI:
    """Create the FastAPI app with ADK mounted and middleware layered."""
    settings = get_settings()

    # Configure structlog
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer(),
        ],
    )

    # ADK's get_fast_api_app() returns a FastAPI app with the agent mounted.
    # We point it at our agents/ directory so it auto-discovers hello_world.
    agents_dir = Path(__file__).parent / "agents"
    app: FastAPI = get_fast_api_app(
        agents_dir=str(agents_dir),
        allow_origins=settings.cors_origins,
        web=True,  # Enables adk web UI
    )
    app.router.lifespan_context = lifespan

    # Layer middleware. Starlette applies `add_middleware` in LIFO order,
    # so the LAST one added becomes the OUTERMOST wrapper on the request.
    # We want AuditLog to be outermost so it captures correlation_id even
    # when FirebaseAuth returns 401/403 short-circuit responses.
    #
    # Execution order on an incoming request (outer → inner):
    #   AuditLog → FirebaseAuth → InputSanitization → CORS → route
    add_cors_middleware(app, settings.cors_origins)  # 1st added → innermost (OK)
    app.add_middleware(InputSanitizationMiddleware)
    app.add_middleware(FirebaseAuthMiddleware)
    app.add_middleware(AuditLogMiddleware)           # last added → outermost

    logger.info("app.created", environment=settings.environment)
    return app


app = create_app()


def cli() -> None:
    """Console entry point: `supply-chain-triage`."""
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "supply_chain_triage.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=(settings.environment == "dev"),
        log_level=settings.log_level.lower(),
    )


if __name__ == "__main__":
    sys.exit(cli())
```

### 7.2 `src/supply_chain_triage/agents/hello_world.py`

```python
"""
Hello World ADK agent — the canonical Sprint 0 sanity check.

Replaces any feature logic. Proves:
1. ADK installed correctly
2. Gemini API key works
3. `adk web` launches
4. AgentEvaluator can drive the agent
"""
from google.adk.agents import LlmAgent

HELLO_INSTRUCTION = """# Hello World Agent

You are a greeting agent. When the user says "hello" or any greeting,
respond with a warm one-sentence greeting mentioning that the
Exception Triage Module foundation is ready.

Keep responses under 30 words. Do not claim any supply chain capabilities
yet — those come in Sprint 1+.
"""

hello_world_agent = LlmAgent(
    name="hello_world",
    model="gemini-2.5-flash",
    description="Sanity-check agent for Sprint 0 foundation.",
    instruction=HELLO_INSTRUCTION,
)
```

### 7.3 `src/supply_chain_triage/runners/agent_runner.py` (interface stub)

Per ADR-001, the project reserves a framework-portability abstraction at
`runners/agent_runner.py`. Sprint 0 lands the **interface only**; the
concrete implementation that wraps ADK's `Runner` (and future BeeAI /
LangGraph runners) arrives in Sprint 3.

```python
"""Framework-portability abstraction layer — Sprint 0 interface stub.

Implementation layer (wrapping ADK's Runner) lands in Sprint 3. The
interface lives now so downstream code (coordinator, API handlers, tests)
can depend on this ABC from day one without binding to a specific SDK.

See docs/decisions/adr-001-framework-choice.md for the rationale behind
keeping the agent SDK swappable.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, AsyncIterator


class AgentRunner(ABC):
    """Abstract interface for running an agent independent of the
    underlying SDK (ADK, BeeAI, LangGraph, etc.)."""

    @abstractmethod
    async def run(
        self,
        input_data: dict[str, Any],
        session_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Run the agent once and return the final result."""
        ...

    @abstractmethod
    async def stream(
        self,
        input_data: dict[str, Any],
        session_state: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Stream agent events incrementally."""
        ...
```

---

## 8. Pydantic Schemas (Full Code)

All schemas use Pydantic v2 syntax. Each file MUST have a corresponding `tests/unit/schemas/test_<name>.py` with round-trip + invalid-input tests.

### 8.1 `src/supply_chain_triage/schemas/exception_event.py`

```python
"""ExceptionEvent — raw input to the triage pipeline."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

SourceChannel = Literal[
    "whatsapp_voice",
    "whatsapp_text",
    "email",
    "phone_call_transcript",
    "carrier_portal_alert",
    "customer_escalation",
    "manual_entry",
]


class ExceptionEvent(BaseModel):
    """The raw exception event received by the Coordinator."""

    model_config = ConfigDict(extra="forbid", frozen=False)

    event_id: str = Field(..., description="Unique ID for this exception", min_length=1)
    timestamp: datetime
    source_channel: SourceChannel
    sender: dict[str, Any] = Field(..., description="Sender metadata (name, role, etc.)")
    raw_content: str = Field(..., min_length=1, max_length=50_000)
    original_language: str | None = None
    english_translation: str | None = None
    media_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
```

### 8.2 `src/supply_chain_triage/schemas/classification.py`

```python
"""ClassificationResult — output of the Classifier Agent."""
from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ExceptionType(str, Enum):
    carrier_capacity_failure = "carrier_capacity_failure"
    route_disruption = "route_disruption"
    regulatory_compliance = "regulatory_compliance"
    customer_escalation = "customer_escalation"
    external_disruption = "external_disruption"
    safety_incident = "safety_incident"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ClassificationResult(BaseModel):
    """Structured classification from the Classifier Agent."""

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    exception_type: ExceptionType
    subtype: str = Field(..., min_length=1)
    severity: Severity
    urgency_hours: int | None = Field(
        None, ge=0, description="Estimated hours until situation becomes critical"
    )
    confidence: float = Field(..., ge=0.0, le=1.0)

    key_facts: dict[str, Any] = Field(
        ..., description="Structured facts extracted from raw content"
    )
    reasoning: str = Field(..., min_length=1, max_length=2000)
    requires_human_approval: bool = False
    tools_used: list[str] = Field(default_factory=list)
    safety_escalation: dict[str, Any] | None = None
```

### 8.3 `src/supply_chain_triage/schemas/impact.py`

```python
"""ImpactResult + ShipmentImpact — output of the Impact Agent."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ShipmentImpact(BaseModel):
    """Impact assessment for a single affected shipment."""

    model_config = ConfigDict(extra="forbid")

    shipment_id: str = Field(..., min_length=1)
    customer_id: str = Field(..., min_length=1)
    customer_name: str
    customer_tier: Literal["high_value", "repeat_standard", "new", "b2b_enterprise"]
    customer_type: Literal["d2c", "b2b", "marketplace"]

    product_description: str
    value_inr: int = Field(..., ge=0)
    destination: str

    deadline: str = Field(..., description="ISO 8601 timestamp")
    hours_until_deadline: float

    sla_breach_risk: Literal["LOW", "MEDIUM", "HIGH", "CRITICAL"]
    churn_risk: Literal["LOW", "MEDIUM", "HIGH"]
    penalty_amount_inr: int | None = Field(None, ge=0)

    # Rule E: Reputation risk flag
    public_facing_deadline: bool = False
    reputation_risk_note: str | None = None
    reputation_risk_source: Literal["metadata_flag", "llm_inference"] | None = None

    special_notes: str | None = None


class ImpactResult(BaseModel):
    """Aggregate impact result returned by the Impact Agent."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    affected_shipments: list[ShipmentImpact] = Field(default_factory=list)

    total_value_at_risk_inr: int = Field(..., ge=0)
    total_penalty_exposure_inr: int = Field(..., ge=0)
    estimated_churn_impact_inr: int | None = Field(None, ge=0)

    critical_path_shipment_id: str | None = None
    recommended_priority_order: list[str] = Field(default_factory=list)
    priority_reasoning: str = ""

    impact_weights_used: dict[str, Any] = Field(
        default_factory=dict,
        description="Weights LLM chose for (value, penalty, churn) and why",
    )

    has_reputation_risks: bool = False
    reputation_risk_shipments: list[str] = Field(default_factory=list)

    tools_used: list[str] = Field(default_factory=list)
    summary: str = ""
```

### 8.4 `src/supply_chain_triage/schemas/triage_result.py`

```python
"""TriageResult — combined output of the full triage pipeline."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from supply_chain_triage.schemas.classification import ClassificationResult
from supply_chain_triage.schemas.impact import ImpactResult

TriageStatus = Literal[
    "complete",
    "partial",
    "escalated_to_human",
    "escalated_to_human_safety",
]

EscalationPriority = Literal[
    "standard",
    "reputation_risk",
    "safety",
    "regulatory",
]


class TriageResult(BaseModel):
    """Final structured triage result returned to the UI."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    status: TriageStatus
    coordinator_trace: list[dict[str, Any]] = Field(default_factory=list)
    classification: ClassificationResult | None = None
    impact: ImpactResult | None = None
    summary: str
    processing_time_ms: int = Field(..., ge=0)
    errors: list[str] = Field(default_factory=list)
    escalation_priority: EscalationPriority | None = None
```

### 8.5 `src/supply_chain_triage/schemas/user_context.py`

```python
"""UserContext — injected into Coordinator prompt at runtime."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WorkingHours(BaseModel):
    start: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class UserContext(BaseModel):
    """User profile fetched from Supermemory, formatted as markdown for prompt."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    company_id: str

    # Identity
    name: str
    email: str
    role: str
    experience_years: int = Field(..., ge=0)
    city: str
    state: str
    timezone: str

    # Volume & Workload
    avg_daily_shipments: int = Field(..., ge=0)
    avg_daily_exceptions: int = Field(..., ge=0)
    busiest_days: list[str] = Field(default_factory=list)
    workload_classification: str

    # Communication preferences
    preferred_language: str                # REQUIRED per Test 1.9
    tone: str
    formality: str
    notification_channels: list[str] = Field(default_factory=list)

    working_hours: WorkingHours

    # Learned preferences (populated over time)
    override_patterns: list[str] = Field(default_factory=list)
    learned_priorities: dict = Field(default_factory=dict)

    def to_markdown(self) -> str:
        """Render UserContext as markdown sections for prompt injection."""
        return (
            f"## Identity\n"
            f"- Name: {self.name}\n"
            f"- Role: {self.role}\n"
            f"- Experience: {self.experience_years} years in logistics\n"
            f"- Location: {self.city}, {self.state}\n"
            f"- Working hours: {self.timezone}, "
            f"{self.working_hours.start}-{self.working_hours.end}\n\n"
            f"## Volume & Workload\n"
            f"- Daily volume: {self.avg_daily_shipments} shipments handled\n"
            f"- Exception rate: {self.avg_daily_exceptions} per day\n"
            f"- Peak days: {', '.join(self.busiest_days) or 'n/a'}\n"
            f"- Burden level: {self.workload_classification}\n\n"
            f"## Communication Preferences\n"
            f"- Preferred language: {self.preferred_language}\n"
            f"- Communication style: {self.tone}\n"
            f"- Formality: {self.formality}\n"
            f"- Notification channels: "
            f"{', '.join(self.notification_channels) or 'n/a'}\n"
        )
```

### 8.6 `src/supply_chain_triage/schemas/company_profile.py`

```python
"""CompanyProfile — company metadata, required by Classifier severity validator."""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CustomerPortfolio(BaseModel):
    model_config = ConfigDict(extra="forbid")
    d2c_percentage: float = Field(..., ge=0.0, le=1.0)
    b2b_percentage: float = Field(..., ge=0.0, le=1.0)
    b2b_enterprise_percentage: float = Field(..., ge=0.0, le=1.0)
    top_customers: list[str] = Field(default_factory=list)


class CompanyProfile(BaseModel):
    """Company profile stored in Firestore + Supermemory."""

    model_config = ConfigDict(extra="forbid")

    company_id: str = Field(..., min_length=1)
    name: str
    profile_summary: str

    num_trucks: int = Field(..., ge=0)
    num_employees: int = Field(..., ge=0)
    regions_of_operation: list[str] = Field(default_factory=list)
    carriers: list[str] = Field(default_factory=list)

    customer_portfolio: CustomerPortfolio

    # REQUIRED per Classifier Rule 3 (5% relative revenue threshold)
    avg_daily_revenue_inr: int = Field(
        ...,
        ge=0,
        description="Daily revenue in INR — required for Classifier severity validator",
    )

    active: bool = True
```

---

## 9. Middleware (Full Code)

### 9.1 `src/supply_chain_triage/middleware/firebase_auth.py`

```python
"""
Firebase Auth middleware — verifies Firebase ID tokens using the
first-party firebase-admin SDK (Resolved Decision #4).

Extracts uid, email, and custom claims (company_id, user_id) from the
verified token and attaches them to request.state for downstream handlers.
"""
from __future__ import annotations

from typing import Awaitable, Callable

import structlog
from fastapi import Request, Response
from fastapi.responses import JSONResponse
from firebase_admin import auth as firebase_auth
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

# Paths that skip auth (health checks, ADK web UI assets, CORS preflight)
PUBLIC_PATHS: frozenset[str] = frozenset({
    "/health",
    "/docs",
    "/openapi.json",
    "/redoc",
    "/",
})


class FirebaseAuthMiddleware(BaseHTTPMiddleware):
    """Verify Firebase ID token on every protected route."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        # Skip auth for public paths and OPTIONS preflight
        if request.method == "OPTIONS" or request.url.path in PUBLIC_PATHS:
            return await call_next(request)

        # Skip auth for ADK web UI static assets (Sprint 0 convenience)
        if request.url.path.startswith(("/static", "/dev-ui")):
            return await call_next(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            logger.warning("auth.missing_credentials", path=request.url.path)
            return JSONResponse(
                status_code=401,
                content={"error": "missing_credentials"},
            )

        token = auth_header.removeprefix("Bearer ").strip()
        if not token:
            return JSONResponse(
                status_code=401,
                content={"error": "missing_credentials"},
            )

        try:
            decoded = firebase_auth.verify_id_token(
                token,
                check_revoked=False,  # Set True in Sprint 4 hardening
            )
        except firebase_auth.ExpiredIdTokenError:
            logger.info("auth.token_expired")
            return JSONResponse(
                status_code=401,
                content={"error": "token_expired"},
            )
        except firebase_auth.InvalidIdTokenError:
            logger.warning("auth.invalid_signature")
            return JSONResponse(
                status_code=401,
                content={"error": "invalid_signature"},
            )
        except Exception as exc:
            # Generic catch-all. Test 2.6 asserts a plain ValueError from
            # verify_id_token yields a 401 here so this branch is covered.
            logger.error("auth.verify_failed", error=str(exc))
            return JSONResponse(
                status_code=401,
                content={"error": "invalid_token"},
            )

        # Attach identity + custom claims to request.state
        request.state.user_id = decoded["uid"]
        request.state.email = decoded.get("email")
        request.state.company_id = decoded.get("company_id")  # Custom claim
        request.state.firebase_claims = decoded

        if not request.state.company_id:
            logger.warning(
                "auth.missing_company_claim",
                user_id=request.state.user_id,
            )
            return JSONResponse(
                status_code=403,
                content={"error": "missing_company_claim"},
            )

        return await call_next(request)
```

### 9.2 `src/supply_chain_triage/middleware/cors.py`

```python
"""CORS middleware — environment-based allowlist."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


def add_cors_middleware(app: FastAPI, allowed_origins: list[str]) -> None:
    """
    Attach CORS with explicit allowlist. Wildcards are banned in prod.

    Dev: ["http://localhost:3000", "http://localhost:8080"]
    Prod: ["https://<firebase-hosting-url>"]
    """
    if not allowed_origins:
        raise ValueError("CORS_ORIGINS must not be empty")
    if "*" in allowed_origins:
        raise ValueError("Wildcard CORS is banned (security policy)")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Correlation-ID"],
        max_age=600,
    )
```

### 9.3 `src/supply_chain_triage/middleware/audit_log.py`

```python
"""
Audit logging middleware — structured JSON logs with correlation IDs.

Every request gets a correlation_id (from X-Correlation-ID header or generated).
Logs include user_id, company_id, method, path, status, duration_ms.
"""
from __future__ import annotations

import time
import uuid
from typing import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = structlog.get_logger("audit")


def audit_event(event: str, **kwargs) -> None:
    """Emit a structured audit event OUTSIDE the HTTP middleware context.

    The `AuditLogMiddleware` class below covers the request lifecycle (one
    log per request). This helper is for agents, tools, and callbacks that
    need to emit their own audit entries outside of a request — e.g., the
    Classifier `after_agent_callback` in Sprint 1 logs `classifier.classified`
    with the raw_content hash and final severity.

    Reuses the same `structlog` sink as the middleware, so `correlation_id`
    (and any other contextvars bound by the middleware) are automatically
    included when available.
    """
    logger.info(event, **kwargs)


class AuditLogMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        correlation_id = request.headers.get("X-Correlation-ID") or str(uuid.uuid4())
        request.state.correlation_id = correlation_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(
            correlation_id=correlation_id,
            method=request.method,
            path=request.url.path,
        )

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception as exc:
            duration_ms = int((time.perf_counter() - start) * 1000)
            logger.error(
                "request.exception",
                duration_ms=duration_ms,
                error=str(exc),
                user_id=getattr(request.state, "user_id", None),
                company_id=getattr(request.state, "company_id", None),
            )
            raise

        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "request.completed",
            status=response.status_code,
            duration_ms=duration_ms,
            user_id=getattr(request.state, "user_id", None),
            company_id=getattr(request.state, "company_id", None),
        )
        response.headers["X-Correlation-ID"] = correlation_id
        return response
```

### 9.4 `src/supply_chain_triage/middleware/input_sanitization.py`

```python
"""
Input sanitization middleware + utilities.

Defense-in-depth: strips XSS script tags, control characters, and
enforces length limits at the HTTP boundary, before Pydantic parsing.

NOT a replacement for Pydantic validation — this is the first line.
"""
from __future__ import annotations

import re
from typing import Awaitable, Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Compile once
_SCRIPT_TAG_RE = re.compile(r"<\s*script[^>]*>.*?<\s*/\s*script\s*>", re.IGNORECASE | re.DOTALL)
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")  # keep \n \r \t
_MAX_BODY_BYTES = 2 * 1024 * 1024  # 2 MiB


def sanitize(text: str) -> str:
    """
    Strip XSS script tags and dangerous control characters.

    Preserves:
    - Unicode (Hindi, Hinglish, emoji)
    - Newlines (\\n), carriage returns (\\r), tabs (\\t)

    Removes:
    - <script>...</script> blocks (case-insensitive)
    - Control bytes 0x00-0x08, 0x0B, 0x0C, 0x0E-0x1F
    """
    if not isinstance(text, str):
        return text
    text = _SCRIPT_TAG_RE.sub("", text)
    text = _CONTROL_CHARS_RE.sub("", text)
    return text


class InputSanitizationMiddleware(BaseHTTPMiddleware):
    """Enforce max body size. Actual text sanitization happens per-field."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > _MAX_BODY_BYTES:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=413,
                content={"error": "payload_too_large"},
            )
        return await call_next(request)
```

### 9.5 `src/supply_chain_triage/middleware/rate_limit.py` (stub)

```python
"""
Rate-limiter stub — real enforcement deferred to Sprint 4.

Sprint 0 provides an interface so downstream code can import it
without breaking when Sprint 4 plugs in the real implementation.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    TODO(sprint-4): Implement token-bucket rate limiter backed by
    Firestore or in-memory dict. See docs/decisions/adr-004 for rationale.
    """
    pass  # Intentionally empty — placeholder for Sprint 4
```

---

## 10. Config & Environment

### 10.1 `src/supply_chain_triage/config.py`

```python
"""Pydantic Settings — loads env vars with validation."""
from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from .env or environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Environment ---
    environment: Literal["dev", "staging", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    port: int = 8000

    # --- GCP ---
    gcp_project_id: str
    secret_manager_project: str | None = None

    # --- Gemini ---
    gemini_api_key: str = Field(..., min_length=10)

    # --- Firebase ---
    firebase_project_id: str
    firebase_service_account_path: str = "./firebase-service-account.json"

    # --- Supermemory (Sprint 3+) ---
    supermemory_api_key: str | None = None

    # --- CORS ---
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:8080"]
    )

    # --- Firestore emulator (tests only) ---
    firestore_emulator_host: str | None = None


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor — one Settings instance per process."""
    return Settings()  # type: ignore[call-arg]


# ======================================================================
# Runtime helpers (Sprint 1 dependency backfill — see §10.4)
# ======================================================================


class SecretNotFoundError(Exception):
    """Raised when a secret cannot be fetched from Secret Manager."""


@lru_cache(maxsize=16)
def get_secret(key: str) -> str:
    """Runtime fetch from Secret Manager with an in-process LRU cache.

    Used by tools/agents that need secrets at runtime (e.g., `translate_text`
    fetching `GEMINI_API_KEY`). In `environment == "test"` this reads the
    value from `get_settings()` so unit tests never hit GCP. In prod/dev it
    calls `SecretManagerServiceClient.access_secret_version()` against
    `projects/{gcp_project_id}/secrets/{key}/versions/latest`.

    Raises:
        SecretNotFoundError: if the secret is unavailable (test env missing
        attribute, or Secret Manager access fails).
    """
    from google.cloud import secretmanager

    settings = get_settings()
    if settings.environment == "test":
        value = getattr(settings, key.lower(), "")
        if not value:
            raise SecretNotFoundError(
                f"Secret '{key}' not found on Settings in test mode"
            )
        return value
    try:
        client = secretmanager.SecretManagerServiceClient()
        name = (
            f"projects/{settings.gcp_project_id}"
            f"/secrets/{key}/versions/latest"
        )
        response = client.access_secret_version(request={"name": name})
        return response.payload.data.decode("UTF-8")
    except Exception as exc:  # pragma: no cover - thin wrapper
        raise SecretNotFoundError(
            f"Secret '{key}' unavailable: {exc}"
        ) from exc


# Module-level cache for the async Firestore client. Created lazily so
# importing `config` does not trigger GCP credentials resolution.
_firestore_client = None  # type: ignore[var-annotated]


def get_firestore_client():
    """Return a cached async Firestore client (production or emulator).

    When `FIRESTORE_EMULATOR_HOST` is set (via `.env` or pytest fixture),
    the underlying `AsyncClient` picks it up automatically from the
    environment — no code branch needed. Used by `get_festival_context`
    and `get_monsoon_status` tools in Sprint 1.
    """
    global _firestore_client
    if _firestore_client is None:
        from google.cloud.firestore_v1.async_client import (
            AsyncClient as AsyncFirestoreClient,
        )

        settings = get_settings()
        _firestore_client = AsyncFirestoreClient(project=settings.gcp_project_id)
    return _firestore_client
```

### 10.2 `.env.template`

```bash
# ============================================
# Supply Chain Triage — Environment Template
# ============================================
# Copy to `.env` and fill in values.
# NEVER commit .env to git. See .gitignore.

# --- Environment ---
ENVIRONMENT=dev                # dev | staging | prod
LOG_LEVEL=INFO                 # DEBUG | INFO | WARNING | ERROR
PORT=8000

# --- GCP ---
GCP_PROJECT_ID=your-gcp-project-id
SECRET_MANAGER_PROJECT=your-gcp-project-id

# --- Gemini ---
# Fetched from Secret Manager in prod; local .env for dev
GEMINI_API_KEY=your-gemini-api-key-here

# --- Firebase ---
FIREBASE_PROJECT_ID=your-firebase-project-id
# Path to downloaded service account JSON key
# Get from: Firebase Console > Project Settings > Service Accounts
FIREBASE_SERVICE_ACCOUNT_PATH=./firebase-service-account.json

# --- Supermemory (Sprint 3+) ---
SUPERMEMORY_API_KEY=

# --- CORS ---
# JSON array format for pydantic-settings
CORS_ORIGINS=["http://localhost:3000","http://localhost:8080"]

# --- Firestore Emulator (tests only) ---
# Set to localhost:8080 when running `firebase emulators:start`
FIRESTORE_EMULATOR_HOST=
```

### 10.3 `.gitignore`

```
# Python
__pycache__/
*.py[cod]
*.egg-info/
.venv/
venv/
.python-version-local

# Env / secrets
.env
.env.local
firebase-service-account*.json
*.pem
*.key

# IDE
.idea/
.vscode/
*.swp

# Test / coverage
.pytest_cache/
.coverage
coverage.xml
htmlcov/

# uv
# uv.lock IS committed

# OS
.DS_Store
Thumbs.db

# Build
dist/
build/
```

### 10.4 Runtime helper contracts (Sprint 1 dependency backfill)

Sprint 1 snippets import three helpers that must exist by end of Sprint 0. They live alongside existing Sprint 0 modules (no new files) so Sprint 1 Hour 1 does not have to create scaffolding. The full code lives inline above in §10.1 and §9.3; the table below is the contract:

| # | Helper | Module | Signature | Behavior |
|---|--------|--------|-----------|----------|
| 1 | `get_secret` | `supply_chain_triage.config` | `get_secret(key: str) -> str` | Runtime Secret Manager fetch with in-process `@lru_cache(16)`. In `environment == "test"` reads from `get_settings()`. Raises `SecretNotFoundError` on miss. |
| 2 | `SecretNotFoundError` | `supply_chain_triage.config` | `class SecretNotFoundError(Exception)` | Raised by `get_secret` when the secret is unavailable. |
| 3 | `get_firestore_client` | `supply_chain_triage.config` | `get_firestore_client() -> AsyncFirestoreClient` | Cached factory returning an async Firestore client. Emulator is picked up automatically via `FIRESTORE_EMULATOR_HOST`. |
| 4 | `audit_event` | `supply_chain_triage.middleware.audit_log` | `audit_event(event: str, **kwargs) -> None` | Structured-log helper for emissions outside HTTP middleware context (agent callbacks, tools). Shares the `structlog` sink with `AuditLogMiddleware` so `correlation_id` from contextvars is included when available. |

Each helper ships with a 1-2 line smoke test in Sprint 0's `tests/unit/config/` or `tests/unit/middleware/` so the contract cannot silently regress between sprints.

**Rationale for living here (not Sprint 1):** Sprint 1's classifier, translate tool, festival tool, monsoon tool, and `after_agent_callback` all import these helpers. If they were deferred to Sprint 1 Hour 1, the first hour would be pure scaffolding — no feature progress. Putting them in Sprint 0 means Sprint 1 can open the file, write tests, and build the Classifier.

---

## 11. Tooling Files

### 11.1 `Makefile` (Linux / macOS / partial Windows Git Bash)

> **Windows note:** Most targets work under Git Bash, but `emulator-start`
> backgrounding (`&`) and `emulator-stop` (`pkill -f ...`) are POSIX-only.
> Windows users should either (a) run the emulator in a separate terminal
> manually (`firebase emulators:start --only firestore`) and close it with
> Ctrl-C, or (b) use a small `scripts/emulator.py` wrapper (deferred — not
> in Sprint 0 scope). `make test`, `make coverage`, `make lint`,
> `make type-check`, `make format`, `make security`, `make adk-web`,
> `make pre-commit`, `make clean`, and `make ci` all work on Windows
> Git Bash without modification.

```makefile
.PHONY: help setup install test coverage lint format type-check security \
        emulator-start emulator-stop adk-web clean ci pre-commit

help:
	@echo "Supply Chain Triage — Make targets"
	@echo "  setup           Full idempotent dev setup (uv + hooks + verify)"
	@echo "  install         Install deps via uv sync"
	@echo "  test            Run pytest (unit only)"
	@echo "  coverage        Run tests with coverage report"
	@echo "  lint            Run ruff check"
	@echo "  format          Run ruff format"
	@echo "  type-check      Run mypy"
	@echo "  security        Run bandit + safety + pip-audit"
	@echo "  emulator-start  Start Firestore emulator"
	@echo "  emulator-stop   Stop Firestore emulator"
	@echo "  adk-web         Launch adk web UI"
	@echo "  pre-commit      Run all pre-commit hooks"
	@echo "  clean           Remove caches and build artifacts"
	@echo "  ci              Run all CI checks (lint + type + test + security)"

setup:
	bash scripts/setup.sh

install:
	uv sync --all-extras

test:
	uv run pytest tests/unit -v

coverage:
	uv run pytest tests/unit --cov --cov-report=term-missing --cov-report=html

lint:
	uv run ruff check src tests

format:
	uv run ruff format src tests

type-check:
	uv run mypy src

security:
	uv run bandit -r src -ll
	uv run safety check --json || true
	uv run pip-audit || true

emulator-start:
	firebase emulators:start --only firestore --project demo-supply-chain &

emulator-stop:
	@pkill -f "firebase emulators" || echo "No emulator running"

adk-web:
	uv run adk web --agents_dir src/supply_chain_triage/agents

pre-commit:
	uv run pre-commit run --all-files

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov coverage.xml
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

ci: lint type-check test security
	@echo "All CI checks passed"
```

### 11.2 `.pre-commit-config.yaml`

```yaml
# See https://pre-commit.com for more information
minimum_pre_commit_version: "4.0.0"

repos:
  # --- Built-ins ---
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-json
      - id: check-toml
      - id: check-merge-conflict
      - id: check-added-large-files
        args: ["--maxkb=500"]
      - id: mixed-line-ending
        args: ["--fix=lf"]

  # --- Ruff (lint + format, replaces black/flake8/isort/pyupgrade) ---
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: ["--fix", "--exit-non-zero-on-fix"]
      - id: ruff-format

  # --- mypy ---
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.13.0
    hooks:
      - id: mypy
        files: ^src/
        additional_dependencies:
          - "pydantic>=2.9.0"
          - "pydantic-settings>=2.5.0"
          - "types-requests"

  # --- bandit (security) ---
  - repo: https://github.com/PyCQA/bandit
    rev: "1.7.10"
    hooks:
      - id: bandit
        args: ["-c", "pyproject.toml", "-r", "src"]
        additional_dependencies: ["bandit[toml]"]

  # --- detect-secrets ---
  - repo: https://github.com/Yelp/detect-secrets
    rev: v1.5.0
    hooks:
      - id: detect-secrets
        args: ["--baseline", ".secrets.baseline"]
        exclude: "^(uv\\.lock|.*\\.ipynb)$"
```

### 11.3 `infra/firestore.rules` (Sprint 0 skeleton)

Multi-tenant isolation depends on these rules. Sprint 0 lands a minimal
skeleton that enforces authentication + `company_id` custom claim;
Sprint 2 extends it with `shipments/`, `customers/`, and `exceptions/`
subcollection rules.

```javascript
rules_version = '2';
service cloud.firestore {
  match /databases/{database}/documents {
    // Sprint 0: minimal multi-tenant skeleton.
    // Sprint 2 extends with shipments/customers/exceptions rules.

    function isAuthenticated() {
      return request.auth != null;
    }

    function hasCompanyId() {
      return request.auth.token.company_id != null;
    }

    function belongsToCompany(companyId) {
      return isAuthenticated()
        && hasCompanyId()
        && request.auth.token.company_id == companyId;
    }

    // Default deny — everything not explicitly allowed is rejected.
    match /{document=**} {
      allow read, write: if false;
    }

    // Companies: members can read their own company profile.
    // Writes are server-only (admin SDK bypasses rules).
    match /companies/{companyId} {
      allow read: if belongsToCompany(companyId);
      allow write: if false;
    }

    // Users: self-read/write on own uid document.
    match /users/{userId} {
      allow read, write: if isAuthenticated() && request.auth.uid == userId;
    }

    // Sprint 2 will add: shipments/, customers/, exceptions/
    // with belongsToCompany() checks on each document's company_id field.
  }
}
```

### 11.4 `.secrets.baseline` (committed empty baseline)

Commit a pre-generated empty `.secrets.baseline` so `pre-commit install`
can run on a fresh clone before `setup.sh` has had a chance to generate
one (chicken-and-egg otherwise). The file is regenerated lazily by
`setup.sh` only when missing.

```json
{
  "version": "1.5.0",
  "plugins_used": [
    {"name": "ArtifactoryDetector"},
    {"name": "AWSKeyDetector"},
    {"name": "AzureStorageKeyDetector"},
    {"name": "Base64HighEntropyString", "limit": 4.5},
    {"name": "BasicAuthDetector"},
    {"name": "CloudantDetector"},
    {"name": "DiscordBotTokenDetector"},
    {"name": "GitHubTokenDetector"},
    {"name": "HexHighEntropyString", "limit": 3.0},
    {"name": "IbmCloudIamDetector"},
    {"name": "IbmCosHmacDetector"},
    {"name": "JwtTokenDetector"},
    {"name": "KeywordDetector", "keyword_exclude": ""},
    {"name": "MailchimpDetector"},
    {"name": "NpmDetector"},
    {"name": "PrivateKeyDetector"},
    {"name": "SendGridDetector"},
    {"name": "SlackDetector"},
    {"name": "SoftlayerDetector"},
    {"name": "SquareOAuthDetector"},
    {"name": "StripeDetector"},
    {"name": "TwilioKeyDetector"}
  ],
  "filters_used": [
    {"path": "detect_secrets.filters.allowlist.is_line_allowlisted"},
    {"path": "detect_secrets.filters.common.is_ignored_due_to_verification_policies", "min_level": 2},
    {"path": "detect_secrets.filters.heuristic.is_indirect_reference"},
    {"path": "detect_secrets.filters.heuristic.is_likely_id_string"},
    {"path": "detect_secrets.filters.heuristic.is_lock_file"},
    {"path": "detect_secrets.filters.heuristic.is_not_alphanumeric_string"},
    {"path": "detect_secrets.filters.heuristic.is_potential_uuid"},
    {"path": "detect_secrets.filters.heuristic.is_prefixed_with_dollar_sign"},
    {"path": "detect_secrets.filters.heuristic.is_sequential_string"},
    {"path": "detect_secrets.filters.heuristic.is_swagger_file"},
    {"path": "detect_secrets.filters.heuristic.is_templated_secret"}
  ],
  "results": {},
  "generated_at": "2026-04-10T00:00:00Z"
}
```

---

## 12. CI/CD Workflows

### 12.1 `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

jobs:
  test:
    name: Lint + Type + Test
    runs-on: ubuntu-latest
    timeout-minutes: 15

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          version: "latest"
          enable-cache: true

      - name: Set up Python 3.13
        run: uv python install 3.13

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Run pre-commit
        run: uv run pre-commit run --all-files

      - name: Lint
        run: uv run ruff check src tests

      - name: Type check
        run: uv run mypy src

      - name: Run tests with coverage
        env:
          GEMINI_API_KEY: "fake-ci-key-do-not-use"
          GCP_PROJECT_ID: "ci-project"
          FIREBASE_PROJECT_ID: "ci-project"
          FIREBASE_SERVICE_ACCOUNT_PATH: "./tests/fixtures/fake-sa.json"
        run: uv run pytest tests/unit --cov --cov-report=xml --cov-fail-under=80

      - name: Upload coverage
        uses: actions/upload-artifact@v4
        with:
          name: coverage-report
          path: coverage.xml
```

### 12.2 `.github/workflows/security.yml`

```yaml
name: Security

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
  schedule:
    - cron: "0 3 * * *"   # Nightly 03:00 UTC

jobs:
  scan:
    name: Bandit + Safety + pip-audit + Secrets
    runs-on: ubuntu-latest
    timeout-minutes: 10

    steps:
      - uses: actions/checkout@v4

      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - name: Set up Python 3.13
        run: uv python install 3.13

      - name: Install dependencies
        run: uv sync --all-extras

      - name: Bandit (SAST)
        run: uv run bandit -r src -f sarif -o bandit.sarif || true

      - name: Upload Bandit SARIF
        uses: github/codeql-action/upload-sarif@v3
        if: always()
        with:
          sarif_file: bandit.sarif

      - name: Safety (dependency vulns)
        run: uv run safety check --json || true

      - name: pip-audit
        run: uv run pip-audit || true

      - name: detect-secrets
        run: uv run detect-secrets scan --baseline .secrets.baseline || true

  dependency-review:
    name: Dependency Review
    runs-on: ubuntu-latest
    if: github.event_name == 'pull_request'
    steps:
      - uses: actions/checkout@v4
      - uses: actions/dependency-review-action@v4
```

### 12.3 `.github/workflows/deploy.yml` (STUB)

```yaml
name: Deploy (STUB — deferred to Sprint 5)

on:
  push:
    branches: [main]

jobs:
  deploy:
    name: Deploy placeholder
    runs-on: ubuntu-latest
    steps:
      - name: Placeholder
        run: |
          echo "============================================================"
          echo "Deployment is DEFERRED to Sprint 5 per Resolved Decision #7."
          echo ""
          echo "See Supply-Chain-Deployment-Options-Research.md in the"
          echo "Obsidian vault for the 4 deployment options being"
          echo "evaluated (Cloud Run, Render, Fly.io, Railway)."
          echo ""
          echo "TODO(sprint-5): Replace this stub with the chosen platform."
          echo "============================================================"
          exit 0
```

---

## 13. Documentation Templates

### 13.1 `README.md` (content)

```markdown
# Supply Chain Triage

AI-powered exception triage for small 3PLs in India. Built on Google ADK,
Gemini 2.5 Flash, Firestore, and Firebase Auth.

## Prerequisites

- Python 3.13 (see `.python-version`)
- [`uv`](https://github.com/astral-sh/uv) package manager
- Node.js 20 LTS (for Firebase emulator)
- Java 17 JRE (for Firestore emulator)
- `gcloud` CLI authenticated
- `firebase` CLI (`npm i -g firebase-tools`)
- GCP project with billing enabled
- Firebase project with Google Sign-In OAuth enabled

## Quick Start

```bash
# 1. Clone
git clone https://github.com/<you>/supply-chain-triage.git
cd supply-chain-triage

# 2. Setup (idempotent)
make setup

# 3. Copy env template and fill in secrets
cp .env.template .env
# Edit .env with your GCP / Firebase / Gemini keys

# 4. Run tests
make test

# 5. Launch ADK web UI
make adk-web
# Visit http://localhost:8000
```

## Project Structure

See `docs/architecture/overview.md` for the full architecture. This is a
hexagonal-ish layout with clear boundaries between agents, schemas,
middleware, and runners.

## Running Tests

```bash
make test           # Unit tests
make coverage       # With coverage report
make ci             # Full CI suite locally (lint + type + test + security)
```

## Running the Firestore Emulator

```bash
make emulator-start
# Emulator listens on localhost:8080
make emulator-stop
```

## Environment Variables

See `.env.template` for the full list. Required for local dev:
`GCP_PROJECT_ID`, `GEMINI_API_KEY`, `FIREBASE_PROJECT_ID`,
`FIREBASE_SERVICE_ACCOUNT_PATH`.

## Contributing

See `CONTRIBUTING.md` for dev workflow, TDD policy, and ADR process.

## Security

See `SECURITY.md` for vulnerability reporting and our security policy.

## License

MIT — see `LICENSE`.
```

### 13.2 `CONTRIBUTING.md` (content)

```markdown
# Contributing

## Dev Workflow

1. Create a feature branch from `main`: `git checkout -b sprint-N/<slug>`
2. Write failing test FIRST (strict TDD per ADR-005)
3. Implement minimum code to pass
4. Run `make ci` locally — must be green before PR
5. Open PR; GitHub Actions CI + security workflows must pass
6. Request review (self-review with `superpowers:code-reviewer`)
7. Squash-merge to `main`

## Code Style

- **Formatter + linter**: `ruff` (replaces black, flake8, isort, pyupgrade)
- **Type checker**: `mypy --strict`
- **Line length**: 100
- Run `make format` before committing

## TDD Policy (ADR-005)

Every change MUST follow Red → Green → Refactor:
1. **Red**: Write test, run it, confirm it fails with the expected message
2. **Green**: Write the minimum code to make the test pass
3. **Refactor**: Improve structure without changing behavior

PRs without a failing test commit in the history will be rejected.

## ADR Process

Significant architectural decisions are recorded in `docs/decisions/`
using the Michael Nygard template (see `docs/templates/adr-template.md`).
An ADR is required when:
- Choosing between frameworks, libraries, or patterns
- Changing data models
- Changing security posture
- Adding a new external dependency

## Sprint Workflow (Spiral SDLC)

See `docs/sprints/` and the Obsidian vault
`[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]`. Every sprint produces
9 artifacts: PRD, test-plan, risks, ADRs, security, impl-log,
test-report, review, retro.

## PR Checklist

- [ ] Failing test committed first (visible in git history)
- [ ] `make ci` passes locally
- [ ] Pre-commit hooks pass
- [ ] Coverage ≥ 80% on changed files
- [ ] ADR added/updated if architecture changed
- [ ] `docs/sprints/sprint-N/impl-log.md` updated

## Security Disclosure

See `SECURITY.md`. Report vulnerabilities privately — do not open
public issues.
```

### 13.3 `SECURITY.md` (content)

```markdown
# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 0.1.x   | ✅         |

(Pre-Apr-24 prototype. Production support commitments come post-hackathon.)

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Instead, email the maintainer privately (see repo metadata). We will
acknowledge within 48 hours and provide a resolution timeline within
7 days.

## Security Policies

1. **No secrets in code.** All secrets are stored in GCP Secret Manager
   and fetched at runtime. `.env` files are gitignored.
2. **Least-privilege IAM.** Service accounts get only the exact roles
   they need. No `owner` or `editor` grants.
3. **JWT validation on every protected route** via Firebase Admin SDK.
4. **Explicit CORS allowlist.** No wildcards in production.
5. **Input sanitization at the HTTP boundary** (defense-in-depth).
6. **Audit logging on every state change.**
7. **Dependency scanning on every CI run** (bandit, safety, pip-audit).
8. **Pre-commit `detect-secrets`** catches accidental credential commits.

## Responsible Disclosure

We follow a 90-day disclosure window: from the time a vulnerability is
reported, we commit to a fix or published mitigation within 90 days.
Researchers who report responsibly will be credited in release notes.

## Dependency Scanning Commitment

Every CI run executes:
- `bandit` (Python SAST)
- `safety` (known-CVE check)
- `pip-audit` (PyPA advisory database)
- `detect-secrets` (credential leakage)

High-severity findings block merge to `main`.
```

### 13.4 `docs/templates/adr-template.md` (Michael Nygard format)

```markdown
# ADR-NNN: <Title>

**Status:** Proposed | Accepted | Deprecated | Superseded by ADR-XXX
**Date:** YYYY-MM-DD
**Deciders:** <names>
**Sprint:** <sprint-N>

## Context

What is the issue that we're seeing that is motivating this decision or change?
Describe the forces at play (technical, business, political). Include
relevant constraints and assumptions. Cite any research sources
(web links, internal docs, prior ADRs).

## Decision

What is the change that we're actually proposing or doing?
State it clearly, in one or two sentences if possible.

## Consequences

### Positive
- What becomes easier?
- What new capabilities?

### Negative
- What becomes harder?
- What are we committing to?

### Neutral
- What's unchanged but worth noting?

## Alternatives Considered

### Alternative 1: <name>
- Pros:
- Cons:
- Why rejected:

### Alternative 2: <name>
- Pros:
- Cons:
- Why rejected:

## References

- [Link 1](url)
- [Link 2](url)
- Related ADRs: ADR-XXX, ADR-YYY
```

### 13.5 `docs/security/threat-model.md` (STRIDE outline)

```markdown
# Threat Model — Sprint 0 Foundation

## Scope

The Exception Triage Module backend: FastAPI + ADK + Firebase Auth +
Firestore + Gemini + (Sprint 3) Supermemory.

## Assets

1. **User credentials** (Firebase ID tokens)
2. **Tenant data isolation** (company_id custom claims)
3. **API keys** (Gemini, Supermemory)
4. **Exception audit trail** (PII possible in raw_content)
5. **Customer/shipment data** (commercial sensitivity)

## STRIDE Analysis

### S — Spoofing Identity
- **Threat:** Attacker forges a Firebase ID token.
- **Mitigation:** `firebase_admin.auth.verify_id_token()` verifies
  signature against Google's public keys. Check `aud` and `iss`.
- **Residual risk:** Low.

### T — Tampering with Data
- **Threat:** Attacker modifies exception event in transit.
- **Mitigation:** HTTPS (TLS 1.3) for all traffic. Pydantic strict
  validation rejects unknown fields (`extra="forbid"`).
- **Residual risk:** Low.

### R — Repudiation
- **Threat:** User denies having submitted an exception.
- **Mitigation:** Audit log middleware captures user_id, correlation_id,
  timestamp for every request. Immutable Firestore audit collection.
- **Residual risk:** Low.

### I — Information Disclosure
- **Threat:** One tenant reads another tenant's data.
- **Mitigation:** (1) Firestore security rules filter by
  `request.auth.token.company_id`. (2) Middleware rejects requests
  without `company_id` custom claim. (3) Every query includes
  `company_id` filter.
- **Residual risk:** Medium until Firestore rules unit-tested (Sprint 4).

### D — Denial of Service
- **Threat:** Attacker floods the API.
- **Mitigation:** Sprint 0 stub; real rate limiter Sprint 4. GCP
  platform DDOS protection covers infrastructure layer.
- **Residual risk:** Medium until Sprint 4 rate limiter.

### E — Elevation of Privilege
- **Threat:** User escalates to admin via custom claim manipulation.
- **Mitigation:** Custom claims are server-signed by Firebase Admin SDK.
  Client cannot modify them. Admin SDK grants are version-controlled
  in `scripts/gcp_bootstrap.sh`.
- **Residual risk:** Low.

## Sprint-Specific Threats (Sprint 0)

1. **Secret leakage via `.env` committed to git** — Mitigated by
   `.gitignore` + pre-commit `detect-secrets`.
2. **Dependency supply chain attack** — Mitigated by `uv.lock` +
   `pip-audit` in nightly CI.
3. **ADK sample code contains hardcoded key** — Mitigated by code
   review + bandit scan.

## Next Review

End of Sprint 4 (when security hardening completes).
```

### 13.6 `docs/security/owasp-checklist.md`

```markdown
# OWASP API Security Top 10 (2023) Coverage

| # | Risk | Sprint 0 Coverage | Owner Sprint |
|---|------|-------------------|--------------|
| API1 | Broken Object Level Authorization | Firestore rules skeleton | Sprint 4 hardening |
| API2 | Broken Authentication | firebase-admin verify_id_token | ✅ Sprint 0 |
| API3 | Broken Object Property Level Authorization | Pydantic strict mode | ✅ Sprint 0 |
| API4 | Unrestricted Resource Consumption | Max body size, rate limit stub | Sprint 4 |
| API5 | Broken Function Level Authorization | RBAC via custom claims | Sprint 4 |
| API6 | Unrestricted Access to Sensitive Business Flows | — | Sprint 4 |
| API7 | Server Side Request Forgery | No outbound user-controlled URLs | ✅ Sprint 0 |
| API8 | Security Misconfiguration | CORS allowlist, no wildcards | ✅ Sprint 0 |
| API9 | Improper Inventory Management | OpenAPI auto-generated | Sprint 4 |
| API10 | Unsafe Consumption of APIs | Pydantic for all external responses | Sprint 1+ |

## Sprint 0 Verification Commands

```bash
make security              # bandit + safety + pip-audit
make test                  # includes auth middleware unit tests
pre-commit run detect-secrets --all-files
```
```

### 13.7 ADR entries (7 files — already exist per user note, NOT modified this sprint)

Per user directive: "DO NOT update the 7 ADRs — they are already correct." The 7 ADR files live at `docs/decisions/adr-001-framework-choice.md` through `adr-007-ui-strategy.md`. Sprint 0 creates the directory and template; the 7 actual ADRs are already authored and should be committed as-is.

---

## 14. Scripts

### 14.1 `scripts/setup.sh`

```bash
#!/usr/bin/env bash
# Idempotent Sprint 0 dev setup.
# Safe to run multiple times.
set -euo pipefail

echo "=== Supply Chain Triage — Setup ==="

# 1. Verify Python 3.13
if ! command -v python3.13 &> /dev/null && ! python3 --version | grep -q "3.13"; then
  echo "Python 3.13 not found. Install from python.org or pyenv." >&2
  exit 1
fi
echo "Python 3.13 OK"

# 2. Install uv if missing
if ! command -v uv &> /dev/null; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
echo "uv version: $(uv --version)"

# 3. Sync dependencies (creates .venv)
uv sync --all-extras
echo "Dependencies installed"

# 4. Ensure .secrets.baseline exists BEFORE installing pre-commit hooks.
# We commit an empty baseline to git (see §11.4), but regenerate lazily
# if a user deleted it — either way, pre-commit install must see a file.
if [ ! -f ".secrets.baseline" ]; then
  uv run detect-secrets scan > .secrets.baseline
  echo "Created .secrets.baseline (was missing)"
else
  echo ".secrets.baseline present"
fi

# 5. Install pre-commit hooks
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg
echo "Pre-commit hooks installed"

# 6. Verify gcloud
if ! command -v gcloud &> /dev/null; then
  echo "WARNING: gcloud CLI not found. Install from cloud.google.com/sdk" >&2
else
  echo "gcloud OK: $(gcloud --version | head -1)"
fi

# 7. Verify firebase CLI
if ! command -v firebase &> /dev/null; then
  echo "WARNING: firebase CLI not found. Run: npm i -g firebase-tools" >&2
else
  echo "firebase OK: $(firebase --version)"
fi

# 8. Verify Java (for Firestore emulator)
if ! command -v java &> /dev/null; then
  echo "WARNING: Java not found. Firestore emulator requires JRE 17+." >&2
else
  echo "Java OK"
fi

# 9. Check .env exists
if [ ! -f ".env" ]; then
  echo "WARNING: .env missing. Copy .env.template to .env and fill in values." >&2
fi

# 10. Smoke test: import the package
uv run python -c "import supply_chain_triage; print('Package import OK')"

echo "=== Setup complete ==="
echo "Next: make test"
```

### 14.2 `scripts/gcp_bootstrap.sh`

```bash
#!/usr/bin/env bash
# One-time GCP + Firebase bootstrap.
# Idempotent: safe to re-run after mistakes.
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env first}"
: "${FIREBASE_PROJECT_ID:?Set FIREBASE_PROJECT_ID in .env first}"

echo "=== GCP Bootstrap for $GCP_PROJECT_ID ==="

# 1. Enable required APIs
gcloud services enable \
  secretmanager.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  --project="$GCP_PROJECT_ID"

# 2. Create Firestore database (asia-south1 Mumbai)
gcloud firestore databases create \
  --location=asia-south1 \
  --project="$GCP_PROJECT_ID" \
  || echo "Firestore DB already exists"

# 3. Create secrets (idempotent — will fail silently if exists)
for secret in GEMINI_API_KEY SUPERMEMORY_API_KEY FIREBASE_SERVICE_ACCOUNT; do
  gcloud secrets create "$secret" \
    --replication-policy=automatic \
    --project="$GCP_PROJECT_ID" \
    || echo "Secret $secret already exists"
done

# 4. Create dev service account
DEV_SA="supply-chain-dev@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts create supply-chain-dev \
  --display-name="Supply Chain Dev SA" \
  --project="$GCP_PROJECT_ID" \
  || echo "Dev SA already exists"

# 5. Grant minimum roles
for role in roles/secretmanager.secretAccessor roles/datastore.user; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$DEV_SA" \
    --role="$role" \
    --condition=None
done

echo "=== GCP Bootstrap complete ==="
echo "Next: Add secret versions via 'gcloud secrets versions add ...'"
```

### 14.3 `scripts/seed_firestore.py` (stub) + Seed Data Ownership

**Cross-sprint seed data ownership:**

| Sprint | Owns seed data for | Files populated |
|--------|-------------------|-----------------|
| **Sprint 0** | Empty skeleton files + loader stub | `scripts/seed/festival_calendar.json` (empty `[]`), `scripts/seed/monsoon_regions.json` (empty `[]`), `scripts/seed_firestore.py` stub |
| **Sprint 1** | Classifier reference data | `scripts/seed/festival_calendar.json` (10–15 real Indian festivals), `scripts/seed/monsoon_regions.json` (6–8 real regions) |
| **Sprint 2** | Impact Agent operational data | `scripts/seed/shipments.json` (4 NH-48 + 5 distractors), `scripts/seed/customers.json` (4 customers), `scripts/seed/companies.json`, `scripts/seed/users.json` |

Sprint 0 creates the `scripts/seed/` directory and empty JSON skeleton files, plus the loader stub below. Each subsequent sprint populates the files it owns and extends the loader.

```python
"""
Firestore seed script — evolved across sprints.

Sprint 0: Empty skeleton files + loader shell (this sprint).
Sprint 1: festival_calendar.json + monsoon_regions.json (Classifier tool data).
Sprint 2: shipments.json + customers.json + companies.json + users.json (Impact Agent data).
"""
import json
import os
from pathlib import Path

SEED_DIR = Path(__file__).parent / "seed"
COLLECTIONS = [
    "festival_calendar",   # Populated by Sprint 1
    "monsoon_regions",     # Populated by Sprint 1
    "shipments",           # Populated by Sprint 2
    "customers",           # Populated by Sprint 2
    "companies",           # Populated by Sprint 2
    "users",               # Populated by Sprint 2
]

def main():
    for collection in COLLECTIONS:
        path = SEED_DIR / f"{collection}.json"
        if not path.exists():
            print(f"SKIP: {collection} (file missing)")
            continue
        with open(path) as f:
            data = json.load(f)
        if not data:
            print(f"SKIP: {collection} (empty — populated by later sprint)")
            continue
        # TODO(sprint-1/sprint-2): Write to Firestore emulator
        print(f"Would seed {len(data)} docs into {collection}")

if __name__ == "__main__":
    main()
```

**Sprint 0 creates these empty skeleton files:**
- `scripts/seed/festival_calendar.json` → `[]`
- `scripts/seed/monsoon_regions.json` → `[]`
- `scripts/seed/shipments.json` → `[]`
- `scripts/seed/customers.json` → `[]`
- `scripts/seed/companies.json` → `[]`
- `scripts/seed/users.json` → `[]`

Sprint 1 will populate the first two; Sprint 2 will populate the remaining four and add the real Firestore write logic to this loader.

### 14.4 `scripts/deploy.sh` (stub)

```bash
#!/usr/bin/env bash
# Deployment — DEFERRED to Sprint 5.
# See Supply-Chain-Deployment-Options-Research.md for 4 options being evaluated.
echo "Deployment deferred to Sprint 5."
echo "See Supply-Chain-Deployment-Options-Research.md in the Obsidian vault."
echo "TODO(sprint-5): Implement after deployment target is chosen."
exit 0
```

---

## 15. Day-by-Day Build Sequence

> Total budget: ~20 working hours across 2–3 days. Any task that blows 2× its budget → raise flag (see Rollback Plan).

### Day 1 — Apr 10 (~8 hours): Cloud + Project Skeleton

| Hour | Task | DoD |
|------|------|-----|
| **1** | Run `scripts/gcp_bootstrap.sh` — enable APIs, create Firestore (asia-south1), secrets, dev SA, IAM grants | `gcloud secrets list` shows 3 secrets; `gcloud firestore databases list` shows Mumbai DB |
| **2** | Firebase Console: create project, enable Google Sign-In provider, download service account JSON to local path referenced by `.env` | `firebase projects:list` shows project; `firebase-service-account.json` exists locally |
| **3** | Create GitHub repo, clone, add `.gitignore`, `LICENSE`, empty `README.md`. Create full directory tree per §5. | `tree supply_chain_triage/` matches §5 exactly |
| **4** | Write `pyproject.toml` per §6. Run `uv sync --all-extras`. Verify `uv.lock` committed. | `uv sync` exits 0; `uv run python -c "import fastapi, pydantic, google.adk"` works |
| **5** | Write all 6 Pydantic schema files per §8. Write 2 tests per schema (1 round-trip + 1 invalid). | `uv run pytest tests/unit/schemas -v` shows 12 passing |
| **6** | Write `config.py` + `.env.template` + `.env` (local). Smoke test `get_settings()`. | `uv run python -c "from supply_chain_triage.config import get_settings; print(get_settings().gcp_project_id)"` prints project ID |
| **7** | Write `.pre-commit-config.yaml` + run `pre-commit install` + `pre-commit run --all-files`. | All hooks green on clean repo; committing a bad file (trailing ws, hardcoded secret) triggers failures |
| **8** | Write `.github/workflows/ci.yml` + `security.yml` + `deploy.yml` (stub). Push to GitHub. Watch workflows run. | Both `ci` and `security` workflows green on first real push; `deploy` exits 0 with TODO message |

### Day 2 — Apr 11 (~8 hours): Middleware + ADK + Emulator + Docs

| Hour | Task | DoD |
|------|------|-----|
| **1** | Write `firebase_auth.py` middleware + 5 unit tests (valid, expired, tampered, missing, missing_company_claim) plus a 6th test asserting a generic `ValueError` from `verify_id_token` yields a 401. Mock `firebase_admin.auth.verify_id_token` via `pytest-mock`. | `pytest tests/unit/middleware/test_firebase_auth.py -v` → 6 pass |
| **2** | Write `cors.py`, `audit_log.py`, `input_sanitization.py` middleware + tests per §9. | All middleware unit tests pass; XSS/control-char tests green; Hindi unicode preserved |
| **3** | Write `main.py` bootstrap per §7.1 — `create_app()`, lifespan, middleware layering. Smoke test with `uvicorn`. | `curl http://localhost:8000/health` returns 200 (or 401 if guarded); `/docs` renders OpenAPI |
| **4** | Write `agents/hello_world.py` + `prompts/hello_world.md` per §7.2 and §2.7. Run `make adk-web`. | `adk web` loads at localhost:8000, agent responds to "hello" in browser |
| **5** | Write 1 AgentEvaluator test for hello_world (marked `@pytest.mark.integration`). Verify real Gemini call works. | `pytest tests/unit/agents/test_hello_world.py -v -m integration` passes when `GEMINI_API_KEY` set |
| **6** | Install Java 17 + firebase-tools. Run `firebase init emulators` (firestore only). Write `infra/firestore.rules` + `firebase.json`. | `firebase emulators:start --only firestore` runs without error |
| **7** | Write `tests/integration/firestore/test_emulator_roundtrip.py` + `conftest.py` autouse fixture setting `FIRESTORE_EMULATOR_HOST`. | `pytest tests/integration/firestore -v` passes (emulator must be running) |
| **8** | Write `README.md`, `CONTRIBUTING.md`, `SECURITY.md` per §13.1–§13.3. | All 3 files render correctly on GitHub |

### Day 3 — Apr 12 (~4–6 hours): Docs + Polish + Gate

| Hour | Task | DoD |
|------|------|-----|
| **1** | Write `docs/security/threat-model.md` + `docs/security/owasp-checklist.md` per §13.5 and §13.6. | Files exist, STRIDE categories populated |
| **2** | Write 5 templates in `docs/templates/`: PRD, ADR (Michael Nygard per §13.4), test-plan, retrospective, sprint-layout. | All templates present; ADR template matches §13.4 |
| **3** | Verify all 7 ADR files exist in `docs/decisions/` (user said they're already correct — DO NOT MODIFY). Commit as-is. | `ls docs/decisions/` shows 7 files |
| **4** | Write `scripts/setup.sh` per §14.1 + `scripts/gcp_bootstrap.sh` + deploy/seed stubs. Run `bash scripts/setup.sh` on fresh clone to verify idempotency. | Setup script runs clean twice in a row |
| **5** | Run full gate check: `make ci` locally, push to GitHub, verify all workflows green. Run acceptance criteria checklist in §17. | All 12 acceptance criteria ✅ |
| **6** | Write `docs/sprints/sprint-0/impl-log.md` + `test-report.md`. Tag release `v0.1.0-sprint-0`. | Sprint 0 closed; Sprint 1 unblocked |

---

## 16. Definition of Done per Sub-Scope

### 2.1 GCP + Security Foundation — DoD
- [ ] `gcloud config get-value project` returns the correct project ID
- [ ] `gcloud billing projects describe <id>` shows `billingEnabled: true`
- [ ] `gcloud secrets list` shows `GEMINI_API_KEY`, `SUPERMEMORY_API_KEY`, `FIREBASE_SERVICE_ACCOUNT`
- [ ] `gcloud firestore databases list` shows a database in `asia-south1`
- [ ] Firebase project exists with Google Sign-In OAuth provider enabled
- [ ] Dev SA has `secretmanager.secretAccessor` + `datastore.user` roles

### 2.2 Python Project Skeleton — DoD
- [ ] `.python-version` contains `3.13`
- [ ] `uv sync --all-extras` exits 0, `uv.lock` committed
- [ ] `uv run python -c "import supply_chain_triage"` succeeds
- [ ] Full directory tree from §5 exists (verify via `tree` or `find`)

### 2.3 Test Harness — DoD
- [ ] `make test` runs 30+ tests, all green
- [ ] `make coverage` reports ≥ 80% on `src/supply_chain_triage`
- [ ] `pytest.ini_options.asyncio_mode = "auto"` in pyproject
- [ ] Three fake clients exist: `fake_gemini.py`, `fake_supermemory.py`, `fake_firestore.py`

### 2.4 Security Middleware — DoD
- [ ] Firebase Auth middleware attached to app
- [ ] 6 Firebase Auth tests pass (valid, expired, tampered, missing, missing_company_claim, generic ValueError → 401)
- [ ] CORS rejects wildcards at startup (raises ValueError)
- [ ] `sanitize()` strips script tags but preserves Hindi/Hinglish unicode
- [ ] Audit log middleware emits JSON with correlation_id

### 2.5 Pre-commit + CI — DoD
- [ ] `pre-commit run --all-files` green on clean repo
- [ ] Intentionally bad file (trailing ws + hardcoded password) fails pre-commit
- [ ] GitHub Actions `ci.yml` green on `main`
- [ ] GitHub Actions `security.yml` green on `main`
- [ ] `deploy.yml` exits 0 with TODO message

### 2.6 Pydantic Schemas — DoD
- [ ] All 6 schema files exist under `src/supply_chain_triage/schemas/`
- [ ] `from supply_chain_triage.schemas import *` succeeds
- [ ] 12 schema tests pass (2 per schema)
- [ ] All use Pydantic v2 (`ConfigDict`, `model_validate`, `model_dump`)

### 2.7 ADK Baseline — DoD
- [ ] `hello_world_agent` is an `LlmAgent(model="gemini-2.5-flash")`
- [ ] `make adk-web` launches, agent responds to "hello" in browser
- [ ] One `AgentEvaluator.evaluate()` test passes with real Gemini call

### 2.8 Documentation Infrastructure — DoD
- [ ] `docs/` tree from §5 exists
- [ ] 5 templates present in `docs/templates/`
- [ ] 7 ADRs present in `docs/decisions/` (not modified this sprint)
- [ ] `threat-model.md` + `owasp-checklist.md` present
- [ ] `README.md`, `CONTRIBUTING.md`, `SECURITY.md` present and render on GitHub

---

## 17. Acceptance Criteria (Sprint Gate)

All must be ✅ before Sprint 1 starts.

1. **Tests pass**: `make test` exits 0 with ≥ 30 tests
2. **Coverage ≥ 80%**: `make coverage` shows 80%+ on `src/`
3. **`adk web` works**: Launches on localhost, `hello_world_agent` responds to a typed message
4. **Firestore emulator**: `firebase emulators:start --only firestore` runs; integration test writes + reads via emulator
5. **Pre-commit**: `pre-commit run --all-files` passes on clean repo; fails on a deliberately bad file
6. **CI green**: GitHub Actions `ci.yml` + `security.yml` both pass on `main`; `deploy.yml` exits 0 with TODO
7. **Security scan**: `bandit -r src/` → 0 high-severity; `safety check` → 0 vulns; `pip-audit` → 0 high
8. **Docs exist**: 5 templates + 7 ADRs + threat-model + OWASP checklist + README/CONTRIBUTING/SECURITY
9. **Schemas import**: `python -c "from supply_chain_triage.schemas import ExceptionEvent, ClassificationResult, ImpactResult, ShipmentImpact, TriageResult, UserContext, CompanyProfile"` exits 0
10. **Auth middleware**: Firebase JWT validation unit tests pass using mocked `verify_id_token`
11. **`.env.template`** documents every required env var with a comment
12. **Full directory tree from §5** exists
13. **Sprint 1 backfill helpers importable** (see §10.4): `python -c "from supply_chain_triage.config import get_secret, get_firestore_client, SecretNotFoundError; from supply_chain_triage.middleware.audit_log import audit_event"` exits 0. Each helper has a smoke test in `tests/unit/config/` or `tests/unit/middleware/`.

---

## 18. Rollback Plan (if Sprint 0 blows past 3 days)

If by end of Apr 12 (~24 hours of work) Sprint 0 is not green, cut scope in this order:

### Trim Level 1: Drop nice-to-haves (saves ~4h)
- Delete `deploy.yml` workflow (defer entirely to Sprint 5)
- Delete `docs/templates/*` except `adr-template.md` + `prd-template.md`
- Delete `docs/security/owasp-checklist.md` — keep only `threat-model.md`
- Skip `pip-audit` in CI (keep `bandit` + `safety` only)

### Trim Level 2: Defer non-blocking infrastructure (saves ~4h)
- Drop Firestore emulator — use `mockfirestore` Python library instead
- Drop `AgentEvaluator` integration test — keep only the `adk web` smoke check
- Drop `mypy` from pre-commit (keep in CI only)
- Drop `detect-secrets` baseline (keep pre-commit hook but accept all current state)

### Trim Level 3: Minimum viable Sprint 0 (saves ~4h more)
Must still have:
- All 6 Pydantic schemas + round-trip tests
- Firebase Auth middleware + 1 test
- Pre-commit with ruff only (drop mypy, bandit, detect-secrets from hooks)
- `hello_world_agent` + `adk web` smoke check
- `ci.yml` running pytest
- `.env.template` + `README.md`

Must NOT be cut:
- Pydantic schemas (Sprint 1–3 depend on them)
- Firebase Auth middleware (Sprint 4 depends on it)
- GCP project + secrets (Sprint 1+ depend on Gemini key access)

### Decision Gate
If Trim Level 3 still doesn't fit by end of Apr 13, escalate — Sprint 1 start shifts and `Should-Have` scope in Sprints 4/5 compresses accordingly (already flagged in `Supply-Chain-Sprint-Plan-Spiral-SDLC.md`).

---

## 19. Security Considerations

Sprint 0 sets security precedent for all subsequent sprints. Non-negotiables:

1. **No secrets in code.** Secret Manager runtime fetch in Cloud; `.env` for local dev only. Both gitignored.
2. **Least privilege IAM.** Dev SA gets only `secretmanager.secretAccessor` + `datastore.user`. No `owner` or `editor`.
3. **JWT validation on every protected route.** Middleware applied by default via `BaseHTTPMiddleware`; public paths are an explicit allowlist.
4. **CORS allowlist.** Wildcards banned — `add_cors_middleware` raises ValueError on `*`.
5. **Input sanitization at the boundary.** Max body size + XSS script strip + control char strip.
6. **Audit logging for every request.** Structured JSON via `structlog` with `correlation_id`, `user_id`, `company_id`.
7. **Dependency scanning on every CI run.** `bandit` + `safety` + `pip-audit`. Nightly cron catches new CVEs.
8. **Pre-commit `detect-secrets`** catches accidental credential commits.
9. **Firebase custom claims** required — middleware returns 403 if `company_id` claim missing. This is the multi-tenant isolation anchor.

See `docs/security/threat-model.md` for Sprint 0 STRIDE enumeration and `docs/security/owasp-checklist.md` for API Top 10 coverage.

---

## 20. Dependencies

### External
- GCP account with billing enabled
- Firebase CLI (`npm i -g firebase-tools`)
- `gcloud` CLI authenticated
- Python **3.13** installed locally
- Node 20 LTS for Firebase emulator
- Java 17 JRE for Firestore emulator
- `uv` package manager

### Internal (from vault)
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — parent sprint plan + gate criteria
- [[Supply-Chain-Architecture-Decision-Analysis]] — ADR rationale source
- [[Supply-Chain-Agent-Spec-Coordinator]] — defines schemas
- [[Supply-Chain-Agent-Spec-Classifier]] — defines Classification schema
- [[Supply-Chain-Agent-Spec-Impact]] — defines Impact schemas
- [[Supply-Chain-Firestore-Schema-Tier1]] — defines data model
- [[Supply-Chain-Deployment-Options-Research]] — referenced by deploy.yml stub
- [[Supply-Chain-Research-Sources]] — citations for all ADRs

### Blocking items BEFORE Sprint 0 starts
- [ ] GCP billing confirmed active (15-minute check)
- [ ] Gemini API key provisioned
- [ ] GitHub repo created + cloned
- [ ] Python 3.13 installed locally

---

## 21. Risks (summary)

Full pre-mortem in `risks.md`. Top 3:

| # | Risk | Prob | Severity | Mitigation |
|---|------|------|----------|-----------|
| 2 | IAM permission errors (SA hell) | High | High | Version-control IAM via `scripts/gcp_bootstrap.sh`; verify roles at boot |
| 10 | Scope creep into Sprint 1 (writing Classifier logic) | High | Medium | Strict discipline: ZERO agent logic this sprint; `hello_world` is the only agent |
| 8 | Doc overhead eats the sprint | Medium | Medium | Time-box each ADR to 30 min; templates aggressive; 7 ADRs already authored |

---

## 22. Success Metrics

### Quantitative
- **Time to green CI**: First successful CI run < 4 hours from repo creation
- **Test count**: ≥ 30 tests passing (12 schema + 6 Firebase auth [valid, expired, tampered, missing, missing_company_claim, generic-ValueError→401] + 3 sanitize + 2 audit log [log shape + correlation_id-on-401 regression guard] + 2 CORS + 1 hello_world + 1 firestore emulator + 2 pre-commit meta + 1 Secret Manager fetch)
- **Coverage**: ≥ 80% on schemas, middleware, sanitizers
- **Security findings**: 0 high, 0 medium (bandit + safety + pip-audit)
- **Docs count**: 7 ADRs + 5 templates + 2 security docs + README + CONTRIBUTING + SECURITY = **16 docs minimum**
- **File count**: ~95 files created matching §5 tree

### Qualitative
- A new developer could clone the repo, run `make setup && make test`, and have green tests in under 15 minutes
- Sprint 1 Day 1 engineer spends **zero** time on infrastructure — they start the Classifier test-first immediately

---

## 23. Cross-References

- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — parent sprint plan
- [[Supply-Chain-Agent-Spec-Coordinator]] — Sprint 3 target (schemas drive Sprint 0)
- [[Supply-Chain-Agent-Spec-Classifier]] — Sprint 1 target
- [[Supply-Chain-Agent-Spec-Impact]] — Sprint 2 target
- [[Supply-Chain-Firestore-Schema-Tier1]] — data model Sprint 0 prepares
- [[Supply-Chain-Architecture-Decision-Analysis]] — ADR-001/002/003/004/007 rationale
- [[Supply-Chain-Deployment-Options-Research]] — referenced by `deploy.yml` stub
- [[Supply-Chain-Research-Sources]] — all citations
- `./test-plan.md` — detailed Given/When/Then test cases
- `./risks.md` — full pre-mortem
- `../docs/decisions/adr-001-framework-choice.md` through `adr-007-ui-strategy.md` (authored separately, not modified this sprint)
