---
title: "Sprint 5 Test Plan — Cloud Run Deployment + React Frontend"
type: deep-dive
domains: [supply-chain, hackathon, testing, deployment, frontend]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]", "[[Supply-Chain-Deployment-Options-Research]]"]
---

# Sprint 5 Test Plan — Deployment & Frontend

> **Scope:** Every acceptance criterion in Sprint 5 PRD §4 has at least one test case here. Tests are tagged by layer (Unit, Integration, E2E-live, Manual) and by acceptance criterion number (AC1-AC16).

## Legend

- **Layer**: `U` = Unit (local, mocked), `I` = Integration (local, real deps via emulator), `E` = E2E against LIVE deployed URLs, `M` = Manual (browser / CLI)
- **Gate**: `hard` = must pass to close sprint, `soft` = must document if failed
- **AC**: maps to Sprint 5 PRD §4 acceptance criterion number

---

## 1. Backend — Unit Tests (pytest)

### TC-B1 — `/healthz` returns 200 with service metadata
- **Layer**: U | **Gate**: hard | **AC**: 2
- **File**: `tests/unit/test_healthz.py::test_healthz_ok`
- **Given**: the FastAPI app is imported in a TestClient
- **When**: `client.get("/healthz")`
- **Then**: status_code == 200
- **And**: body has keys `status`, `revision`, `service`
- **And**: `body["status"] == "ok"`
- **Test data**: n/a
- **Expected failure mode before impl**: 404 (endpoint doesn't exist in Sprint 4 code)

### TC-B2 — `/readyz` returns 200 when Firebase Admin is ready
- **Layer**: U | **Gate**: hard | **AC**: 3
- **File**: `tests/unit/test_healthz.py::test_readyz_ready`
- **Given**: `_firebase_ready = True` (monkeypatched)
- **When**: `client.get("/readyz")`
- **Then**: 200 with `{"status": "ready"}`

### TC-B2b — `/readyz` returns 503 when Firebase Admin is NOT ready
- **Layer**: U | **Gate**: hard | **AC**: 3
- **File**: `tests/unit/test_healthz.py::test_readyz_not_ready`
- **Given**: `_firebase_ready = False` (monkeypatched)
- **When**: `client.get("/readyz")`
- **Then**: 503 with reason string containing "not initialized"

### TC-B3 — CORS allowlist is a single origin
- **Layer**: U | **Gate**: hard | **AC**: 14
- **File**: `tests/unit/middleware/test_cors_lockdown.py::test_single_origin_enforced`
- **Given**: `FRONTEND_ORIGIN=https://nimblefreight-hack.web.app`
- **When**: the FastAPI app is built
- **Then**: the CORSMiddleware `allow_origins` list has length 1
- **And**: that single entry == `https://nimblefreight-hack.web.app`
- **And**: `allow_origins` never contains `"*"` or a regex

### TC-B3b — CORS rejects evil origin at request level
- **Layer**: U | **Gate**: hard | **AC**: 14
- **File**: `tests/unit/middleware/test_cors_lockdown.py::test_evil_origin_rejected`
- **Given**: the configured allowlist is `https://nimblefreight-hack.web.app`
- **When**: `client.options("/api/triage/stream", headers={"Origin": "https://evil.example.com", "Access-Control-Request-Method": "POST"})`
- **Then**: response `Access-Control-Allow-Origin` header != `https://evil.example.com`
- **And**: header != `"*"`

### TC-B4 — Non-dev env refuses plain-http FRONTEND_ORIGIN
- **Layer**: U | **Gate**: hard | **AC**: 14
- **File**: `tests/unit/test_main_startup.py::test_prod_requires_https_origin`
- **Given**: `ENV=prod`, `FRONTEND_ORIGIN=http://insecure.example.com` (http, not https)
- **When**: `Settings()` is instantiated and `main.py` is imported
- **Then**: `RuntimeError` is raised at import time with message containing "https"

### TC-B5 — Unauth POST /api/triage/stream returns 401
- **Layer**: U | **Gate**: hard | **AC**: 13
- **File**: `tests/unit/test_auth_gate.py::test_triage_stream_requires_auth`
- **Given**: no `Authorization` header
- **When**: `client.post("/api/triage/stream", json=NH48_BODY)`
- **Then**: status_code == 401
- **And**: body contains error code or message indicating auth required

### TC-B6 — Authenticated /api/triage/stream emits ordered events
- **Layer**: I | **Gate**: hard | **AC**: 7, 11
- **File**: `tests/integration/test_triage_stream_integration.py::test_nh48_ordered_events`
- **Given**: a valid Firebase test token, Classifier + Impact agents mocked to deterministic responses
- **When**: `client.post("/api/triage/stream", json=NH48_BODY, headers={"Authorization": f"Bearer {TOKEN}"})`
- **Then**: response `Content-Type` starts with `text/event-stream`
- **And**: events collected arrive in order: `classifier_start`, `classifier_done`, `impact_start`, `impact_done`, `final`
- **And**: total wall-clock < 3s (with mocked agents)

### TC-B7 — `K_REVISION` env var surfaces in /healthz response
- **Layer**: U | **Gate**: soft | **AC**: 2
- **File**: `tests/unit/test_healthz.py::test_healthz_exposes_revision`
- **Given**: `K_REVISION=supply-chain-triage-00042-abc`
- **When**: `client.get("/healthz")`
- **Then**: body `revision` == that value

---

## 2. Deployment Scripts — Integration Tests

### TC-D1 — `deploy_backend.sh` fails gracefully when no gcloud auth
- **Layer**: I | **Gate**: soft | **AC**: 1
- **File**: `tests/integration/scripts/test_deploy_backend_preflight.sh`
- **Given**: `gcloud auth revoke --all` (test isolation)
- **When**: `./scripts/deploy_backend.sh` invoked
- **Then**: exit code non-zero
- **And**: stderr contains "no active gcloud account"

### TC-D2 — `deploy_backend.sh` fails gracefully when secret missing
- **Layer**: I | **Gate**: soft | **AC**: 15
- **File**: `tests/integration/scripts/test_deploy_backend_preflight.sh`
- **Given**: the secret `gemini-api-key` is intentionally deleted from a test GCP project
- **When**: `./scripts/deploy_backend.sh` invoked
- **Then**: exit code non-zero
- **And**: stderr contains "Secret 'gemini-api-key' not found"

### TC-D3 — `deploy_backend.sh` is idempotent
- **Layer**: E | **Gate**: hard | **AC**: 1
- **Manual + script**: run `./scripts/deploy_backend.sh` twice in a row; second run should succeed (Cloud Run updates the revision, does not error)
- **Then**: `gcloud run revisions list` shows both revisions

### TC-D4 — `deploy_frontend.sh` fails when dist/ missing
- **Layer**: I | **Gate**: soft | **AC**: 8
- **Given**: `rm -rf frontend/dist`, build step mocked to no-op
- **When**: the script runs the post-build dist-exists check
- **Then**: exits with error "dist not found"

---

## 3. Frontend — Unit Tests (vitest)

### TC-F1 — `LoginPage` renders sign-in button when unauthed
- **Layer**: U | **Gate**: hard | **AC**: 10
- **File**: `frontend/src/pages/LoginPage.test.tsx`
- **Given**: `useAuth()` returns `{ user: null, loading: false }` via mock
- **When**: `render(<App />)` in `MemoryRouter`
- **Then**: `screen.getByRole("button", { name: /sign in with google/i })` is truthy

### TC-F2 — `TriagePage` renders when authed
- **Layer**: U | **Gate**: hard | **AC**: 10
- **File**: `frontend/src/pages/TriagePage.test.tsx`
- **Given**: `useAuth()` returns `{ user: mockUser, loading: false }`
- **When**: `render(<App />)`
- **Then**: elements for `ExceptionInput`, `AgentStream`, `SummaryBanner` are all present

### TC-F3 — `useTriageSSE` parses two SSE frames
- **Layer**: U | **Gate**: hard | **AC**: 11
- **File**: `frontend/src/hooks/useTriageSSE.test.ts`
- **Given**: `globalThis.fetch` mocked to return a Response whose body is a ReadableStream yielding:
  ```
  event: classifier_done
  data: {"type":"classifier_done","payload":{"x":1}}

  event: final
  data: {"type":"final","payload":{"ok":true}}

  ```
- **When**: hook is invoked with a test `ExceptionEvent` via `start()`
- **Then**: after stream ends, `result.current.events.length === 2`
- **And**: `events[0].type === "classifier_done"`, `events[1].type === "final"`
- **And**: `result.current.state === "done"`

### TC-F4 — `useTriageSSE` reconnects on transient error
- **Layer**: U | **Gate**: hard | **AC**: 12
- **File**: `frontend/src/hooks/useTriageSSE.test.ts::reconnects_on_drop`
- **Given**: `fetch` throws `TypeError("network")` on first call, returns a valid 1-frame stream on second
- **When**: hook is invoked with `start(event)`, time is advanced with `vi.useFakeTimers()` past 1.5s
- **Then**: states pass through `connecting → error → reconnecting → connecting → streaming → done`
- **And**: final `events.length === 1`
- **And**: `retries` counter is 1

### TC-F4b — `useTriageSSE` surfaces error after 5 failed retries
- **Layer**: U | **Gate**: hard | **AC**: 12
- **File**: `frontend/src/hooks/useTriageSSE.test.ts::gives_up_after_five_retries`
- **Given**: `fetch` always throws
- **When**: hook is invoked and timers are advanced past each backoff delay
- **Then**: after the 5th retry, `state === "error"` and `error` is a non-empty string
- **And**: no further `fetch` calls are made

### TC-F5 — `ExceptionInput` validates non-empty narrative
- **Layer**: U | **Gate**: hard | **AC**: 10
- **File**: `frontend/src/components/ExceptionInput.test.tsx`
- **Given**: empty narrative textarea
- **When**: user clicks the submit button
- **Then**: the `onSubmit` prop is NOT called
- **And**: an element with `role="alert"` appears containing "narrative"

### TC-F6 — `fetchWithAuth` attaches Bearer token
- **Layer**: U | **Gate**: hard | **AC**: 11
- **File**: `frontend/src/lib/api.test.ts::fetchWithAuth_attaches_token`
- **Given**: `getAuth().currentUser.getIdToken` returns `"fake-token"` via mock
- **When**: `await fetchWithAuth("/triage/stream", { method: "POST", body: "{}" })`
- **Then**: the `fetch` spy was called with `Authorization: Bearer fake-token` header
- **And**: `Content-Type: application/json`

### TC-F7 — `fetchWithAuth` throws when not authenticated
- **Layer**: U | **Gate**: hard | **AC**: 13
- **File**: `frontend/src/lib/api.test.ts::fetchWithAuth_throws_when_unauthed`
- **Given**: `getAuth().currentUser === null`
- **When**: `await fetchWithAuth("/triage/stream")`
- **Then**: Promise rejects with Error("Not authenticated")

### TC-F8 — `streamTriage` handles malformed SSE frame gracefully
- **Layer**: U | **Gate**: soft | **AC**: 11
- **File**: `frontend/src/lib/api.test.ts::streamTriage_skips_malformed_frame`
- **Given**: a stream with one malformed JSON frame followed by one valid frame
- **When**: hook processes the stream
- **Then**: only the valid frame triggers `onEvent`; no throw

---

## 4. E2E Tests Against LIVE URLs (pytest)

> Require env vars `LIVE_BACKEND_URL`, `LIVE_FRONTEND_URL`, `FIREBASE_TEST_TOKEN`. Skipped cleanly when not set.

### TC-E1 — Live `/healthz` returns 200
- **Layer**: E | **Gate**: hard | **AC**: 2
- **File**: `tests/e2e/test_live_deployment.py::test_backend_healthz_returns_200`
- **When**: `httpx.get(f"{LIVE_BACKEND_URL}/healthz")`
- **Then**: status 200, body has `status: "ok"`, `revision` present

### TC-E2 — Live `/readyz` returns 200
- **Layer**: E | **Gate**: hard | **AC**: 3
- **File**: `tests/e2e/test_live_deployment.py::test_backend_readyz_returns_200`

### TC-E3 — Firebase Hosting serves index.html
- **Layer**: E | **Gate**: hard | **AC**: 9, 10
- **File**: `tests/e2e/test_live_deployment.py::test_frontend_hosting_serves_index_html`
- **Then**: response contains `id="root"` marker and status 200

### TC-E4 — Firebase Hosting `/api/**` rewrite reaches Cloud Run
- **Layer**: E | **Gate**: hard | **AC**: 9
- **File**: `tests/e2e/test_live_deployment.py::test_frontend_api_proxy_reaches_cloud_run`
- **When**: `httpx.get(f"{LIVE_FRONTEND_URL}/api/healthz")`
- **Then**: status 200 (proves reverse-proxy works)

### TC-E5 — Unauth /api/triage/stream returns 401
- **Layer**: E | **Gate**: hard | **AC**: 13
- **File**: `tests/e2e/test_live_deployment.py::test_unauth_triage_stream_is_401`

### TC-E6 — NH-48 end-to-end on live URL < 10s
- **Layer**: E | **Gate**: hard | **AC**: 7
- **File**: `tests/e2e/test_live_deployment.py::test_triage_stream_end_to_end_nh48`
- **Given**: valid `FIREBASE_TEST_TOKEN`
- **When**: `httpx.stream("POST", ...)` with NH-48 body
- **Then**: elapsed < 10s
- **And**: events include `classifier_done`, `impact_done`, `final`

### TC-E7 — CORS blocks evil origin on live URL
- **Layer**: E | **Gate**: hard | **AC**: 14
- **File**: `tests/e2e/test_live_deployment.py::test_cors_blocks_evil_origin`

### TC-E8 — Warm latency ≤ 3s (10 samples)
- **Layer**: E | **Gate**: soft | **AC**: 5
- **Script**: `scripts/measure_warm_latency.sh $LIVE_BACKEND_URL`
- **When**: 10 sequential `curl -o /dev/null -s -w "%{time_total}\n" $URL/healthz`
- **Then**: p50 ≤ 3.0s

### TC-E9 — Cold-from-zero latency ≤ 8s (scale-from-zero scenario)
- **Layer**: E | **Gate**: soft | **AC**: 6
- **Precondition**: temporarily set `min_instances=0`, wait 15 min, send a single request
- **Then**: elapsed ≤ 8s
- **Cleanup**: restore `min_instances=1`
- **Note**: this test damages demo readiness; run once at end of Sprint 5 and only if time permits

### TC-E10 — Cloud Run service config verification
- **Layer**: E | **Gate**: hard | **AC**: 4, 15
- **Script**: `tests/e2e/test_cloudrun_config.sh`
- **When**: `gcloud run services describe supply-chain-triage --region asia-south1 --format=json`
- **Then**: `.spec.template.metadata.annotations["autoscaling.knative.dev/minScale"] == "1"`
- **And**: each of the 3 secrets appears in `.spec.template.spec.containers[0].env[].valueFrom.secretKeyRef` (not `.value`)

---

## 5. Manual / Browser Tests

### TC-M1 — Google Sign-In popup flow
- **Layer**: M | **Gate**: hard | **AC**: 10
- **Steps**:
  1. Open `https://nimblefreight-hack.web.app` in Chrome Incognito
  2. Click "Sign in with Google"
  3. Choose a test account
- **Expected**: popup closes, `TriagePage` renders, `SummaryBanner` shows user email

### TC-M2 — NH-48 triage live in browser
- **Layer**: M | **Gate**: hard | **AC**: 7, 11
- **Steps**:
  1. On `TriagePage`, paste NH-48 narrative into `ExceptionInput`
  2. Click Submit
  3. Watch `AgentStream`
- **Expected**:
  - First event appears < 2s after submit
  - ≥ 4 events stream in (classifier_start/done, impact_done, final)
  - `ClassificationCard` renders with non-empty exception_type and severity
  - `ImpactCard` renders with at least one affected shipment
  - Total elapsed (submit → final) < 8s

### TC-M3 — Mid-stream disconnect + reconnect
- **Layer**: M | **Gate**: soft | **AC**: 12
- **Steps**:
  1. Start NH-48 triage
  2. In DevTools Network tab, throttle to "Offline" for 3 seconds after first event
  3. Un-throttle
- **Expected**: UI shows `state="reconnecting"`, then resumes streaming, then `state="done"`

### TC-M4 — Sign-out clears state
- **Layer**: M | **Gate**: hard | **AC**: 10
- **Steps**: Click sign-out in `SummaryBanner`
- **Expected**: redirected to `LoginPage`; any in-flight stream is aborted

### TC-M5 — DevTools: confirm no secrets in bundle
- **Layer**: M | **Gate**: hard | **AC**: 15
- **Steps**:
  1. Open `view-source:https://nimblefreight-hack.web.app/assets/*.js`
  2. Search for `gemini`, `supermemory`, `sk-`, `AIza` (generic API-key prefixes)
- **Expected**: only `VITE_FIREBASE_API_KEY` matches (which is public by design); no Gemini or Supermemory keys present

### TC-M6 — Lighthouse Performance ≥ 80
- **Layer**: M | **Gate**: soft | **AC**: n/a (metric only)
- **Command**: `pnpm dlx lighthouse $HOSTING_URL --only-categories=performance --quiet --chrome-flags="--headless"`
- **Expected**: Performance score ≥ 80

---

## 6. CI/CD Tests

### TC-CI1 — Workflow triggers on push to main
- **Layer**: M | **Gate**: hard | **AC**: 1, 8
- **Steps**: create a commit touching `src/supply_chain_triage/main.py`, push to main
- **Expected**: `deploy.yml` runs within 60s; all three jobs (deploy-backend, deploy-frontend, e2e-smoke) succeed

### TC-CI2 — Workflow uses WIF (not JSON keys)
- **Layer**: M | **Gate**: soft | **AC**: n/a (security hygiene)
- **Steps**: inspect `.github/workflows/deploy.yml`
- **Expected**: `workload_identity_provider` present, no `credentials_json` input, no `GOOGLE_APPLICATION_CREDENTIALS` env set from a GitHub secret

### TC-CI3 — e2e-smoke job catches a broken deploy
- **Layer**: M | **Gate**: soft
- **Steps**: deliberately break `/healthz` in a PR (return 500)
- **Expected**: `e2e-smoke` job fails; PR cannot be merged (if branch protection enforced)

---

## 7. Fresh-Clone Acceptance Test

### TC-FC1 — Fresh clone to live URL in < 15 min
- **Layer**: M | **Gate**: hard | **AC**: 16
- **Steps** (wall-clock timed):
  1. `git clone <repo> fresh-clone && cd fresh-clone`
  2. `cp .env.template .env` + fill values
  3. `gcloud auth login` + `gcloud config set project <project>`
  4. `firebase login`
  5. `make deploy`
  6. Open the printed Hosting URL in browser
  7. Sign in + run NH-48
- **Expected**: Wall-clock from step 1 to successful NH-48 render ≤ 15 min

---

## 8. Test Execution Order

1. **TDD loop (Day 1 morning)**: TC-B1, TC-B2, TC-B2b, TC-B3, TC-B3b, TC-B4, TC-B5 → all RED first, then GREEN
2. **After first backend deploy (Day 1 afternoon)**: TC-E1, TC-E2, TC-E5, TC-E6, TC-E10
3. **TDD loop (Day 2 morning)**: TC-F3, TC-F4, TC-F4b, TC-F6, TC-F7 → RED then GREEN
4. **After frontend builds (Day 2 midday)**: TC-F1, TC-F2, TC-F5, TC-F8
5. **After frontend deploy (Day 2 afternoon)**: TC-E3, TC-E4, TC-E7, TC-E8
6. **Manual browser pass (Day 2 afternoon)**: TC-M1 through TC-M6
7. **CI verification (Day 2 end)**: TC-CI1
8. **Sprint close**: TC-FC1 (if time permits; otherwise Sprint 6 Day 1)

## 9. Coverage Matrix (AC → Test)

| AC | Tests |
|----|-------|
| 1  | TC-D3, TC-CI1 |
| 2  | TC-B1, TC-B7, TC-E1 |
| 3  | TC-B2, TC-B2b, TC-E2 |
| 4  | TC-E10 |
| 5  | TC-E8 |
| 6  | TC-E9 |
| 7  | TC-B6, TC-E6, TC-M2 |
| 8  | TC-D4 |
| 9  | TC-E3, TC-E4 |
| 10 | TC-F1, TC-F2, TC-F5, TC-M1, TC-M4 |
| 11 | TC-B6, TC-F3, TC-F6, TC-F8, TC-M2 |
| 12 | TC-F4, TC-F4b, TC-M3 |
| 13 | TC-B5, TC-F7, TC-E5 |
| 14 | TC-B3, TC-B3b, TC-B4, TC-E7 |
| 15 | TC-D2, TC-E10, TC-M5 |
| 16 | TC-FC1 |

Every acceptance criterion has at least one hard-gate test.

## Cross-References

- `prd.md` — Sprint 5 PRD with acceptance criteria and code snippets
- `risks.md` — pre-mortem risk analysis (what we test against)
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — sprint workflow and gate philosophy
