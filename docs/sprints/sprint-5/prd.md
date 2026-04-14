---
title: "Sprint 5 PRD — Cloud Run Deployment + React Frontend (First Live Deploy)"
type: deep-dive
domains: [supply-chain, hackathon, sdlc, deployment, frontend]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]", "[[Supply-Chain-Deployment-Options-Research]]", "[[Supply-Chain-Architecture-Decision-Analysis]]", "[[Supply-Chain-Product-Recap]]", "[[Supply-Chain-Demo-Scenario-Tier1]]"]
---

# Sprint 5 PRD — Cloud Run Deployment + React Frontend (Comprehensive Execution Guide)

> **Plan authored with:** `superpowers:writing-plans` skill
> **Sprint window:** Apr 20 – Apr 21, 2026 (2 days, non-negotiable)
> **Deadline context:** Prototype due Apr 24, 2026 (4 days remaining after this sprint closes)
> **Audience:** A new developer must be able to execute Sprint 5 verbatim from this PRD.
> **This sprint is the first time code leaves localhost.**

---

## Table of Contents

1. [Objective](#1-objective)
2. [Scope IN](#2-scope-in-file-by-file)
3. [Out-of-Scope](#3-out-of-scope-deferred)
4. [Acceptance Criteria (Sprint Gate)](#4-acceptance-criteria-sprint-gate)
5. [Test Cases](#5-test-cases-givenwhenthen)
6. [Security Considerations](#6-security-considerations)
7. [Dependencies on Sprint 0-4](#7-dependencies-on-sprint-0-4)
8. [Day-by-Day Build Sequence](#8-day-by-day-build-sequence)
9. [Definition of Done per Scope Item](#9-definition-of-done-per-scope-item)
10. [Risks](#10-risks)
11. [Success Metrics](#11-success-metrics)
12. [Full Code Snippets](#12-full-code-snippets-a-j)
13. [Rollback Plan](#13-rollback-plan)
14. [Cross-References](#14-cross-references)
15. [Research Citations](#15-research-citations)
16. [Open Assumptions](#16-open-assumptions)

---

## 1. Objective

**One-sentence goal:** Ship the first live, publicly-accessible deployment of the Supply Chain Triage system — backend on Google Cloud Run (source-based deploy) and frontend on Firebase Hosting — with streaming SSE end-to-end, Firebase Auth enforced, and an NH-48 demo reproducible on the public URL within 8 seconds.

**Why this sprint exists:**
Sprints 0-4 built and locally tested the full triage pipeline: Classifier, Impact, Coordinator agents, `/triage/stream` SSE endpoint, Firebase Auth middleware, Guardrails, rate-limiting. None of it has ever run outside `localhost`. Sprint 5 **locks in the deployment decision** that was explicitly deferred in Sprint 0 (see [[Supply-Chain-Deployment-Options-Research]]), wires the code to a production environment, and gives the hackathon judges (and demo video) a URL they can actually click.

**What changes from Sprint 4 to Sprint 5:**
- Sprint 4 delivered `/triage/stream` and hardened the API.
- Sprint 5 wraps that API in a Cloud Run service, points a React frontend at it, and deploys both.
- No new business logic. No new agents. Only the glue between "code that works locally" and "code a stranger can use over the internet."

**Deployment decision — LOCKED IN this sprint:** Option B — **Cloud Run + Custom FastAPI + `gcloud run deploy --source .`**. Rationale and swap-out paths captured in ADR-016 (this sprint). See [[Supply-Chain-Deployment-Options-Research]] for the full 4-option matrix. Option B was the "Currently Recommended" pick in that doc; Sprint 5 confirms it after real implementation experience from Sprints 1-4 (middleware stack works, SSE streaming works, `get_fast_api_app()` is idiomatic, no blocker surfaced).

---

## 2. Scope (IN) — File by File

### 2.1 Backend Production Entry Point Updates

- **Modify**: `src/supply_chain_triage/main.py`
  - Read `PORT` from env (Cloud Run injects it, default 8080 for local)
  - Read `FRONTEND_ORIGIN` from env for CORS allowlist (single origin in prod, `*` forbidden)
  - Enable `trace_to_cloud=True` in `get_fast_api_app()` for Cloud Trace spans
  - Add `/api/healthz` endpoint returning `{"status":"ok","revision":REVISION}` for Cloud Run startup + liveness probes
  - Add `/api/readyz` endpoint returning 200 only after Firebase Admin SDK has initialized and the Firestore client can reach the project
  - Use **class-based** Sprint 0 middleware (`FirebaseAuthMiddleware`, `AuditLogMiddleware`, `InputSanitizationMiddleware`) via `app.add_middleware(...)` — not function-style `@app.middleware("http")`
  - Extend Sprint 0's `FirebaseAuthMiddleware.PUBLIC_PATHS` to include `"/api/healthz"` and `"/api/readyz"` so Cloud Run probes bypass auth (document as a Sprint 5 addition to the middleware file)
  - Attach lifespan via `app.router.lifespan_context = lifespan` (ADK's `get_fast_api_app()` does not accept a `lifespan` kwarg)
  - Initialize Firebase Admin via ADC (`firebase_admin.initialize_app()` with no args) — **no service-account JSON anywhere**
  - Drop any `session_service_uri` kwarg — Sprint 5 uses the default `InMemorySessionService`; session persistence is out-of-scope and deferred to Tier 2
  - Do **not** call `uvicorn.run()` at import time — Cloud Run expects the ASGI app exported as `app`

- **Modify**: `src/supply_chain_triage/middleware/firebase_auth.py` (Sprint 0 file)
  - Append `"/api/healthz"` and `"/api/readyz"` to the class attribute `PUBLIC_PATHS` (Sprint 5 addition, one-line change)

- **Modify**: `src/supply_chain_triage/config.py`
  - Add `frontend_origin: str` field (Pydantic Settings)
  - Add `gcp_project: str` (already present in Sprint 0, verify)
  - Add `cloud_run_revision: str | None = None` (Cloud Run sets `K_REVISION`; alias it via env)
  - Add `min_instances: int = 1` for docs/metadata (informational; actual flag lives in deploy script)

### 2.2 Deployment Scripts

- **Create**: `scripts/deploy_backend.sh`
  - Idempotent `gcloud run deploy supply-chain-triage --source .` with all flags: region, min-instances, max-instances, memory, CPU, timeout, concurrency, env vars, secrets from Secret Manager, allow-unauthenticated (auth enforced at middleware layer, not at Cloud Run layer)
  - Pre-flight checks: `gcloud auth list`, `gcloud config get-value project`, verify required Secret Manager secrets exist
  - Post-deploy: print the live URL, run `curl /healthz` smoke test, exit non-zero on any failure
  - Shell-safe: `set -euo pipefail`, trap errors
  - Full code in §12.B

- **Create**: `scripts/deploy_frontend.sh`
  - `pnpm --dir frontend build` → `firebase deploy --only hosting` from `frontend/`
  - Reads `VITE_API_BASE_URL` from shell or `frontend/.env.production`
  - Verifies `frontend/dist/` exists before invoking firebase CLI
  - Post-deploy: print Hosting URL, run `curl` smoke test against Hosting URL + `/api/healthz`
  - Full code in §12.C

- **Create**: `scripts/deploy_all.sh`
  - Orchestrator: calls `deploy_backend.sh` → waits for Cloud Run URL → writes it to `frontend/.env.production` → calls `deploy_frontend.sh`
  - Single command for fresh-clone deploys: `make deploy` wraps this

- **Modify**: `Makefile`
  - Add targets: `deploy`, `deploy-backend`, `deploy-frontend`, `frontend-dev`, `frontend-build`, `frontend-install`

### 2.3 CI/CD Finalization

- **Modify**: `.github/workflows/deploy.yml` (was stub in Sprint 0 per [[Supply-Chain-Deployment-Options-Research]] §CI/CD Decision)
  - Trigger: `push` to `main` affecting `src/**`, `frontend/**`, `scripts/deploy_*.sh`, `pyproject.toml`, `infra/cloudrun.yaml`
  - Google Cloud auth via **Workload Identity Federation** (NOT JSON keys; ADR-016 security addendum)
  - Job 1 `deploy-backend`: checkout → setup Python 3.13 + uv → `gcloud run deploy --source .` → smoke test
  - Job 2 `deploy-frontend`: needs `deploy-backend` → read Cloud Run URL from job output → setup Node 20 → pnpm install/build → firebase deploy → smoke test
  - Job 3 `e2e-smoke`: needs both → run `pytest tests/e2e/test_live_deployment.py` against the live URL
  - Full code in §12.D

### 2.4 Cloud Run Service Config

- **Create**: `infra/cloudrun.yaml`
  - Declarative Knative/Cloud Run YAML (documentation + optional `gcloud run services replace` path)
  - Captures: min/max instances, memory, CPU, timeout, concurrency, container port, env vars, secret refs, startup and liveness probes
  - This file is the source of truth; `deploy_backend.sh` uses `--source .` with equivalent CLI flags — we treat the YAML as spec
  - Full code in §12.H

### 2.5 React Frontend — Vite + TypeScript

User chose **wireframe variant** (recorded in ADR-017): one of `tier1-ui-variation-a-command-center.html`, `…-b-chat-first.html`, `…-c-document-review.html`. Default assumption if user has not yet chosen: **Variant A (Command Center)** because it most closely matches the "dispatcher console" demo narrative in [[Supply-Chain-Demo-Scenario-Tier1]]. Swap path: only `TriagePage.tsx` layout and CSS tokens change; components and hooks are wireframe-agnostic.

- **Create**: `frontend/package.json`
  - Deps: `react@^19`, `react-dom@^19`, `firebase@^11`, `react-router-dom@^7`
  - Dev deps: `vite@^6`, `@vitejs/plugin-react@^5`, `typescript@^5.6`, `@types/react`, `@types/react-dom`, `@types/node`, `eslint`, `@typescript-eslint/*`, `vitest@^2`, `@testing-library/react@^16`, `@testing-library/jest-dom`, `jsdom`
  - Scripts: `dev`, `build`, `preview`, `test`, `lint`, `typecheck`
  - Full code in §12 appendix

- **Create**: `frontend/tsconfig.json` — strict TypeScript, `moduleResolution: "bundler"`, `jsx: "react-jsx"`, `target: "ES2022"`

- **Create**: `frontend/vite.config.ts`
  - `@vitejs/plugin-react`
  - `server.proxy`: `/api` → `http://localhost:8080` for local dev (so dev runs against a locally-running backend)
  - `build.outDir: "dist"`, `build.sourcemap: true`
  - Full code in §12 appendix

- **Create**: `frontend/index.html` — Vite root HTML with `<div id="root" />`, imports `/src/main.tsx`, includes CSP meta tag

- **Create**: `frontend/src/main.tsx` — React 19 `createRoot` bootstrap, mounts `<App />`, imports `./index.css`

- **Create**: `frontend/src/App.tsx`
  - Router with two routes: `/` → `<LoginPage />` if unauthed, `<TriagePage />` if authed
  - Wraps everything in `<AuthProvider>` context (from `lib/firebase.ts`)

- **Create**: `frontend/src/pages/LoginPage.tsx`
  - Single "Sign in with Google" button calling `signInWithPopup(auth, googleProvider)`
  - Error banner for `auth/popup-closed-by-user` etc.
  - Redirects to `/` on success (App re-renders via auth state)

- **Create**: `frontend/src/pages/TriagePage.tsx`
  - Composes: `<SummaryBanner />`, `<ExceptionInput onSubmit>`, `<AgentStream events />`, `<ClassificationCard result />`, `<ImpactCard result />`
  - Holds triage state (`events`, `classification`, `impact`, `final`, `loading`, `error`)
  - Calls `useTriageSSE()` hook to stream events
  - Full code in §12.G

- **Create**: `frontend/src/components/ExceptionInput.tsx`
  - Controlled form: event type, narrative, reference ID, submit button
  - Validates non-empty narrative before calling `onSubmit`
  - Loading state disables the button during streaming

- **Create**: `frontend/src/components/AgentStream.tsx`
  - Vertical timeline of SSE events as they arrive
  - Each event row: timestamp, agent name, event type, collapsible payload
  - Auto-scrolls to newest; sticky "Clear" button

- **Create**: `frontend/src/components/ClassificationCard.tsx`
  - Renders `ClassificationResult` (exception_type, severity, confidence, reasoning)
  - Color-coded severity chip (green/amber/red)

- **Create**: `frontend/src/components/ImpactCard.tsx`
  - Renders `ImpactResult` with shipment list, monetary impact, affected customers

- **Create**: `frontend/src/components/SummaryBanner.tsx`
  - Top bar showing: user email/avatar from Firebase, sign-out button, environment badge (dev/prod), revision hash from `/healthz`

- **Create**: `frontend/src/hooks/useTriageSSE.ts`
  - EventSource-style wrapper using `fetch` + `ReadableStream` (because native `EventSource` cannot attach auth headers — see research §15)
  - State machine: `idle | connecting | streaming | done | error | reconnecting`
  - Exponential-backoff reconnect (max 5 attempts, 1s → 30s)
  - Parses SSE frames, invokes callback per event
  - Full code in §12.E

- **Create**: `frontend/src/lib/firebase.ts`
  - Initializes Firebase app, exports `auth`, `googleProvider`, `AuthProvider` React context, `useAuth()` hook
  - Reads config from `import.meta.env.VITE_FIREBASE_*`
  - `onAuthStateChanged` listener wired into provider state

- **Create**: `frontend/src/lib/api.ts`
  - `apiBaseUrl` from `import.meta.env.VITE_API_BASE_URL` (falls back to `/api` for dev proxy + prod same-origin via Firebase Hosting rewrite)
  - `fetchWithAuth()` wrapper that calls `await user.getIdToken()` and sets `Authorization: Bearer <token>`
  - `streamTriage(event, onEvent, signal)`: async function using `fetch` + `ReadableStream.getReader()` + `TextDecoder` to parse SSE frames; supports `AbortController` cancellation
  - Full code in §12.F

- **Create**: `frontend/src/types/triage.ts`
  - TypeScript mirrors of Pydantic schemas: `ExceptionEvent`, `ClassificationResult`, `ImpactResult`, `TriageResult`, `StreamEvent` union type
  - Hand-written for Sprint 5; codegen from OpenAPI deferred post-hackathon

- **Create**: `frontend/src/index.css` — global reset + CSS custom properties from the chosen wireframe

- **Create**: `frontend/.env.template` — `VITE_API_BASE_URL=`, `VITE_FIREBASE_API_KEY=`, `VITE_FIREBASE_AUTH_DOMAIN=`, `VITE_FIREBASE_PROJECT_ID=`, `VITE_FIREBASE_APP_ID=`

- **Create**: `frontend/.gitignore` — `node_modules`, `dist`, `.env*`, `.firebase/`

- **Create**: `frontend/.eslintrc.cjs` — React + TypeScript + hooks rules

### 2.6 Firebase Hosting Config

- **Create**: `frontend/firebase.json`
  - `hosting.public = "dist"`
  - `hosting.rewrites`: `/api/**` → `run: { serviceId: "supply-chain-triage", region: "asia-south1", pinTag: true }` (reverse proxies to Cloud Run so frontend is same-origin; eliminates a whole class of CORS bugs)
  - SPA fallback: `**` → `/index.html`
  - `headers`: immutable `Cache-Control` for `dist/assets/**`, `no-cache` for `index.html`, HSTS + nosniff + Referrer-Policy
  - Full code in §12.J

- **Create**: `frontend/.firebaserc` — `{ "projects": { "default": "nimblefreight-hack" } }`

### 2.7 E2E Smoke Test

- **Create**: `tests/e2e/test_live_deployment.py`
  - Reads `LIVE_BACKEND_URL` and `LIVE_FRONTEND_URL` from env
  - `test_backend_healthz_returns_200` (TC-E1)
  - `test_frontend_hosting_serves_index_html` (TC-E2)
  - `test_frontend_api_proxy_reaches_cloud_run` (TC-E2)
  - `test_triage_stream_end_to_end_nh48` (TC-E3) — authenticated request with test Firebase token, streams the full NH-48 scenario, asserts classification + impact + final event arrive within 10 seconds (8s target + 2s slack)
  - `test_cors_blocks_evil_origin`
  - Full code in §12.I

### 2.8 Architecture Decision Records

- **Create**: `docs/decisions/adr-016-deployment-target-finalized.md`
  - **LOCKS IN** the deployment decision deferred in Sprint 0
  - Context: Sprints 0-4 complete, custom FastAPI + middleware stack working, SSE streaming working
  - Decision: Option B — Cloud Run + custom FastAPI + `gcloud run deploy --source .`
  - Alternatives considered: A (`adk deploy cloud_run`), C (Vertex AI Agent Engine), D (Agent Starter Pack)
  - Rejection reasoning for each: A (too little control for our middleware), C (no custom UI), D (Terraform learning curve during crunch)
  - Swap-out paths: how to migrate to C or D post-hackathon
  - Consequences: min_instances cost (~$5/mo), cold-start handling, source-build latency trade-off

- **Create**: `docs/decisions/adr-017-frontend-framework-wireframe.md`
  - Context: three HTML wireframes exist ([[Supply-Chain-Product-Recap]] §Wireframes); must pick one
  - Decision: React 19 + Vite + TypeScript; wireframe **variant [A/B/C]** (user confirms)
  - Alternatives: `adk web` only (rejected: judges need custom UI), Next.js (rejected: overkill for SPA), Svelte (rejected: React ecosystem familiarity)
  - Consequences: new frontend subtree in repo, Firebase Hosting becomes second deploy target, Vite dev-server proxy for local dev

### 2.9 Documentation

- **Modify**: `docs/architecture/overview.md` — add a "Deployment Topology" diagram section showing: browser → Firebase Hosting (CDN, static) → `/api/**` rewrite → Cloud Run → Gemini + Firestore + Secret Manager
- **Create**: `docs/sprints/sprint-5/impl-log.md` — dev diary, filled during sprint
- **Create**: `docs/sprints/sprint-5/test-report.md` — pytest + vitest results, filled at sprint end
- **Create**: `docs/sprints/sprint-5/review.md` — code-reviewer + user notes, filled at sprint end
- **Create**: `docs/sprints/sprint-5/retro.md` — start/stop/continue, filled at sprint end
- **Modify**: `README.md` — add "Live Demo" section with Cloud Run + Firebase Hosting URLs once deployed; add `make deploy` quickstart

---

## 3. Out-of-Scope (Deferred)

| Item | Deferred to | Reason |
|------|-------------|--------|
| CI/CD beyond push-to-main auto-deploy | Post-hackathon | Workflow is deployed but we don't add canary, blue/green, preview environments |
| Advanced observability (dashboards, alerting) | Post-hackathon | Cloud Trace enabled via `trace_to_cloud=True`; log explorer is sufficient for demo |
| Custom domain + SSL cert | Post-hackathon | `nimblefreight-hack.web.app` is fine for the demo |
| Load testing / autoscaling tuning | Post-hackathon | `max_instances=10` + concurrency `80` handles demo load |
| Frontend unit test coverage threshold | Post-hackathon | Smoke tests + manual QA only; Vitest config added but no gate |
| Frontend i18n / accessibility audit | Post-hackathon | EN-only, basic a11y only |
| Progressive Web App / offline mode | Never for Tier 1 | Online-only demo |
| Dockerfile | Post-hackathon | `gcloud run deploy --source .` lets Cloud Build auto-detect Python; no manual Dockerfile until production hardening. (Per user directive recorded in Sprint 0 PRD §4 Resolved Decision 9) |
| Terraform / Infrastructure-as-Code | Post-hackathon | Option D (Agent Starter Pack) is the migration target; see ADR-016 |
| Migration to Vertex AI Agent Engine | Post-hackathon | See swap-out path in ADR-016 |
| `adk deploy cloud_run` path | Never (rejected) | See ADR-016 rejection rationale |
| Session persistence across Cloud Run instances | Tier 2 | Sprint 5 uses the default `InMemorySessionService`. `min_instances=1` keeps a single warm process so session state survives for the demo. Tier 2 will add `DatabaseSessionService` with Cloud SQL or a custom `FirestoreSessionService`. |

---

## 4. Acceptance Criteria (Sprint Gate)

You cannot close Sprint 5 until **all 15** of these are green. (AC #6 — cold-start from zero — was demoted to Success Metric in §11 because verifying it requires temporarily breaking AC #4, which undermines demo readiness.)

1. ✅ `gcloud run deploy --source .` succeeds from a fresh clone, producing a live HTTPS URL
2. ✅ `curl https://<cloud-run-url>/api/healthz` returns `200` with `{"status":"ok","revision":"<K_REVISION>"}`
3. ✅ `curl https://<cloud-run-url>/api/readyz` returns `200` (proves Firebase Admin + Firestore reachable)
4. ✅ Cloud Run service has `min_instances=1` set, verified via `gcloud run services describe`
5. ✅ First request after 10-minute idle period returns in `< 3s` (warm instance)
6. ✅ Full NH-48 end-to-end `/api/triage/stream` runs on the live URL and returns classification + impact + final event within **8 seconds** (measured on a Mumbai network)
7. ✅ `firebase deploy --only hosting` produces a live Hosting URL (e.g., `https://nimblefreight-hack.web.app`)
8. ✅ Hosting URL serves React bundle; `/api/**` rewrite reaches Cloud Run (verified by hitting `{hosting}/api/healthz`)
9. ✅ A browser navigation to the Hosting URL loads the login page; "Sign in with Google" succeeds; `TriagePage` renders
10. ✅ Submitting the NH-48 scenario from the UI streams SSE events live; `AgentStream` component renders at least 4 events (classifier_start, classifier_done, impact_done, final)
11. ✅ `useTriageSSE` hook handles a mid-stream disconnect gracefully: exponential-backoff reconnect attempted, error surfaces to user after 5 failed retries
12. ✅ Unauthenticated request to `/api/triage/stream` returns `401 Unauthorized` (Firebase Auth middleware from Sprint 0/4 still enforced)
13. ✅ CORS: only the Firebase Hosting origin is allowed; a request from `http://evil.example.com` is not granted an `Access-Control-Allow-Origin` match
14. ✅ Secret Manager: `GEMINI_API_KEY`, `SUPERMEMORY_API_KEY` are not in env vars, not in logs, not in repo — only referenced via `--set-secrets` flag. `FIREBASE_SERVICE_ACCOUNT` is NOT a secret at all in Sprint 5 — Firebase Admin uses ADC via the Cloud Run runtime service account
15. ✅ A fresh-clone engineer running `make deploy` with only a `.env` file and `gcloud auth login` produces a working live URL in `< 15 minutes`

---

## 5. Test Cases (Given/When/Then)

### Backend (pytest)

**TC-B1 — healthz returns 200**
- Given: the backend is running (locally or on Cloud Run)
- When: `GET /api/healthz`
- Then: status `200`, body contains `status: "ok"` and a `revision` string

**TC-B2 — readyz validates Firebase Admin + Firestore reachability**
- Given: Firebase Admin SDK is initialized with valid credentials and Firestore is reachable
- When: `GET /api/readyz`
- Then: status `200`
- And: when Firebase Admin is not initialized OR Firestore probe fails, `GET /api/readyz` returns `503`

**TC-B3 — CORS blocks non-allowlisted origin**
- Given: `FRONTEND_ORIGIN=https://nimblefreight-hack.web.app`
- When: a request with `Origin: https://evil.example.com` hits `/api/triage/stream`
- Then: response has no `Access-Control-Allow-Origin: https://evil.example.com` header (browser will block)

**TC-B4 — unauth request to /triage/stream is 401**
- Given: no `Authorization` header
- When: `POST /api/triage/stream` with a valid NH-48 body
- Then: status `401`

**TC-B5 — SSE stream produces ordered events**
- Given: authenticated request with NH-48 body
- When: `POST /api/triage/stream`
- Then: response `Content-Type: text/event-stream`
- And: events arrive in order `classifier_start`, `classifier_done`, `impact_start`, `impact_done`, `final`
- And: all events arrive within 8 seconds

### Frontend (vitest + testing-library)

**TC-F1 — LoginPage renders sign-in button when unauthed**
- Given: `useAuth()` returns `{ user: null, loading: false }`
- When: `<App />` mounts
- Then: a button with text "Sign in with Google" is in the DOM

**TC-F2 — TriagePage renders when authed**
- Given: `useAuth()` returns `{ user: mockUser, loading: false }`
- When: `<App />` mounts
- Then: `ExceptionInput`, `AgentStream`, `SummaryBanner` are rendered

**TC-F3 — useTriageSSE parses SSE frames**
- Given: a mock fetch returning a `ReadableStream` of two SSE frames
- When: the hook is invoked with an exception event
- Then: the `onEvent` callback fires twice with the parsed payloads

**TC-F4 — useTriageSSE reconnects on drop**
- Given: a mock fetch that errors on first call, succeeds on second
- When: the hook is invoked
- Then: after the error, a second fetch is made after ~1s
- And: state transitions `connecting → error → reconnecting → connecting → streaming → done` (matches test-plan.md TC-F4)

**TC-F5 — ExceptionInput validates non-empty narrative**
- Given: empty narrative field
- When: submit is clicked
- Then: `onSubmit` is NOT called
- And: an error message appears

### E2E (pytest, hits real live URLs)

**TC-E1 — live backend healthz**
- Given: `LIVE_BACKEND_URL` env var set
- When: `GET {LIVE_BACKEND_URL}/healthz`
- Then: status `200`

**TC-E2 — live hosting proxies API**
- Given: `LIVE_FRONTEND_URL` env var set
- When: `GET {LIVE_FRONTEND_URL}/api/healthz`
- Then: status `200` (proves Firebase Hosting rewrite works)

**TC-E3 — live NH-48 end-to-end**
- Given: Firebase test token minted via Firebase Admin SDK
- When: `POST {LIVE_BACKEND_URL}/api/triage/stream` with NH-48 body + `Authorization: Bearer <token>`
- Then: full stream completes in `< 10s`
- And: final event contains a non-empty `TriageResult`

---

## 6. Security Considerations

Sprint 5 is the **highest-risk sprint for security** because it exposes the API to the public internet for the first time. Every control Sprint 0-4 built must hold up.

### 6.1 Secrets Management
- **No secrets in env vars**, no secrets in logs, no secrets in repo
- Only two secrets are referenced via `--set-secrets`: `GEMINI_API_KEY=gemini-api-key:latest,SUPERMEMORY_API_KEY=supermemory-api-key:latest`
- **Firebase Admin uses the Cloud Run runtime service account via ADC.** There is NO `firebase-sa` secret and no service-account JSON in Secret Manager. `firebase_admin.initialize_app()` picks up the runtime SA's credentials automatically on Cloud Run. The runtime SA is granted `roles/firebase.sdkAdminServiceAgent` (see `deploy_backend.sh` IAM section) so it can act as Firebase Admin.
- Cloud Run runtime service account requires `roles/secretmanager.secretAccessor` on the two remaining secrets (`gemini-api-key`, `supermemory-api-key`), plus `roles/firebase.sdkAdminServiceAgent` and `roles/datastore.user` for Firestore reachability
- **Verification step in `test_live_deployment.py`**: `gcloud run services describe --format json` shows `template.spec.containers[0].env[].valueFrom.secretKeyRef` for each of the two secrets, NOT `value`

### 6.2 CORS Lockdown
- `allow_origins` in `get_fast_api_app()` = `[os.environ["FRONTEND_ORIGIN"]]` — single origin only
- **Forbidden**: `allow_origins=["*"]`, `allow_origin_regex=".*"`, `allow_credentials=True` with wildcard
- Enforced in `main.py` via `assert FRONTEND_ORIGIN.startswith("https://")` at startup in non-dev env
- **CORS lockdown is defense-in-depth only.** The primary frontend-to-backend path is same-origin via the Firebase Hosting `/api/**` rewrite (§2.6, §12.J), which never triggers CORS preflights. The allowlist exists to block any direct browser access to the raw `*.run.app` URL from a malicious page.

### 6.3 HTTPS-Only
- Cloud Run provides HTTPS by default; `allow-unauthenticated` means any internet client can reach the service, but our Firebase Auth middleware enforces token check
- Firebase Hosting is HTTPS by default
- No HTTP listener anywhere in the stack

### 6.4 Content Security Policy
- `frontend/index.html` has CSP meta tag:
  - `default-src 'self'`
  - `script-src 'self'`
  - `connect-src 'self' https://*.googleapis.com https://*.firebaseio.com https://<cloud-run-domain>`
  - `img-src 'self' data: https://*.googleusercontent.com` (for Google profile photos)
  - `style-src 'self' 'unsafe-inline'` (Vite inlines some styles; tighten post-hackathon)
- Backend also sets `Strict-Transport-Security: max-age=31536000; includeSubDomains` via middleware from Sprint 0

### 6.5 Authentication
- Firebase Auth middleware (Sprint 0 + Sprint 4) validates `Authorization: Bearer <idToken>` on every `/api/**` route
- `/healthz` and `/readyz` are the only unauthenticated endpoints; they return no user data
- Frontend attaches `Authorization` header via `fetchWithAuth()` which calls `await user.getIdToken()` on every request (Firebase SDK auto-refreshes expired tokens)
- Sign-out clears state and redirects to login

### 6.6 Rate Limiting (from Sprint 4)
- Already enforced in middleware; Sprint 5 verifies it still works over the public URL
- Per-user rate limit: 60 requests / minute (stored in Firestore `rate_limits/{uid}` per Sprint 4 PRD)

### 6.7 Audit Logging
- Structured JSON logs via `structlog` (Sprint 0) → Cloud Logging automatically
- Every `/api/triage/stream` request logs: `trace_id`, `user_uid`, `exception_type`, `duration_ms`, `status`
- No PII in logs beyond `user_uid` (Firebase UID, not email)

### 6.8 OWASP API Top 10 Re-check for Sprint 5 (delta from Sprint 4)
| Risk | Control | Status |
|------|---------|--------|
| API1 Broken Object-Level Auth | Firestore security rules enforce `uid == request.auth.uid` | ✅ Sprint 0 |
| API2 Broken Authentication | Firebase Auth middleware | ✅ Sprint 0 + re-verified |
| API3 Broken Object Property-Level Auth | Pydantic schemas whitelist fields | ✅ Sprint 0 |
| API4 Unrestricted Resource Consumption | Rate limit middleware + Cloud Run `max_instances=10` | ✅ Sprint 4 + Sprint 5 cap |
| API5 Broken Function-Level Auth | All `/api/**` routes require auth | ✅ Sprint 4 |
| API6 Server-Side Request Forgery | No user-controlled URLs in tools | ✅ N/A |
| API7 Security Misconfiguration | CORS allowlist, CSP, HSTS, Secret Manager | ✅ Sprint 5 |
| API8 Lack of Protections | bandit, safety, pip-audit in CI | ✅ Sprint 0 |
| API9 Improper Inventory Management | README + OpenAPI published | ✅ Sprint 4 |
| API10 Unsafe Consumption of APIs | Gemini responses parsed through Pydantic | ✅ Sprint 1-3 |

### 6.9 Threat Model Addendum for Sprint 5
Add to `docs/security/threat-model.md`:
- **Threat**: Attacker discovers Cloud Run URL via DNS / shodan and bypasses Firebase Hosting
  **Mitigation**: Auth enforced at app layer, not network layer; Cloud Run URL is not a security boundary
- **Threat**: Stale Firebase ID token accepted after user sign-out
  **Mitigation**: `verify_id_token(token, check_revoked=True)` (Sprint 0 already sets this; verify enabled in prod config)
- **Threat**: Client-side React bundle leaks API keys
  **Mitigation**: Only `VITE_FIREBASE_*` keys ship in the bundle (these are public by design per Firebase docs); no Gemini or Supermemory keys ever ship to browser

---

## 7. Dependencies on Sprint 0-4

Sprint 5 is the "last mile" — it depends on everything before it and adds no new agent logic.

### From Sprint 0
- `src/supply_chain_triage/main.py` FastAPI bootstrap exists
- `src/supply_chain_triage/config.py` Pydantic Settings pattern exists
- `middleware/firebase_auth.py` enforces JWT validation
- `middleware/cors.py` exists (Sprint 5 tightens the allowlist)
- `middleware/audit_log.py` emits structured logs
- Pydantic schemas exist for `ExceptionEvent`, `ClassificationResult`, `ImpactResult`, `TriageResult` (frontend `types/triage.ts` mirrors these)
- Firebase project exists with Google Sign-In OAuth provider enabled
- Firestore instance exists in `asia-south1`
- Secret Manager has `GEMINI_API_KEY`, `SUPERMEMORY_API_KEY`, `FIREBASE_SERVICE_ACCOUNT`
- GitHub Actions workflows `ci.yml`, `security.yml`, `deploy.yml` (stub) exist
- `scripts/deploy.sh` stub exists (renamed / split into `deploy_backend.sh` + `deploy_frontend.sh` this sprint)
- ADRs 001-007 exist (Sprint 4 adds 014-015; Sprint 5 adds 016-017)

### From Sprint 1
- `agents/classifier.py` is production-ready
- `prompts/classifier.md` is locked in
- Guardrails validators wrap classifier output

### From Sprint 2
- `agents/impact.py` is production-ready
- Firestore collections (`shipments`, `customers`) are seeded with NH-48 data
- Firestore security rules deny cross-tenant reads

### From Sprint 3
- `agents/coordinator.py` orchestrates the pipeline
- Supermemory adapter works (or DIY Firestore fallback per Should-Have)
- Full NH-48 scenario runs via `adk web` locally

### From Sprint 4
- `/api/triage/stream` SSE endpoint exists in `api/triage_endpoint.py`
- Hybrid SSE + Gemini text streaming works
- Rate limiting enforced
- Audit logging + trace IDs on every request
- E2E test `tests/e2e/test_triage_stream.py` passes locally (Sprint 5 adds `test_live_deployment.py` as a superset)

### External
- GCP project `nimblefreight-hack` (or user's actual project ID) with billing enabled
- Firebase project linked to the same GCP project
- `gcloud` CLI authenticated
- `firebase` CLI authenticated (`firebase login`)
- Node.js 20+ and `pnpm` (or `npm`) installed

**Sprint 5 cannot start until `adk web` + `/api/triage/stream` both complete NH-48 locally.** This is the hard gate.

---

## 8. Day-by-Day Build Sequence

> **Two-deploy workflow note:** The backend is deployed **twice** across the sprint — once on Day 1 with a placeholder/bootstrap `FRONTEND_ORIGIN` (`https://<project>.web.app`, the eventual Hosting default), and again on Day 2 afternoon after the frontend is actually live and we've confirmed the real Hosting URL. If the Hosting URL differs from the default (e.g., a custom site name), the Day 2 re-deploy updates `FRONTEND_ORIGIN` to the real value. This is intentional — we cannot set CORS to the real origin before the frontend exists, and we cannot build the frontend until the backend URL is known. The two-deploy sequence is cheap (source builds cache) and avoids a chicken-and-egg bootstrap problem.

### Day 1 (Apr 20) — Backend to Cloud Run

**Morning (3-4 hours)**

1. **Write Acceptance-Criteria tests first (TDD)** — 45 min
   - `tests/unit/test_healthz.py` — TC-B1, TC-B2
   - `tests/unit/test_cors_lockdown.py` — TC-B3
   - Run: `make test` → watch them FAIL (healthz/readyz don't exist yet)

2. **Implement `main.py` production updates** — 45 min
   - Add `/healthz` and `/readyz` handlers
   - Wire `FRONTEND_ORIGIN`, `SESSION_SERVICE_URI`, `PORT` from env
   - Enable `trace_to_cloud=True`
   - Run: `make test` → watch TC-B1, TC-B2, TC-B3 PASS

3. **Local dry run (no Docker)** — 30 min
   - `PORT=8080 FRONTEND_ORIGIN=http://localhost:5173 uv run uvicorn supply_chain_triage.main:app`
   - `curl localhost:8080/api/healthz` → 200
   - `curl localhost:8080/api/readyz` → 200 (after Firebase Admin init + Firestore probe)

4. **GCP pre-flight** — 30 min
   - `gcloud auth login`, `gcloud config set project nimblefreight-hack`
   - Enable required APIs: `run.googleapis.com`, `cloudbuild.googleapis.com`, `secretmanager.googleapis.com`, `firebase.googleapis.com`
   - Verify Secret Manager secrets exist: `gcloud secrets list | grep -E 'gemini-api-key|supermemory-api-key|firebase-sa'`
   - Create / verify Cloud Run runtime service account with `secretmanager.secretAccessor`

5. **Write `scripts/deploy_backend.sh`** — 30 min (code in §12.B)
   - `chmod +x scripts/deploy_backend.sh`
   - Dry-run: `bash -n scripts/deploy_backend.sh` (syntax check)

6. **Write `infra/cloudrun.yaml`** — 15 min (code in §12.H)
   - Documentation, not used by deploy script this sprint

**Afternoon (3-4 hours)**

7. **First deploy attempt** — 45 min
   - `./scripts/deploy_backend.sh`
   - Watch Cloud Build logs; expect first deploy 3-5 min (source upload + container build)
   - On success: capture the live URL, store in `BACKEND_URL` env var

8. **Smoke test live backend** — 30 min
   - `curl $BACKEND_URL/api/healthz` → expect 200
   - `curl $BACKEND_URL/api/readyz` → expect 200
   - Authenticated `curl` with a minted Firebase test token against `/api/triage/stream` + NH-48 body
   - Measure latency: `time curl ...` → target `< 8s` total

9. **Debug any startup issues** — 60 min (buffer)
   - Likely issues: ADK import overhead 8-20s cold start (see research §15), missing env var, secret binding failure, Firebase Admin init failure
   - Fix: increase Cloud Run timeout + startup probe, fix missing var, re-deploy

10. **Finalize `.github/workflows/deploy.yml`** — 45 min (code in §12.D)
    - Test by pushing to a branch first, then merging to main
    - Verify Workload Identity Federation works (or fall back to JSON key in GitHub secret with explicit TODO)

11. **Write `tests/e2e/test_live_deployment.py`** — 30 min (code in §12.I)
    - Run: `LIVE_BACKEND_URL=$BACKEND_URL uv run pytest tests/e2e/test_live_deployment.py -v`
    - Expect TC-E1, TC-E3 PASS (TC-E2 still failing — frontend not deployed yet)

12. **Commit + tag** — 15 min
    - `git commit -m "feat(sprint-5): cloud run backend deploy"`
    - Tag: `git tag sprint-5-day-1`

**End of Day 1 gate:** Live Cloud Run URL responds to NH-48 end-to-end in `< 8s`.

### Day 2 (Apr 21) — React Frontend to Firebase Hosting

**Morning (4 hours)**

13. **Scaffold Vite app** — 30 min
    - `pnpm create vite@latest frontend -- --template react-ts` (or `npm create`)
    - `cd frontend && pnpm install`
    - `pnpm dev` → verify default Vite page loads on `localhost:5173`
    - Delete boilerplate (`App.css`, `assets/react.svg`, default `App.tsx`)

14. **Write `frontend/package.json` deps + scripts, `vite.config.ts`, `tsconfig.json`** — 30 min (code in §12 appendix)
    - Install firebase, react-router-dom, testing libs

15. **Write `frontend/src/lib/firebase.ts` + `AuthProvider`** — 45 min
    - Initialize Firebase client
    - Build `AuthProvider` context with `onAuthStateChanged`
    - Export `useAuth()` hook

16. **Write `frontend/src/lib/api.ts` with `fetchWithAuth` + `streamTriage`** — 60 min (code in §12.F)
    - TDD: write `frontend/src/lib/api.test.ts` first for TC-F3 (SSE parse)
    - Implement until tests pass

17. **Write `frontend/src/hooks/useTriageSSE.ts`** — 45 min (code in §12.E)
    - TDD: `frontend/src/hooks/useTriageSSE.test.ts` for TC-F4 (reconnect)
    - Implement with state machine

**Midday (2 hours)**

18. **Build components** — 90 min
    - `SummaryBanner.tsx`, `ExceptionInput.tsx`, `AgentStream.tsx`, `ClassificationCard.tsx`, `ImpactCard.tsx`
    - Drop in styles from chosen wireframe (copy CSS tokens to `index.css`)
    - Render against mock data in isolation (Vite HMR for rapid iteration)

19. **Build `LoginPage.tsx` and `TriagePage.tsx`** — 30 min (code in §12.G)
    - Wire hook + components together
    - Test against local backend (Vite proxy `/api` → `localhost:8080`)

**Afternoon (3 hours)**

20. **Local end-to-end smoke** — 30 min
    - Run backend locally: `PORT=8080 FRONTEND_ORIGIN=http://localhost:5173 uv run uvicorn supply_chain_triage.main:app`
    - Run frontend: `pnpm --dir frontend dev`
    - Open `localhost:5173`, sign in, submit NH-48, watch events stream
    - Fix whatever breaks

21. **Write `frontend/firebase.json` + `.firebaserc`** — 15 min (code in §12.J)

22. **Write `scripts/deploy_frontend.sh`** — 15 min (code in §12.C)

23. **First frontend deploy** — 30 min
    - Set `VITE_API_BASE_URL=/api` in `frontend/.env.production` (uses Firebase Hosting rewrite)
    - Set `VITE_FIREBASE_*` keys in `frontend/.env.production`
    - `./scripts/deploy_frontend.sh`
    - Capture Hosting URL: `https://nimblefreight-hack.web.app`

24. **Live end-to-end smoke** — 30 min
    - Open Hosting URL in browser
    - Sign in with Google
    - Submit NH-48 scenario
    - Verify stream events render live
    - Check Cloud Trace in GCP Console for spans

25. **Update backend CORS to include Hosting URL** — 15 min
    - Re-deploy backend: `FRONTEND_ORIGIN=https://nimblefreight-hack.web.app ./scripts/deploy_backend.sh`
    - Verify TC-B3 still passes

26. **Run full E2E test suite against live URLs** — 30 min
    - `LIVE_BACKEND_URL=https://... LIVE_FRONTEND_URL=https://... uv run pytest tests/e2e/test_live_deployment.py -v`
    - Expect all TC-E1, TC-E2, TC-E3 PASS

27. **Write ADR-016, ADR-017** — 30 min

28. **Final commit + tag** — 15 min
    - `git commit -m "feat(sprint-5): react frontend + firebase hosting deploy"`
    - `git tag sprint-5-complete`
    - Update `README.md` with live URLs

**End of Day 2 gate:** All 16 acceptance criteria green. Sprint 5 closed.

---

## 9. Definition of Done per Scope Item

| # | Scope Item | DoD |
|---|-----------|-----|
| 1 | `main.py` prod updates | All unit tests pass; `/healthz` + `/readyz` return correct status; CORS uses single origin from env |
| 2 | `scripts/deploy_backend.sh` | Script deploys successfully from a fresh clone; smoke test passes; idempotent (re-run works) |
| 3 | `scripts/deploy_frontend.sh` | Script deploys successfully; Hosting URL returns 200; `/api/**` rewrite works |
| 4 | `scripts/deploy_all.sh` | Orchestrator runs both in order; writes Cloud Run URL to frontend env |
| 5 | `.github/workflows/deploy.yml` | Workflow triggered by push to main deploys both backend + frontend; E2E smoke job passes |
| 6 | `infra/cloudrun.yaml` | YAML matches actual deployed service config (`gcloud run services describe` diff check) |
| 7 | `frontend/package.json` + Vite config | `pnpm install && pnpm build` succeeds; `dist/` contains hashed assets |
| 8 | `frontend/src/App.tsx` + routing | Unit tests pass for authed / unauthed render |
| 9 | `LoginPage.tsx` | Manual: Google sign-in works end-to-end in browser |
| 10 | `TriagePage.tsx` | Manual: submitting NH-48 renders all 5 expected sections |
| 11 | Components (5 files) | Rendered in TriagePage; no React warnings; Vitest snapshots or basic render tests pass |
| 12 | `useTriageSSE.ts` | TC-F3, TC-F4 pass; manual test of mid-stream disconnect |
| 13 | `lib/firebase.ts` | Sign-in + sign-out work; `useAuth()` returns correct state |
| 14 | `lib/api.ts` | TC-F3 passes; `fetchWithAuth` attaches token correctly |
| 15 | `frontend/firebase.json` | Deploy succeeds; `/api/**` rewrite verified by hitting Hosting URL |
| 16 | `tests/e2e/test_live_deployment.py` | All E2E test cases pass against live URLs |
| 17 | `adr-016` | Decision + rationale + alternatives + swap-out paths documented |
| 18 | `adr-017` | Framework + wireframe variant documented |
| 19 | `docs/sprints/sprint-5/*.md` | All 4 dev-diary files created with content |

---

## 10. Risks

### R1 — Cold start exceeds 8-second demo budget
- **Probability**: Medium
- **Severity**: High (judges walk away from a blank screen)
- **Cause**: ADK import overhead is documented at 8-20s for Python Cloud Run services (see research §15, adk-python issue #2433)
- **Mitigation**:
  1. `min_instances=1` keeps one warm instance (~$5/mo, acceptable for 4-day demo window)
  2. Cloud Build defaults to a slim Python base image for source deploys
  3. Gunicorn `--preload` to evaluate app code before listening (moves init cost out of request path; add if cold start is still over budget)
  4. Custom startup probe with generous `failureThreshold` so Cloud Run waits for readiness
  5. Pre-warm before demo: send 3 dummy requests 2 minutes before recording
- **Fallback**: Bump `min_instances=2` for demo day only (~$10/mo); revert after

### R2 — CORS misconfiguration blocks the frontend
- **Probability**: Medium
- **Severity**: High
- **Cause**: Mismatch between `FRONTEND_ORIGIN` env var and actual Hosting URL; trailing-slash bugs; preflight OPTIONS not handled
- **Mitigation**:
  1. Use Firebase Hosting `/api/**` rewrite as primary path (same-origin, no CORS at all)
  2. CORS allowlist as defense-in-depth for direct-to-Cloud-Run calls
  3. TC-B3 test catches wildcard regression
  4. Manual browser DevTools check on Day 2
- **Fallback**: Temporarily add `https://*.web.app` regex to allowlist (less secure but unblocks demo)

### R3 — Cloud Run quota / billing surprise
- **Probability**: Low
- **Severity**: Medium
- **Cause**: Free tier exhausted mid-demo, billing alert triggers, service throttled
- **Mitigation**:
  1. `max_instances=10` hard cap
  2. GCP billing alert at $20/month
  3. Rate limiting at app layer (Sprint 4) prevents runaway
- **Fallback**: Bump quota or lower max_instances

### R4 — React frontend scope creep blows the 1-day budget
- **Probability**: High (user explicitly called this out in sprint plan)
- **Severity**: Medium (we have `adk web` as rollback — see §13)
- **Cause**: Chasing pixel perfection from wireframe; unknown React issues; state management complexity
- **Mitigation**:
  1. Strict component list (6 components, no more)
  2. Use wireframe CSS verbatim — don't re-design
  3. No react-query, no redux, no form libraries — plain `useState` + hook
  4. Vitest only for hook tests, not components
  5. Cut feature list at noon on Day 2 if behind
- **Fallback**: Ship `adk web` in an iframe on a single static page served by Firebase Hosting; call it done

### R5 — EventSource + auth header incompatibility
- **Probability**: Medium (native `EventSource` API does NOT support custom headers — research §15)
- **Severity**: Medium (requires `fetch` + `ReadableStream` fallback)
- **Cause**: We need `Authorization: Bearer <firebase-id-token>` on SSE; `new EventSource(url)` can't set headers
- **Mitigation**: Implement via `fetch` + `response.body.getReader()` + manual SSE parsing in `useTriageSSE.ts` (per research §15). DO NOT use `new EventSource()`.
- **Fallback**: Pass token as query param (`?token=...`) — less secure (tokens in URL show up in logs); only if `fetch` approach fails

### R6 — Firebase Hosting rewrite latency
- **Probability**: Low
- **Severity**: Low
- **Cause**: Hosting → Cloud Run proxy adds `~100-200ms` per request
- **Mitigation**: Acceptable; keeps everything same-origin and eliminates CORS. `pinTag: true` in rewrite config prevents version drift.

### R7 — Workload Identity Federation setup fails
- **Probability**: Medium
- **Severity**: Low (can fall back to JSON key)
- **Cause**: IAM binding subtleties; WIF is new-ish
- **Mitigation**: Start with JSON key in GitHub secret; migrate to WIF post-hackathon. Document in ADR-016 as a known tech-debt item.

### R8 — Source-based deploy slower than expected
- **Probability**: Medium
- **Severity**: Low
- **Cause**: First Cloud Build takes 3-5 min; subsequent builds cache better
- **Mitigation**: Expect it; don't panic; use buildpacks' layer caching

---

## 11. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Live backend URL uptime during demo window (Apr 20-24) | 99.9% | Manual ping every 30 min during demo day |
| Cold-start latency (p50) | `< 3s` warm, `< 8s` from-zero | `time curl $URL/healthz` 10 samples |
| NH-48 E2E latency (p50) | `< 8s` | `test_live_deployment.py::test_triage_stream_end_to_end_nh48` |
| Frontend Lighthouse Performance score | `≥ 80` | `pnpm dlx lighthouse $HOSTING_URL` |
| Frontend bundle size (gzipped) | `< 250 KB` | `du -sh frontend/dist/assets/*.js` after `pnpm build` |
| Fresh-clone deploy time | `< 15 min` | Manual timer during Day 1 |
| Sprint 5 total wall-clock time | `≤ 16 hours` (2 days × 8h) | Time tracker |
| `min_instances=1` monthly cost | `≤ $10` | GCP billing console |
| SSE reconnection success rate | `100%` within 5 retries | TC-F4 |
| E2E test pass rate | `100%` | `pytest tests/e2e/test_live_deployment.py` |
| **Cold-start-from-zero latency** (former AC #6) | `< 8s` (target) | TC-E9 in test-plan.md — run only when time permits, and only after temporarily setting `min_instances=0`; restore `=1` before demo. Demoted from hard AC because verifying it requires breaking AC #4, which undermines demo readiness. |

### 11.1 Latency Budget (NH-48 end-to-end)

Breakdown of the 8-second target for a warm instance, measured submit-to-final-event:

| Segment | Budget | Notes |
|---------|--------|-------|
| Classifier agent (Gemini call + parse) | 1.5 s | Single Gemini `generateContent` call, structured output |
| Impact agent (Firestore reads + Gemini synthesis) | 2.0 s | 2-3 Firestore reads + one Gemini call |
| Coordinator overhead (orchestration + state) | 1.5 s | Session handoff, validator passes, guardrails |
| Network + TLS (browser ↔ Hosting ↔ Cloud Run) | 1.0 s | ~200ms Hosting-to-Run hop + client RTT; Mumbai region |
| Slack / contingency (GC pauses, SSE buffering) | 2.0 s | Absorbs jitter from any segment |
| **Total** | **8.0 s** | Matches AC #6 and TC-E6 gate |

If any segment consistently exceeds its budget in Sprint 5 monitoring, escalate per PRD §10 R1 (pre-warm protocol, Gunicorn `--preload`, `min_instances=2` bump).

---

## 12. Full Code Snippets (A–J)

### 12.A — `src/supply_chain_triage/main.py` (production updates)

```python
"""
FastAPI + ADK production bootstrap for Cloud Run.

Sprint 5 updates from Sprint 0 baseline:
- Reads PORT from env (Cloud Run injects it)
- Reads FRONTEND_ORIGIN from env; enforces single allowlisted origin
- Uses ADC (Application Default Credentials) for Firebase Admin — no SA JSON in secrets
- Enables trace_to_cloud=True for Cloud Trace
- Mounts /api/healthz and /api/readyz for Cloud Run + Firebase Hosting rewrite
- Never calls uvicorn.run() at import time
- Sprint 5 note: default InMemorySessionService. `min_instances=1` keeps one warm
  process so session state survives for the demo. Persistent sessions deferred to
  Tier 2 (DatabaseSessionService on Cloud SQL, or a custom FirestoreSessionService).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

import firebase_admin
import structlog
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import firestore

from supply_chain_triage.config import Settings
from supply_chain_triage.middleware.audit_log import AuditLogMiddleware
from supply_chain_triage.middleware.cors import add_cors_middleware
from supply_chain_triage.middleware.firebase_auth import FirebaseAuthMiddleware
from supply_chain_triage.middleware.input_sanitization import (
    InputSanitizationMiddleware,
)

# ----- Logging (structured JSON for Cloud Logging) -----
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ]
)
log = structlog.get_logger()

# ----- Settings -----
settings = Settings()

# Fail fast on misconfiguration (security-critical)
if settings.env != "dev" and not settings.frontend_origin.startswith("https://"):
    raise RuntimeError(
        f"FRONTEND_ORIGIN must be https:// in non-dev env; got {settings.frontend_origin!r}"
    )

# ----- Firebase Admin (singleton via ADC) -----
_firebase_ready = False


def _init_firebase() -> None:
    """Initialize Firebase Admin using ADC (Cloud Run runtime service account).

    No service-account JSON is ever loaded from Secret Manager. On Cloud Run,
    `firebase_admin.initialize_app()` with no args picks up the runtime SA via
    Application Default Credentials (ADC). Locally, `gcloud auth
    application-default login` provides the same ADC surface.
    """
    global _firebase_ready
    if firebase_admin._apps:
        _firebase_ready = True
        return
    firebase_admin.initialize_app()  # ADC on Cloud Run
    _firebase_ready = True
    log.info("firebase_admin.initialized", project=settings.gcp_project)


def get_firestore_client() -> firestore.Client:
    return firestore.Client(project=settings.gcp_project)


# ----- Lifespan -----
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log.info(
        "app.startup",
        revision=settings.cloud_run_revision,
        frontend_origin=settings.frontend_origin,
    )
    _init_firebase()
    yield
    log.info("app.shutdown")


# ----- ADK FastAPI app -----
AGENTS_DIR = str(Path(__file__).parent / "agents")

app: FastAPI = get_fast_api_app(
    agents_dir=AGENTS_DIR,
    allow_origins=[settings.frontend_origin],
    trace_to_cloud=True,
)

# ADK's get_fast_api_app() does not accept a `lifespan` kwarg; attach to the
# underlying router so our startup hook runs alongside ADK's own lifecycle.
app.router.lifespan_context = lifespan

# ----- Middleware stack (Sprint 0 class-based API) -----
# Order matters: the LAST `add_middleware` call is the OUTERMOST layer
# (runs first on request, last on response). We want audit logging to wrap
# everything else so every request — even auth failures — is logged.
#
# Request flow (outermost → innermost):
#   AuditLogMiddleware           (captures every request)
#     FirebaseAuthMiddleware     (401s unauth; skips /api/healthz, /api/readyz)
#       InputSanitizationMiddleware
#         CORSMiddleware          (added via add_cors_middleware helper)
#           app routes
#
# Rate limiting is handled by per-endpoint slowapi decorators in Sprint 4's
# triage router, not as a global middleware.
add_cors_middleware(app, [settings.frontend_origin])
app.add_middleware(InputSanitizationMiddleware)
app.add_middleware(FirebaseAuthMiddleware)
app.add_middleware(AuditLogMiddleware)  # outermost


# ----- Probes (unauthenticated — exempted via FirebaseAuthMiddleware.PUBLIC_PATHS) -----
# Sprint 5 addition: extend Sprint 0's FirebaseAuthMiddleware.PUBLIC_PATHS to
# include "/api/healthz" and "/api/readyz" so Cloud Run probes bypass auth.
@app.get("/api/healthz", include_in_schema=False)
async def healthz() -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "revision": settings.cloud_run_revision or "local",
            "service": "supply-chain-triage",
        }
    )


@app.get("/api/readyz", include_in_schema=False)
async def readyz() -> JSONResponse:
    if not _firebase_ready:
        return JSONResponse(
            {"status": "not-ready", "reason": "firebase_admin not initialized"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    # Probe Firestore reachability so readyz fails if the runtime SA lacks
    # roles/datastore.user or the project is misconfigured.
    try:
        client = get_firestore_client()
        client.collection("_readyz").document("ping").get()
    except Exception as exc:  # noqa: BLE001 — we want to surface any failure
        return JSONResponse(
            {"status": "not-ready", "error": str(exc)},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return JSONResponse(
        {"status": "ready", "firebase_ready": _firebase_ready}
    )


# ----- Entry for local dev only; Cloud Run uses the exported `app` -----
if __name__ == "__main__":  # pragma: no cover
    import uvicorn

    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run(
        "supply_chain_triage.main:app",
        host="0.0.0.0",  # noqa: S104  # intentional for Cloud Run
        port=port,
        log_config=None,
    )
```

### 12.B — `scripts/deploy_backend.sh`

```bash
#!/usr/bin/env bash
# scripts/deploy_backend.sh
# Sprint 5: Deploy the backend to Cloud Run via source-based build.
#
# Usage:
#   ./scripts/deploy_backend.sh              # uses current gcloud project
#   GCP_PROJECT=my-project ./scripts/deploy_backend.sh
#
# Requirements:
#   - gcloud CLI authenticated: gcloud auth login
#   - APIs enabled: run, cloudbuild, secretmanager, firebase
#   - Secrets exist: gemini-api-key, supermemory-api-key, firebase-sa
#   - Cloud Run runtime SA has roles/secretmanager.secretAccessor on each

set -euo pipefail
trap 'echo "[deploy_backend] FAILED on line $LINENO" >&2' ERR

# ----- Config -----
SERVICE="${SERVICE:-supply-chain-triage}"
REGION="${REGION:-asia-south1}"
GCP_PROJECT="${GCP_PROJECT:-$(gcloud config get-value project 2>/dev/null || true)}"
FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-https://${GCP_PROJECT}.web.app}"
MIN_INSTANCES="${MIN_INSTANCES:-1}"
MAX_INSTANCES="${MAX_INSTANCES:-10}"
MEMORY="${MEMORY:-1Gi}"
CPU="${CPU:-1}"
TIMEOUT="${TIMEOUT:-300}"
CONCURRENCY="${CONCURRENCY:-80}"
RUNTIME_SA="${RUNTIME_SA:-${SERVICE}-runtime@${GCP_PROJECT}.iam.gserviceaccount.com}"
DEPLOY_TAG="${DEPLOY_TAG:-prod}"

echo "[deploy_backend] project=${GCP_PROJECT} service=${SERVICE} region=${REGION}"

# ----- Pre-flight -----
if [[ -z "${GCP_PROJECT}" ]]; then
  echo "[deploy_backend] ERROR: GCP_PROJECT not set and gcloud has no default project" >&2
  exit 1
fi

if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
  echo "[deploy_backend] ERROR: no active gcloud account. Run: gcloud auth login" >&2
  exit 1
fi

# Note: firebase-sa is NOT a secret. Firebase Admin uses ADC via the runtime
# service account (see §6.1). Only Gemini + Supermemory are in Secret Manager.
for secret in gemini-api-key supermemory-api-key; do
  if ! gcloud secrets describe "${secret}" --project "${GCP_PROJECT}" &>/dev/null; then
    echo "[deploy_backend] ERROR: Secret '${secret}' not found in project ${GCP_PROJECT}" >&2
    exit 1
  fi
done

# ----- IAM bindings for the runtime service account (idempotent) -----
# These grants are required for:
#   - Secret Manager access (gemini, supermemory)
#   - Firebase Admin via ADC (no SA JSON)
#   - Firestore reachability (used by /api/readyz + the Impact agent)
echo "[deploy_backend] Ensuring IAM roles on ${RUNTIME_SA} ..."
for role in \
    roles/secretmanager.secretAccessor \
    roles/firebase.sdkAdminServiceAgent \
    roles/datastore.user; do
  gcloud projects add-iam-policy-binding "${GCP_PROJECT}" \
    --member "serviceAccount:${RUNTIME_SA}" \
    --role "${role}" \
    --condition=None \
    --quiet >/dev/null
done

# ----- Deploy -----
echo "[deploy_backend] Deploying from source (tag=${DEPLOY_TAG}) ..."
gcloud run deploy "${SERVICE}" \
  --project "${GCP_PROJECT}" \
  --region "${REGION}" \
  --source . \
  --tag "${DEPLOY_TAG}" \
  --service-account "${RUNTIME_SA}" \
  --allow-unauthenticated \
  --min-instances "${MIN_INSTANCES}" \
  --max-instances "${MAX_INSTANCES}" \
  --memory "${MEMORY}" \
  --cpu "${CPU}" \
  --timeout "${TIMEOUT}" \
  --concurrency "${CONCURRENCY}" \
  --port 8080 \
  --set-env-vars "ENV=prod,GCP_PROJECT=${GCP_PROJECT},FRONTEND_ORIGIN=${FRONTEND_ORIGIN}" \
  --set-secrets "GEMINI_API_KEY=gemini-api-key:latest,SUPERMEMORY_API_KEY=supermemory-api-key:latest" \
  --labels "sprint=5,component=backend"

# ----- Capture URL + smoke test -----
URL="$(gcloud run services describe "${SERVICE}" \
  --project "${GCP_PROJECT}" \
  --region "${REGION}" \
  --format='value(status.url)')"

echo "[deploy_backend] URL: ${URL}"

echo "[deploy_backend] Smoke test: /api/healthz ..."
if curl -sSf "${URL}/api/healthz" > /dev/null; then
  echo "[deploy_backend] healthz OK"
else
  echo "[deploy_backend] ERROR: /api/healthz failed" >&2
  exit 1
fi

echo "[deploy_backend] Smoke test: /api/readyz ..."
if curl -sSf "${URL}/api/readyz" > /dev/null; then
  echo "[deploy_backend] readyz OK"
else
  echo "[deploy_backend] ERROR: /api/readyz failed (Firebase Admin or Firestore reachability issue?)" >&2
  exit 1
fi

mkdir -p .deploy
echo "${URL}" > .deploy/backend-url.txt
echo "[deploy_backend] DONE. URL saved to .deploy/backend-url.txt"
```

### 12.C — `scripts/deploy_frontend.sh`

```bash
#!/usr/bin/env bash
# scripts/deploy_frontend.sh
# Sprint 5: Deploy the React frontend to Firebase Hosting.
#
# Usage:
#   ./scripts/deploy_frontend.sh
#
# Requirements:
#   - firebase CLI authenticated: firebase login
#   - Node 20+ and pnpm installed
#   - frontend/.env.production populated (VITE_API_BASE_URL, VITE_FIREBASE_*)

set -euo pipefail
trap 'echo "[deploy_frontend] FAILED on line $LINENO" >&2' ERR

FRONTEND_DIR="${FRONTEND_DIR:-frontend}"
FIREBASE_PROJECT="${FIREBASE_PROJECT:-$(jq -r '.projects.default' ${FRONTEND_DIR}/.firebaserc 2>/dev/null || echo "")}"

if [[ -z "${FIREBASE_PROJECT}" ]]; then
  echo "[deploy_frontend] ERROR: Firebase project not set. Set FIREBASE_PROJECT env or populate ${FRONTEND_DIR}/.firebaserc" >&2
  exit 1
fi

echo "[deploy_frontend] project=${FIREBASE_PROJECT} dir=${FRONTEND_DIR}"

# ----- Install + build -----
echo "[deploy_frontend] Installing deps ..."
pnpm --dir "${FRONTEND_DIR}" install --frozen-lockfile

echo "[deploy_frontend] Type-checking ..."
pnpm --dir "${FRONTEND_DIR}" typecheck

echo "[deploy_frontend] Building ..."
pnpm --dir "${FRONTEND_DIR}" build

if [[ ! -d "${FRONTEND_DIR}/dist" ]]; then
  echo "[deploy_frontend] ERROR: ${FRONTEND_DIR}/dist not found after build" >&2
  exit 1
fi

BUNDLE_SIZE="$(du -sh "${FRONTEND_DIR}/dist" | cut -f1)"
echo "[deploy_frontend] Bundle size: ${BUNDLE_SIZE}"

# ----- Deploy -----
echo "[deploy_frontend] firebase deploy ..."
(cd "${FRONTEND_DIR}" && firebase deploy --only hosting --project "${FIREBASE_PROJECT}")

HOSTING_URL="https://${FIREBASE_PROJECT}.web.app"
echo "[deploy_frontend] URL: ${HOSTING_URL}"

# ----- Smoke test: index loads -----
echo "[deploy_frontend] Smoke test: index.html ..."
if curl -sSf "${HOSTING_URL}/" | grep -q '<div id="root"'; then
  echo "[deploy_frontend] index OK"
else
  echo "[deploy_frontend] ERROR: index.html did not contain expected marker" >&2
  exit 1
fi

# ----- Smoke test: /api/healthz proxy -----
echo "[deploy_frontend] Smoke test: /api/healthz rewrite ..."
if curl -sSf "${HOSTING_URL}/api/healthz" > /dev/null; then
  echo "[deploy_frontend] rewrite OK"
else
  echo "[deploy_frontend] WARNING: /api/healthz rewrite failed (backend may not be deployed yet)" >&2
fi

mkdir -p .deploy
echo "${HOSTING_URL}" > .deploy/frontend-url.txt
echo "[deploy_frontend] DONE. URL saved to .deploy/frontend-url.txt"
```

### 12.D — `.github/workflows/deploy.yml` (finalized)

```yaml
# .github/workflows/deploy.yml
# Sprint 5: Finalized deploy pipeline.
# Triggers on push to main affecting backend or frontend code.
# Uses Workload Identity Federation (NOT JSON keys) per ADR-016.

name: deploy

on:
  push:
    branches: [main]
    paths:
      - "src/**"
      - "frontend/**"
      - "scripts/deploy_*.sh"
      - "pyproject.toml"
      - "infra/cloudrun.yaml"
      - ".github/workflows/deploy.yml"
  workflow_dispatch:

permissions:
  contents: read
  id-token: write  # Required for Workload Identity Federation

env:
  GCP_PROJECT: nimblefreight-hack
  REGION: asia-south1
  SERVICE: supply-chain-triage

jobs:
  deploy-backend:
    runs-on: ubuntu-latest
    outputs:
      url: ${{ steps.capture.outputs.url }}
    steps:
      - uses: actions/checkout@v4

      - name: Authenticate to GCP (WIF)
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: projects/${{ secrets.GCP_PROJECT_NUMBER }}/locations/global/workloadIdentityPools/github/providers/github
          service_account: github-deploy@${{ env.GCP_PROJECT }}.iam.gserviceaccount.com

      - name: Setup gcloud
        uses: google-github-actions/setup-gcloud@v2

      - name: Setup Python 3.13
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install uv
        run: pip install uv

      - name: Deploy to Cloud Run
        env:
          FRONTEND_ORIGIN: https://${{ env.GCP_PROJECT }}.web.app
        run: ./scripts/deploy_backend.sh

      - name: Capture URL
        id: capture
        run: |
          URL=$(cat .deploy/backend-url.txt)
          echo "url=${URL}" >> "$GITHUB_OUTPUT"
          echo "Backend deployed to ${URL}"

  deploy-frontend:
    runs-on: ubuntu-latest
    needs: deploy-backend
    steps:
      - uses: actions/checkout@v4

      - name: Authenticate to GCP (WIF)
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: projects/${{ secrets.GCP_PROJECT_NUMBER }}/locations/global/workloadIdentityPools/github/providers/github
          service_account: github-deploy@${{ env.GCP_PROJECT }}.iam.gserviceaccount.com

      - name: Setup Node 20
        uses: actions/setup-node@v4
        with:
          node-version: "20"

      - name: Install pnpm
        uses: pnpm/action-setup@v4
        with:
          version: 9

      - name: Install firebase CLI
        run: npm install -g firebase-tools@^13

      - name: Write frontend/.env.production
        run: |
          cat > frontend/.env.production <<EOF
          VITE_API_BASE_URL=/api
          VITE_FIREBASE_API_KEY=${{ secrets.VITE_FIREBASE_API_KEY }}
          VITE_FIREBASE_AUTH_DOMAIN=${{ secrets.VITE_FIREBASE_AUTH_DOMAIN }}
          VITE_FIREBASE_PROJECT_ID=${{ env.GCP_PROJECT }}
          VITE_FIREBASE_APP_ID=${{ secrets.VITE_FIREBASE_APP_ID }}
          EOF

      - name: Deploy to Firebase Hosting
        env:
          FIREBASE_PROJECT: ${{ env.GCP_PROJECT }}
        run: ./scripts/deploy_frontend.sh

  e2e-smoke:
    runs-on: ubuntu-latest
    needs: [deploy-backend, deploy-frontend]
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python 3.13
        uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install uv + deps
        run: |
          pip install uv
          uv sync --group test

      - name: Run live smoke tests
        env:
          LIVE_BACKEND_URL: ${{ needs.deploy-backend.outputs.url }}
          LIVE_FRONTEND_URL: https://${{ env.GCP_PROJECT }}.web.app
          FIREBASE_TEST_TOKEN: ${{ secrets.FIREBASE_TEST_TOKEN }}
        run: uv run pytest tests/e2e/test_live_deployment.py -v
```

### 12.E — `frontend/src/hooks/useTriageSSE.ts`

```typescript
// frontend/src/hooks/useTriageSSE.ts
// Sprint 5: React hook to stream /api/triage/stream events.
//
// Why not native EventSource?
//   The EventSource API cannot attach custom request headers (no Authorization: Bearer).
//   We use fetch + ReadableStream + manual SSE parsing so we can pass the Firebase ID token.
//
// State machine:
//   idle -> connecting -> streaming -> done
//                                   -> error -> reconnecting -> connecting
// Reconnect: exponential backoff 1s, 2s, 4s, 8s, 16s (max 5 attempts, max 30s delay).

import { useCallback, useEffect, useRef, useState } from "react";
import type { ExceptionEvent, StreamEvent } from "../types/triage";
import { streamTriage } from "../lib/api";

export type SSEState =
  | "idle"
  | "connecting"
  | "streaming"
  | "done"
  | "error"
  | "reconnecting";

interface UseTriageSSEResult {
  state: SSEState;
  events: StreamEvent[];
  error: string | null;
  start: (event: ExceptionEvent) => void;
  cancel: () => void;
  reset: () => void;
}

const MAX_RETRIES = 5;
const BASE_DELAY_MS = 1_000;
const MAX_DELAY_MS = 30_000;

export function useTriageSSE(): UseTriageSSEResult {
  const [state, setState] = useState<SSEState>("idle");
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const retriesRef = useRef<number>(0);
  const lastEventRef = useRef<ExceptionEvent | null>(null);

  const cancel = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  const reset = useCallback(() => {
    cancel();
    setState("idle");
    setEvents([]);
    setError(null);
    retriesRef.current = 0;
    lastEventRef.current = null;
  }, [cancel]);

  const runOnce = useCallback(
    async (event: ExceptionEvent): Promise<void> => {
      const controller = new AbortController();
      abortRef.current = controller;
      setState("connecting");

      try {
        await streamTriage(
          event,
          (streamEvent) => {
            setState("streaming");
            setEvents((prev) => [...prev, streamEvent]);
          },
          controller.signal,
        );
        setState("done");
        retriesRef.current = 0;
      } catch (err) {
        if (controller.signal.aborted) {
          return; // user cancelled, do not treat as error
        }
        const message = err instanceof Error ? err.message : String(err);
        setError(message);

        if (retriesRef.current < MAX_RETRIES) {
          const delay = Math.min(
            BASE_DELAY_MS * 2 ** retriesRef.current,
            MAX_DELAY_MS,
          );
          retriesRef.current += 1;
          setState("reconnecting");
          setTimeout(() => {
            if (lastEventRef.current) {
              void runOnce(lastEventRef.current);
            }
          }, delay);
        } else {
          setState("error");
        }
      }
    },
    [],
  );

  const start = useCallback(
    (event: ExceptionEvent) => {
      reset();
      lastEventRef.current = event;
      void runOnce(event);
    },
    [reset, runOnce],
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  return { state, events, error, start, cancel, reset };
}
```

### 12.F — `frontend/src/lib/api.ts`

```typescript
// frontend/src/lib/api.ts
// Sprint 5: API client with Firebase ID token injection + SSE streaming parser.

import { getAuth } from "firebase/auth";
import type { ExceptionEvent, StreamEvent } from "../types/triage";

const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "/api";

async function getIdToken(): Promise<string> {
  const auth = getAuth();
  const user = auth.currentUser;
  if (!user) {
    throw new Error("Not authenticated");
  }
  return user.getIdToken(/* forceRefresh */ false);
}

export async function fetchWithAuth(
  path: string,
  init?: RequestInit,
): Promise<Response> {
  const token = await getIdToken();
  const headers = new Headers(init?.headers);
  headers.set("Authorization", `Bearer ${token}`);
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  return fetch(`${API_BASE_URL}${path}`, { ...init, headers });
}

/**
 * POST /api/triage/stream and parse the SSE response body.
 *
 * The backend emits SSE frames like:
 *   event: classifier_done
 *   data: {"type":"classifier_done","payload":{...}}
 *   \n
 *
 * We read the ReadableStream, split on "\n\n", parse each frame, and
 * invoke onEvent for every data line.
 */
export async function streamTriage(
  event: ExceptionEvent,
  onEvent: (se: StreamEvent) => void,
  signal: AbortSignal,
): Promise<void> {
  const token = await getIdToken();
  const response = await fetch(`${API_BASE_URL}/triage/stream`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
      Accept: "text/event-stream",
    },
    body: JSON.stringify(event),
    signal,
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${await response.text()}`);
  }
  if (!response.body) {
    throw new Error("Response body is empty");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  // Extract the next complete SSE frame from the buffer.
  // Per the SSE spec, a frame ends with a blank line, where line terminators
  // may be "\n", "\r\n", or "\r". We scan for any of "\n\n", "\r\n\r\n",
  // or "\r\r" and return the earliest match so a frame is never split across
  // a CRLF boundary that straddles two reads.
  const takeFrame = (): { frame: string; rest: string } | null => {
    const candidates = ["\r\n\r\n", "\n\n", "\r\r"] as const;
    let best = -1;
    let bestLen = 0;
    for (const sep of candidates) {
      const idx = buffer.indexOf(sep);
      if (idx !== -1 && (best === -1 || idx < best)) {
        best = idx;
        bestLen = sep.length;
      }
    }
    if (best === -1) return null;
    return { frame: buffer.slice(0, best), rest: buffer.slice(best + bestLen) };
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      if (buffer.trim().length > 0) {
        parseFrame(buffer, onEvent);
      }
      return;
    }
    buffer += decoder.decode(value, { stream: true });

    let next = takeFrame();
    while (next !== null) {
      parseFrame(next.frame, onEvent);
      buffer = next.rest;
      next = takeFrame();
    }
  }
}

function parseFrame(frame: string, onEvent: (se: StreamEvent) => void): void {
  // Split on any of "\r\n", "\n", "\r" so a single CR line ending does not
  // merge two SSE fields.
  const lines = frame.split(/\r\n|\n|\r/);
  const dataLines: string[] = [];
  for (const line of lines) {
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (dataLines.length === 0) return;
  try {
    const payload = JSON.parse(dataLines.join("\n")) as StreamEvent;
    onEvent(payload);
  } catch (err) {
    console.warn("[api] malformed SSE frame", err, frame);
  }
}
```

### 12.G — `frontend/src/pages/TriagePage.tsx`

```tsx
// frontend/src/pages/TriagePage.tsx
// Sprint 5: Main triage screen composing all components.

import { useMemo } from "react";
import type { ReactElement } from "react";
import { SummaryBanner } from "../components/SummaryBanner";
import { ExceptionInput } from "../components/ExceptionInput";
import { AgentStream } from "../components/AgentStream";
import { ClassificationCard } from "../components/ClassificationCard";
import { ImpactCard } from "../components/ImpactCard";
import { useTriageSSE } from "../hooks/useTriageSSE";
import type {
  ClassificationResult,
  ImpactResult,
  ExceptionEvent,
} from "../types/triage";

// React 19 no longer ships `JSX.Element` as a global; import `ReactElement`
// from "react" instead to keep `strict: true` tsconfig happy.
export function TriagePage(): ReactElement {
  const { state, events, error, start, reset } = useTriageSSE();

  const classification = useMemo<ClassificationResult | null>(() => {
    const done = events.find((e) => e.type === "classifier_done");
    return done && "classification" in done.payload
      ? (done.payload.classification as ClassificationResult)
      : null;
  }, [events]);

  const impact = useMemo<ImpactResult | null>(() => {
    const done = events.find((e) => e.type === "impact_done");
    return done && "impact" in done.payload
      ? (done.payload.impact as ImpactResult)
      : null;
  }, [events]);

  const handleSubmit = (event: ExceptionEvent): void => {
    start(event);
  };

  return (
    <div className="triage-page">
      <SummaryBanner />

      <main className="triage-grid">
        <section className="panel panel--input">
          <h2>Report Exception</h2>
          <ExceptionInput
            onSubmit={handleSubmit}
            disabled={state === "streaming" || state === "connecting"}
          />
          {error && (
            <div className="error-banner" role="alert">
              {error}
              <button type="button" onClick={reset}>
                Reset
              </button>
            </div>
          )}
        </section>

        <section className="panel panel--stream">
          <h2>Agent Activity</h2>
          <AgentStream events={events} state={state} />
        </section>

        <section className="panel panel--results">
          <h2>Classification</h2>
          {classification ? (
            <ClassificationCard result={classification} />
          ) : (
            <p className="muted">Awaiting classifier...</p>
          )}
        </section>

        <section className="panel panel--impact">
          <h2>Impact</h2>
          {impact ? (
            <ImpactCard result={impact} />
          ) : (
            <p className="muted">Awaiting impact assessment...</p>
          )}
        </section>
      </main>
    </div>
  );
}
```

### 12.H — `infra/cloudrun.yaml`

```yaml
# infra/cloudrun.yaml
# Sprint 5: Declarative Cloud Run service spec (source-of-truth documentation).
# The deploy script uses `gcloud run deploy --source .` with equivalent flags.
# This file can alternatively be applied via:
#   gcloud run services replace infra/cloudrun.yaml

apiVersion: serving.knative.dev/v1
kind: Service
metadata:
  name: supply-chain-triage
  namespace: nimblefreight-hack
  labels:
    sprint: "5"
    component: backend
  annotations:
    run.googleapis.com/ingress: all
    run.googleapis.com/description: "Supply Chain Triage API (Sprint 5)"
spec:
  template:
    metadata:
      annotations:
        autoscaling.knative.dev/minScale: "1"
        autoscaling.knative.dev/maxScale: "10"
        run.googleapis.com/cpu-throttling: "false"
        run.googleapis.com/startup-cpu-boost: "true"
    spec:
      serviceAccountName: supply-chain-triage-runtime@nimblefreight-hack.iam.gserviceaccount.com
      containerConcurrency: 80
      timeoutSeconds: 300
      containers:
        - image: REPLACED_BY_SOURCE_BUILD
          ports:
            - name: http1
              containerPort: 8080
          resources:
            limits:
              cpu: "1"
              memory: 1Gi
          startupProbe:
            httpGet:
              path: /api/readyz
              port: 8080
            initialDelaySeconds: 5
            periodSeconds: 3
            failureThreshold: 20
            timeoutSeconds: 5
          livenessProbe:
            httpGet:
              path: /api/healthz
              port: 8080
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 3
          env:
            - name: ENV
              value: prod
            - name: GCP_PROJECT
              value: nimblefreight-hack
            - name: FRONTEND_ORIGIN
              value: https://nimblefreight-hack.web.app
            # Firebase Admin uses ADC via the runtime SA (roles/firebase.sdkAdminServiceAgent)
            # — no FIREBASE_SERVICE_ACCOUNT secret is mounted.
            # Session state uses the default InMemorySessionService (min_instances=1 keeps
            # one warm process). Persistent sessions are deferred to Tier 2.
            - name: GEMINI_API_KEY
              valueFrom:
                secretKeyRef:
                  name: gemini-api-key
                  key: latest
            - name: SUPERMEMORY_API_KEY
              valueFrom:
                secretKeyRef:
                  name: supermemory-api-key
                  key: latest
  traffic:
    - percent: 100
      latestRevision: true
```

### 12.I — `tests/e2e/test_live_deployment.py`

```python
# tests/e2e/test_live_deployment.py
# Sprint 5: End-to-end smoke tests against the LIVE deployed URLs.
"""
End-to-end smoke tests for Sprint 5 Cloud Run + Firebase Hosting deployment.

Run locally:
    LIVE_BACKEND_URL=https://... \
    LIVE_FRONTEND_URL=https://... \
    FIREBASE_TEST_TOKEN=<minted-token> \
    uv run pytest tests/e2e/test_live_deployment.py -v
"""
from __future__ import annotations

import os
import time

import httpx
import pytest

LIVE_BACKEND_URL = os.environ.get("LIVE_BACKEND_URL")
LIVE_FRONTEND_URL = os.environ.get("LIVE_FRONTEND_URL")
FIREBASE_TEST_TOKEN = os.environ.get("FIREBASE_TEST_TOKEN")

pytestmark = pytest.mark.skipif(
    not LIVE_BACKEND_URL or not LIVE_FRONTEND_URL,
    reason="LIVE_BACKEND_URL and LIVE_FRONTEND_URL required",
)


# ---------------- Fixtures ----------------


@pytest.fixture(scope="module")
def backend() -> str:
    assert LIVE_BACKEND_URL is not None
    return LIVE_BACKEND_URL.rstrip("/")


@pytest.fixture(scope="module")
def frontend() -> str:
    assert LIVE_FRONTEND_URL is not None
    return LIVE_FRONTEND_URL.rstrip("/")


@pytest.fixture(scope="module")
def auth_headers() -> dict[str, str]:
    if not FIREBASE_TEST_TOKEN:
        pytest.skip("FIREBASE_TEST_TOKEN required for authenticated tests")
    return {"Authorization": f"Bearer {FIREBASE_TEST_TOKEN}"}


@pytest.fixture(scope="module")
def nh48_body() -> dict[str, object]:
    # NH-48 anchor scenario — see Supply-Chain-Demo-Scenario-Tier1
    return {
        "event_type": "delay",
        "reference_id": "NH-48-001",
        "narrative": (
            "Truck KM-72 carrying 3 tonnes of frozen poultry broke down on "
            "NH-48 between Surat and Mumbai at 14:30 IST. ETA delay "
            "estimated 4-6 hours. Reefer still operational on battery."
        ),
        "metadata": {"carrier_id": "nimble-01", "shipment_id": "SH-2026-0412-3"},
    }


# ---------------- TC-E1 ----------------


def test_backend_healthz_returns_200(backend: str) -> None:
    r = httpx.get(f"{backend}/api/healthz", timeout=10.0)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "revision" in body


def test_backend_readyz_returns_200(backend: str) -> None:
    r = httpx.get(f"{backend}/api/readyz", timeout=10.0)
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


# ---------------- TC-E2 ----------------


def test_frontend_hosting_serves_index_html(frontend: str) -> None:
    r = httpx.get(f"{frontend}/", timeout=10.0, follow_redirects=True)
    assert r.status_code == 200
    assert 'id="root"' in r.text


def test_frontend_api_proxy_reaches_cloud_run(frontend: str) -> None:
    """Firebase Hosting /api/** rewrite must reach Cloud Run."""
    r = httpx.get(f"{frontend}/api/healthz", timeout=10.0)
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ---------------- TC-E3 ----------------


def test_unauth_triage_stream_is_401(backend: str, nh48_body: dict[str, object]) -> None:
    r = httpx.post(
        f"{backend}/api/triage/stream",
        json=nh48_body,
        timeout=10.0,
    )
    assert r.status_code == 401


def test_triage_stream_end_to_end_nh48(
    backend: str,
    auth_headers: dict[str, str],
    nh48_body: dict[str, object],
) -> None:
    """Full NH-48 pipeline on the live URL must complete under 10 seconds."""
    start_time = time.monotonic()
    events: list[str] = []

    with httpx.stream(
        "POST",
        f"{backend}/api/triage/stream",
        json=nh48_body,
        headers={**auth_headers, "Accept": "text/event-stream"},
        timeout=15.0,
    ) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")
        for line in r.iter_lines():
            if line.startswith("event:"):
                events.append(line.split(":", 1)[1].strip())
            if "final" in events:
                break

    elapsed = time.monotonic() - start_time
    assert elapsed < 10.0, f"Stream took {elapsed:.2f}s (target <10s)"
    assert "classifier_done" in events
    assert "impact_done" in events
    assert "final" in events


def test_cors_blocks_evil_origin(backend: str) -> None:
    """A preflight from an unallowed origin should not get Access-Control-Allow-Origin matched."""
    r = httpx.options(
        f"{backend}/api/triage/stream",
        headers={
            "Origin": "https://evil.example.com",
            "Access-Control-Request-Method": "POST",
        },
        timeout=10.0,
    )
    allow = r.headers.get("access-control-allow-origin", "")
    assert allow != "https://evil.example.com"
    assert allow != "*"
```

### 12.J — `frontend/firebase.json`

```json
{
  "hosting": {
    "public": "dist",
    "ignore": [
      "firebase.json",
      "**/.*",
      "**/node_modules/**"
    ],
    "rewrites": [
      {
        "source": "/api/**",
        "run": {
          "serviceId": "supply-chain-triage",
          "region": "asia-south1",
          "tag": "prod",
          "pinTag": true
        }
      },
      {
        "source": "**",
        "destination": "/index.html"
      }
    ],
    "headers": [
      {
        "source": "/assets/**",
        "headers": [
          {
            "key": "Cache-Control",
            "value": "public, max-age=31536000, immutable"
          }
        ]
      },
      {
        "source": "/index.html",
        "headers": [
          {
            "key": "Cache-Control",
            "value": "no-cache, no-store, must-revalidate"
          }
        ]
      },
      {
        "source": "**",
        "headers": [
          {
            "key": "Strict-Transport-Security",
            "value": "max-age=31536000; includeSubDomains"
          },
          {
            "key": "X-Content-Type-Options",
            "value": "nosniff"
          },
          {
            "key": "Referrer-Policy",
            "value": "strict-origin-when-cross-origin"
          }
        ]
      }
    ]
  }
}
```

### 12 Appendix — `frontend/package.json` + `vite.config.ts` (reference)

```json
{
  "name": "supply-chain-triage-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest",
    "lint": "eslint src --ext .ts,.tsx",
    "typecheck": "tsc -b --noEmit"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "react-router-dom": "^7.0.0",
    "firebase": "^11.0.0"
  },
  "devDependencies": {
    "@types/node": "^22.0.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@typescript-eslint/eslint-plugin": "^8.0.0",
    "@typescript-eslint/parser": "^8.0.0",
    "@vitejs/plugin-react": "^5.0.0",
    "@testing-library/jest-dom": "^6.0.0",
    "@testing-library/react": "^16.0.0",
    "eslint": "^9.0.0",
    "jsdom": "^25.0.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "vitest": "^2.0.0"
  }
}
```

```typescript
// frontend/vite.config.ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8080",
        changeOrigin: true,
        secure: false,
      },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
    target: "es2022",
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
  },
});
```

---

## 13. Rollback Plan

Sprint 5 has multiple rollback tiers; pick the highest tier that still lets us demo.

### Tier 1 — Everything works (target)
- React frontend on Firebase Hosting + Cloud Run backend
- Full UI + streaming + auth
- This is the plan

### Tier 2 — React blows the budget (most likely rollback)
**Trigger:** End of Day 2 morning (12:00 IST Apr 21) and the React app is still not rendering NH-48 end-to-end
**Action:**
1. Stop React work immediately
2. Build a minimal static page (`frontend/dist/index.html`) that embeds `adk web` in an iframe pointed at the Cloud Run URL + an info card with project context
3. Deploy that single HTML page to Firebase Hosting
4. Backend stays deployed on Cloud Run; demo uses `adk web`
5. Update ADR-017 to record the cut
**Time budget:** 1 hour

### Tier 3 — Cloud Run deploy fails hard
**Trigger:** End of Day 1 and `gcloud run deploy` fails repeatedly with unclear errors
**Action:**
1. Spin up a local `uvicorn` process on the dev machine
2. Run `ngrok http 8080` to get a public HTTPS tunnel
3. Point frontend at the ngrok URL
4. Demo from the dev laptop over ngrok (laptop must stay awake)
5. Log Cloud Run failure in risks.md and retry post-Sprint-6 if time allows
**Caveat:** Judges CAN click the URL, but it's only live when the laptop is on. Acceptable for a recorded demo video, risky for a live demo.

### Tier 4 — Total infra failure
**Trigger:** Neither Cloud Run nor Firebase Hosting works; GCP project has billing / IAM issues
**Action:**
1. Record a demo video locally showing `adk web` executing NH-48
2. Submit: video + README + source code; acknowledge "live URL" is a known gap
3. This is Tier 1 submission per [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] §Must-Have — technically passes but loses points on "live URL" criterion
**Time budget:** 2 hours to record + edit

### Rollback decision checkpoint
**Day 2 noon (Apr 21 12:00 IST):** Review progress. If not at least at Tier 1 scope "backend live + frontend rendering locally", formally downgrade to Tier 2.

---

## 14. Cross-References

### Upstream (this PRD consumes)
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — Sprint 5 window, Must-Have criteria, risks R1-R8
- [[Supply-Chain-Deployment-Options-Research]] — 4 options, rationale for Option B, CI/CD decision
- [[Supply-Chain-Architecture-Decision-Analysis]] — D+F architecture driving deployment shape
- [[Supply-Chain-Product-Recap]] — Wireframes, demo narrative
- [[Supply-Chain-Demo-Scenario-Tier1]] — NH-48 scenario body used in E2E test
- [[Supply-Chain-Firestore-Schema-Tier1]] — Firestore schema referenced by session-service URI
- `docs/sprints/sprint-0/prd.md` — Sprint 0 foundation this PRD builds on
- `docs/sprints/sprint-4/prd.md` — `/triage/stream` endpoint spec (hard dependency)

### Downstream (future PRDs consume this)
- `docs/sprints/sprint-6/prd.md` (Submission) — uses the live URLs from this sprint in the demo video + README
- `docs/decisions/adr-016-deployment-target-finalized.md` — authoritative record of the deployment choice
- `docs/decisions/adr-017-frontend-framework-wireframe.md` — authoritative record of frontend choice

---

## 15. Research Citations

All research conducted 2026-04-10 for this PRD.

### Cloud Run + ADK deployment
- [Cloud Run — Agent Development Kit (ADK)](https://google.github.io/adk-docs/deploy/cloud-run/) — Official ADK Cloud Run guide; covers `get_fast_api_app()` with `agents_dir` parameter (note: `agent_dir` → `agents_dir` rename in newer releases)
- [Deploy, Manage, and Observe ADK Agent on Cloud Run — Google Codelabs](https://codelabs.developers.google.com/deploy-manage-observe-adk-cloud-run)
- [Quickstart: Build and deploy an AI agent to Cloud Run using the ADK — Google Cloud](https://docs.cloud.google.com/run/docs/quickstarts/build-and-deploy/deploy-python-adk-service)
- [How to Deploy ADK Agents onto Google Cloud Run — Karl Weinmeister, Google Cloud Community](https://medium.com/google-cloud/how-to-deploy-adk-agents-onto-google-cloud-run-5bbd62049a19)
- [Bug in Cloud Run Deployment · google/adk-python#1025](https://github.com/google/adk-python/issues/1025)

### Cold start + cost optimization
- [ADK import overhead (8-20s) causes slow cold starts · google/adk-python#2433](https://github.com/google/adk-python/issues/2433) — **key finding: plan for cold-start overhead with `min_instances=1`**
- [Advanced Performance Tuning for FastAPI on Google Cloud Run — David Muraya](https://davidmuraya.com/blog/fastapi-performance-tuning-on-google-cloud-run/)
- [Optimize Python applications for Cloud Run — Google Cloud docs](https://docs.cloud.google.com/run/docs/tips/python)
- [Set minimum instances for services — Cloud Run docs](https://docs.cloud.google.com/run/docs/configuring/min-instances) — `--min-instances=1` pattern
- [How to Configure Minimum Instances on Cloud Run to Eliminate Cold Starts — OneUptime (2026-02-17)](https://oneuptime.com/blog/post/2026-02-17-how-to-configure-minimum-instances-on-cloud-run-to-eliminate-cold-starts-for-production-services/view)
- [Tune Cloud Run Concurrency Settings — OneUptime (2026-02-17)](https://oneuptime.com/blog/post/2026-02-17-how-to-tune-cloud-run-concurrency-settings-to-maximize-request-throughput-per-instance/view)
- [3 Ways to optimize Cloud Run response times — Google Cloud Blog](https://cloud.google.com/blog/topics/developers-practitioners/3-ways-optimize-cloud-run-response-times)

### React SSE (EventSource + headers limitation)
- [Implementing React SSE — Logan Lee, Medium](https://medium.com/@dlrnjstjs/implementing-react-sse-server-sent-events-real-time-notification-system-a999bb983d1b) — **confirms native EventSource cannot attach auth headers; use fetch + ReadableStream**
- [How to Implement Server-Sent Events (SSE) in React — OneUptime (2026-01-15)](https://oneuptime.com/blog/post/2026-01-15-server-sent-events-sse-react/view) — exponential backoff reconnect pattern
- [Implementing Server-Sent Events with Axios in React TypeScript — Joel, Medium](https://medium.com/@thisisjoel/implementing-server-sent-events-with-axios-in-react-typescript-2c94f767cdc2)
- [react-eventsource — npm](https://www.npmjs.com/package/react-eventsource) — library option (we implement manually)
- [react-sse-hooks — GitHub](https://github.com/NepeinAV/react-sse-hooks) — reference patterns

### Vite + React + Firebase
- [Vite + Firebase: How to deploy React App — Rajdeep Mallick, Medium](https://medium.com/@rajdeepmallick999/vite-firebase-how-to-deploy-react-app-5e5090730147)
- [Firebase: deploy a React application with Firebase Hosting — DEV Community](https://dev.to/this-is-learning/firebase-deploy-a-react-application-with-firebase-hosting-560j)
- [Deploying Vite + React App to Firebase with Staging and Production Environments — DEV Community](https://dev.to/aqibnawazdev/deploying-vite-react-app-to-firebase-with-staging-and-production-environments-4ekm)
- [firebase-react-vite — nimit2801/GitHub](https://github.com/nimit2801/firebase-react-vite)
- [Vite proxy setup guide — Muyiwa Johnson](https://www.muyiwajohnson.dev/blog/vite-proxy-setup-guide) — dev-only proxy note
- [What web frameworks does Firebase App Hosting support? — Firebase Blog (2025-06)](https://firebase.blog/posts/2025/06/app-hosting-frameworks/)
- [CORS (Cross-Origin Resource Sharing) — FastAPI](https://fastapi.tiangolo.com/tutorial/cors/)

### Firebase Hosting + Cloud Run rewrites
- [Serve dynamic content and host microservices with Cloud Run — Firebase Hosting docs](https://firebase.google.com/docs/hosting/cloud-run) — **authoritative `firebase.json` rewrite shape for Cloud Run**
- [How to Use Firebase Hosting Rewrites to Route Traffic to Cloud Run Services — OneUptime (2026-02-17)](https://oneuptime.com/blog/post/2026-02-17-how-to-use-firebase-hosting-rewrites-to-route-traffic-to-cloud-run-services/view) — `pinTag: true` pattern
- [Configure Hosting behavior — Firebase Hosting docs](https://firebase.google.com/docs/hosting/full-config)
- [Firebase Hosting for Cloud Run — Firebase Blog (2019-04)](https://firebase.blog/posts/2019/04/firebase-hosting-and-cloud-run/)

### Firebase Auth React
- [Authenticate Using Google with JavaScript — Firebase docs (updated 2026-04-09)](https://firebase.google.com/docs/auth/web/google-signin) — `signInWithPopup` + `GoogleAuthProvider` canonical pattern
- [Google SignIn using Firebase Authentication in ReactJS — GeeksforGeeks](https://www.geeksforgeeks.org/reactjs/google-signin-using-firebase-authentication-in-reactjs/)
- [Handling user authentication with Firebase in your React apps — LogRocket](https://blog.logrocket.com/user-authentication-firebase-react-apps/)

### Key findings applied to this PRD
1. **Native `EventSource` does NOT support custom headers** → use `fetch` + `ReadableStream` manual SSE parsing in §12.E, §12.F
2. **ADK Python cold-start is 8-20s** → `min_instances=1` in §12.B, startup probe with `failureThreshold: 20` in §12.H
3. **`agents_dir` (not `agent_dir`) is the current parameter name** → used correctly in §12.A
4. **Firebase Hosting rewrite with `pinTag: true` prevents revision drift** → used in §12.J
5. **Vite dev proxy doesn't apply in prod** → Firebase Hosting rewrite handles prod, proxy is dev-only (§12 appendix)
6. **Gunicorn `--preload` moves init cost out of request path** → documented in §10 R1 as escalation step if cold start exceeds budget

---

## 16. Open Assumptions

These are decisions that the PRD assumes but must be confirmed before or during execution. Flagged explicitly so the executing engineer resolves them up front.

| # | Assumption | Default | Must confirm by |
|---|-----------|---------|-----------------|
| 1 | **Wireframe variant chosen** | Variant A (Command Center) | Before scope item 2.5 starts (Day 2 morning) |
| 2 | **GCP project ID** | `nimblefreight-hack` | Day 1 morning pre-flight |
| 3 | **Firebase project ID** | Same as GCP project | Day 1 morning pre-flight |
| 4 | **Cloud Run region** | `asia-south1` (Mumbai, matches Firestore) | Day 1 morning |
| 5 | **`min_instances` budget** | `1` (~$5/mo) | Before Day 1 deploy |
| 6 | **Frontend origin URL** | `https://<project-id>.web.app` (Firebase default) | Day 2 before backend re-deploy |
| 7 | **Package manager for frontend** | `pnpm` (falls back to `npm` if pnpm unavailable in CI) | Day 2 morning |
| 8 | **Workload Identity Federation setup** | Exists in project; fall back to JSON key in GitHub secret if not | Day 1 end (when deploy.yml is finalized) |
| 9 | **Firebase test token source for E2E** | Minted via `firebase-admin` in a one-time script; stored as GitHub secret `FIREBASE_TEST_TOKEN` | Day 1 for local tests, Day 2 for CI |
| 10 | **Sprint 4 `/api/triage/stream` endpoint is complete** | Assumed complete by start of Sprint 5 | **HARD GATE** — Sprint 5 cannot start otherwise |
| 11 | **Node version** | 20 LTS | Day 2 morning |
| 12 | **pnpm version** | 9.x | Day 2 morning |
| 13 | **Cloud Run runtime service account exists** | `supply-chain-triage-runtime@<project>.iam.gserviceaccount.com` with `secretmanager.secretAccessor` on all three secrets | Day 1 pre-flight |
| 14 | **Firebase Hosting uses default site** (no custom domain) | Yes | Day 2 |
| 15 | **`adk web` remains the local dev UI** during Sprint 5 (frontend is for prod demo) | Yes | N/A |

**If any of 1-14 resolves differently, update this PRD inline before continuing execution. Assumption 10 is a hard gate — do not start Sprint 5 until Sprint 4 is complete.**
