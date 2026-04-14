---
title: "Sprint 5 Risks & Pre-mortem — Deployment & Frontend"
type: deep-dive
domains: [supply-chain, hackathon, risk-management, deployment, frontend]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]", "[[Supply-Chain-Deployment-Options-Research]]"]
---

# Sprint 5 Risks & Pre-mortem — Cloud Run Deployment + React Frontend

> **Purpose:** Assume Sprint 5 failed. Work backward from the failure to identify what went wrong. This is a Gary Klein pre-mortem, not a retrospective.
>
> **Sprint window:** Apr 20-21, 2026 (2 days). **Demo deadline:** Apr 24. **If Sprint 5 fails, there are only 2 days of buffer before submission.**

## TL;DR — Top 3 Risks

1. **React frontend blows the 1-day budget** (Probability: High, Severity: Medium) → Tier-2 rollback to `adk web` iframe
2. **Cold start exceeds 8-second demo budget** (P: Medium, S: High) → `min_instances=1` + pre-warm
3. **EventSource + auth header incompatibility surprises us mid-Day-2** (P: Medium — already known, S: Medium) → `fetch` + `ReadableStream` path already in PRD §12.E/F

---

## Pre-mortem Exercise

**Frame:** It's Apr 22 morning. Sprint 5 formally failed. We have no working live URL. What happened?

### Failure narrative 1 — "The React hole"
> Day 2 started with React scaffolding. By noon we were still debugging Firebase Auth popup issues. By 3pm the SSE hook was throwing "ReadableStream already locked" on reconnect. By 6pm the components looked right but the data didn't flow. By 9pm we gave up and decided to ship `adk web`, but we hadn't actually tested embedding it in Firebase Hosting. Apr 22 morning we're still in the weeds.

**Root causes:**
- Underestimated React setup time (scaffold, auth, hooks, components, styles, routing = many small friction points)
- No React-experience baseline in the team for this codebase
- Tried to match wireframe CSS pixel-perfect instead of "close enough"
- Didn't run the rollback drill on Day 1

**Preventive controls:**
- **R4 mitigation** (PRD §10): Strict component count (6), no form libraries, no react-query, no redux
- Noon checkpoint on Day 2: if NH-48 doesn't render locally by 12:00, cut to Tier-2
- Pre-write the `adk web` iframe fallback HTML on Day 1 so Tier-2 is a one-file swap
- Time-box each component to 15 min; if stuck, drop styling and move on

### Failure narrative 2 — "The cold-start wall"
> Cloud Run deployed fine on Day 1. We verified `/healthz`. We verified NH-48 worked. We moved on to frontend on Day 2. Demo day, judges clicked the URL. First response took 19 seconds (ADK cold start) because `min_instances=0` somehow. Judges scored us a 4/10 on "responsiveness." We didn't catch it because we tested on a warm instance.

**Root causes:**
- `min_instances` not asserted in the deploy script or verified in E2E test
- Demo was warmed up by the team's own testing; judges hit a cold path
- No monitoring/alerting on cold starts

**Preventive controls:**
- **AC4** (PRD §4): Assert `min_instances=1` via `gcloud run services describe`
- **TC-E10** (test-plan.md): E2E test that reads the service config and asserts minScale == "1"
- **Pre-warm protocol** (PRD §10 R1): Send 3 dummy requests 2 min before any demo session
- Bump `min_instances=2` the night before the demo video recording; revert after

### Failure narrative 3 — "The auth-header ambush"
> Day 2 afternoon, we finished the SSE hook using native `EventSource`. It "worked" locally because our middleware was lenient. In prod, every request 401'd because `EventSource` cannot attach the `Authorization` header. We had to rewrite the hook at 6pm using `fetch` + `ReadableStream`. That rewrite introduced a buffering bug. We shipped a broken frontend.

**Root causes:**
- Didn't research SSE client constraints before writing the hook
- Local dev was too permissive and hid the auth gap

**Preventive controls:**
- **Already mitigated in PRD**: §12.E and §12.F use `fetch` + `ReadableStream` from the start; the word "EventSource" appears in the code only as a comment explaining why we don't use it
- **Research §15** documents the finding authoritatively so future engineers don't reintroduce the bug

### Failure narrative 4 — "The CORS maze"
> We set `FRONTEND_ORIGIN=https://nimblefreight-hack.web.app` in the deploy script. Browser still complained "CORS error". Turned out `allow_origins` needed an exact string match including trailing slash rules, and the preflight OPTIONS request was hitting auth middleware which 401'd it before CORS could reply. We spent Day 2 evening debugging middleware order.

**Root causes:**
- Middleware execution order not documented
- Auth middleware didn't exempt OPTIONS
- No unit test for the CORS preflight path

**Preventive controls:**
- **Primary mitigation**: Use Firebase Hosting `/api/**` rewrite as the main path. Same-origin = zero CORS. (PRD §2.6)
- CORS allowlist only for dev and direct-to-Cloud-Run access
- **TC-B3b** (test-plan.md): explicit preflight test from evil origin
- Middleware order: `rate_limit → audit → sanitization → firebase_auth` (last-added runs first). Auth middleware skips OPTIONS preflight (already in Sprint 0's middleware code).

### Failure narrative 5 — "The secret that wasn't"
> We deployed, `/healthz` returned 200, but `/api/triage/stream` 500'd with "GEMINI_API_KEY not set". Turned out the Cloud Run runtime service account didn't have `secretmanager.secretAccessor` and the `--set-secrets` flag silently succeeded at bind time but the env var was empty at runtime.

**Root causes:**
- SA IAM bindings not verified in pre-flight
- No test that secrets actually resolve at runtime (TC-B1 only tests healthz, not a secret-consuming path)

**Preventive controls:**
- **Pre-flight in `deploy_backend.sh`** (PRD §12.B): check each secret exists via `gcloud secrets describe`
- **Follow-up**: add IAM binding check to pre-flight: `gcloud secrets get-iam-policy gemini-api-key | grep $RUNTIME_SA`
- **TC-E10** (test-plan): verify secrets appear in `containers[0].env[].valueFrom.secretKeyRef`
- **TC-E6**: the live NH-48 test actually invokes Gemini — failure here surfaces missing secrets

### Failure narrative 6 — "The WIF quicksand"
> `.github/workflows/deploy.yml` wouldn't auth. Workload Identity Federation needed a pool, provider, and SA-binding we didn't have. Spent 4 hours on GCP IAM docs on Day 1. Never got CI deploy working; resorted to local `./scripts/deploy_backend.sh` for the demo. No rollback safety net.

**Root causes:**
- WIF is new and has many moving parts
- No familiarity baseline
- Treated CI as a hard requirement instead of a nice-to-have

**Preventive controls:**
- **PRD §10 R7**: explicit fallback to JSON key in GitHub secret; document as post-hackathon tech debt
- Time-box WIF debugging to 1 hour on Day 1; if not working, fall back immediately
- Manual deploy via `scripts/deploy_*.sh` is the primary path; CI is the nice-to-have

### Failure narrative 7 — "The Firebase CLI pit"
> Day 2 afternoon, ran `firebase deploy --only hosting`. It asked for an interactive confirmation about "Auto-init Functions". Pressed wrong key. Overwrote the Hosting rewrite config. Frontend deployed but `/api/**` no longer routed to Cloud Run. Had to manually fix `firebase.json` and re-deploy.

**Root causes:**
- Firebase CLI interactive prompts in a supposedly automated script
- No confirmation disabling

**Preventive controls:**
- Use `firebase deploy --only hosting --project $PROJECT --non-interactive` (add `--non-interactive` or equivalent env var)
- Check in `firebase.json` and `.firebaserc` to the repo so there's nothing to auto-init
- Test the deploy script on a clean machine once before the real run

---

## Risk Register

| # | Risk | P | S | Owner | Mitigation | Fallback | AC Impact |
|---|------|---|---|-------|-----------|----------|-----------|
| R1 | Cold start exceeds 8s demo budget | M | H | Dev | `min_instances=1`, pre-warm, startup-cpu-boost, Gunicorn `--preload` if needed | Bump to `min_instances=2` for demo day | AC5, AC6, AC7 |
| R2 | CORS misconfig blocks frontend | M | H | Dev | Primary: Firebase Hosting `/api/**` rewrite (same-origin). Secondary: single-origin allowlist | Wildcard regex allowlist temporarily | AC14 |
| R3 | Cloud Run quota / billing exceeded | L | M | Dev | `max_instances=10`, billing alert at $20, rate limit at app layer | Reduce max_instances; pause service | AC1 |
| R4 | React scope creep (noon checkpoint) | **H** | M | Dev | Strict component list (6), no libs, wireframe CSS verbatim, noon Day-2 checkpoint | Tier-2: `adk web` in iframe on single HTML page | AC10, AC11 |
| R5 | EventSource + auth header incompat | M (known) | M | Dev | `fetch` + `ReadableStream` from the start; comment in code explaining why | Query-param token (insecure last resort) | AC11, AC13 |
| R6 | Firebase Hosting rewrite latency | L | L | Dev | Accept ~100-200ms; `pinTag: true` prevents drift | n/a | AC7 |
| R7 | WIF setup fails | M | L | Dev | Fall back to JSON key in GitHub secret | Manual deploy via script only | AC1 (CI path) |
| R8 | Source-based deploy slower than expected | M | L | Dev | Expect 3-5 min; use Cloud Build layer caching | Pre-build image with Dockerfile post-hackathon | AC1 |
| R9 | Secret Manager IAM missing | L | H | Dev | Pre-flight check, runtime SA has `secretAccessor`, TC-E10 verifies at runtime | Manual IAM binding | AC15 |
| R10 | Firebase CLI interactive prompts | L | M | Dev | `--non-interactive` flag; commit `firebase.json` + `.firebaserc` | Manual fix + re-deploy | AC8, AC9 |
| R11 | Firebase test token generation unclear | M | M | Dev | One-time script using Firebase Admin SDK; store in GitHub secret | Skip E2E auth tests in CI, run manually | AC16 |
| R12 | `min_instances=1` billing unnoticed | L | L | Dev | Billing alert + monthly cost metric in PRD §11 | Revert to `min_instances=0` post-demo | AC16 |
| R13 | Mumbai region latency to test accounts in other regions | L | L | Dev | Mumbai is correct for target market; test users are in India | n/a | AC7 |
| R14 | Sprint 4 endpoint not complete at start | L (hard gate) | **Blocker** | Dev | Sprint 5 cannot start until `/api/triage/stream` works locally | Trim Sprint 4 scope, enter Sprint 5 late | All |
| R15 | Browser CSP blocks Firebase auth domain | L | M | Dev | CSP `connect-src` includes `https://*.googleapis.com` and `https://*.firebaseio.com` | Relax CSP temporarily | AC10 |

### Probability legend
- **H** (High): >50% chance given historical base rates
- **M** (Medium): 20-50%
- **L** (Low): <20%

### Severity legend
- **H** (High): blocks AC directly, threatens demo
- **M** (Medium): causes rework or scope cut
- **L** (Low): annoyance, time cost only
- **Blocker**: cannot proceed without resolving

---

## Go/No-Go Decision Rules

**Go for Day 2 React work** if and only if at end of Day 1:
- ✅ Backend deployed to Cloud Run with live URL
- ✅ `/healthz` + `/readyz` returning 200
- ✅ Authenticated NH-48 E2E passing in `< 8s` via curl
- ✅ `min_instances=1` verified

If any of these is missing, extend Day 1 (possibly sacrificing React polish, never the backend deploy).

**Noon Day-2 go/no-go for full React UI**:
- ✅ Vite app scaffolds and `pnpm dev` works
- ✅ Firebase Auth sign-in flow works locally
- ✅ `useTriageSSE` streams at least one event from local backend
- If any ✗ → downgrade to Tier-2 (adk-web iframe) immediately

**End-of-Day-2 go/no-go for sprint close**:
- ✅ 16/16 acceptance criteria green (or explicitly documented waivers in retro.md)
- ✅ Live URL documented in README
- ✅ ADR-016 and ADR-017 written
- If AC count < 16 → sprint extends into Apr 22, cutting into buffer

---

## Contingency Reserves

- **Time reserve**: 2 days (Apr 22-23) exist between Sprint 5 close and Apr 24 submission. This buffer is the absolute last resort; Sprint 6 (Submission) uses Apr 22-23 per the sprint plan.
- **Budget reserve**: `$20` GCP billing budget accepts a 2x overrun of normal `min_instances=1` cost without alarm.
- **Scope reserve**: Tier-2 rollback (adk-web iframe) cuts React UI work to ~1 hour; Tier-3 (ngrok from laptop) cuts Cloud Run work entirely; Tier-4 (recorded video only) is total rollback to "submit what we have locally."
- **People reserve**: None. Solo dev. This is the critical constraint.

---

## Learning Hooks

After Sprint 5 close, update these files based on what actually happened:

- `docs/sprints/sprint-5/retro.md` — Start/Stop/Continue
- `docs/decisions/adr-016-deployment-target-finalized.md` — note any surprises in Cloud Run behavior vs. expected
- [[Supply-Chain-Deployment-Options-Research]] — append a "Sprint 5 execution notes" section with lessons learned for future deployment decisions
- `wiki/infrastructure/cloud-run.md` — create this wiki page with the finalized deployment recipe (per LLM Wiki conventions)
- `wiki/patterns/sse-auth-in-react.md` — create wiki page capturing the EventSource-vs-fetch finding so this doesn't get rediscovered

## Cross-References

- `prd.md` — Sprint 5 PRD with acceptance criteria, code, risks section (PRD §10 is a summary; this doc is the deep-dive)
- `test-plan.md` — test cases that verify each risk's mitigations
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — pre-mortem workflow for Risk phase
- [[Supply-Chain-Deployment-Options-Research]] — 4-option analysis informing Option B choice

---

**Pre-mortem philosophy** (per superpowers:pre-mortem-analysis): we are deliberately pessimistic here. Every "Go" decision elsewhere assumes things work. This document assumes they don't, and plans accordingly. If the actual Sprint 5 retrospective identifies a failure mode not on this list, update this document for the next deployment sprint.
