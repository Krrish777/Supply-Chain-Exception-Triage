---
title: "2026-04-18 — Research session: Tier 1 closeout decisions"
type: session-notes
last_updated: 2026-04-18
status: active
---

# 2026-04-18 — Research session: Tier 1 closeout decisions

> **Session type:** Research-only (explicit user directive: no building in this session).
> **Deliverables produced:** This doc (decision record) + 7 research docs in `docs/research/` + updated Sprint 3 PRD + next-session handoff.
> **Deadline context:** Tier 1 prototype due **2026-04-28** (updated from 2026-04-24; 10 days runway).
> **Next session:** Execute as a single trimmed sprint per all decisions below.

---

## 1. Progress snapshot (what's already built + committed)

| Layer | Status | Notes |
|---|---|---|
| Sprint 0 — Infra | ✅ Done | Rules, hooks, CI, middleware, models, hello_world |
| Sprint 1 — Classifier | ✅ Done + live-verified | SequentialAgent(fetcher+formatter), 2 tools, 6 exception types, severity clamps, 24 unit tests |
| Sprint 2 — Impact | ✅ Done (pytest only) | SequentialAgent(fetcher+formatter), 5 tools, 5-factor priority scoring, 22 shipments + 12 hubs + 4 routes + 7 customers + 2 tenants, 42 unit tests, `POST /api/v1/impact` |
| Cleanup pass | ✅ Done | Shared triage types, shared runner helper, silent-fallback removed from impact callback (commit e00cd23) |
| **Multi-provider LLM abstraction** | 🟡 Uncommitted | `core/llm.py` + Groq-via-LiteLLM support + config validators + `ResolvedLlmModel` + tests. 3 agents rewired through `get_resolved_llm_model()`. |

---

## 2. Scope & sequencing decisions

| # | Decision | Rationale |
|---|---|---|
| 2.1 | **Demo bar = `adk web` + Cloud Run URL** | Judges need a live URL. Cloud Run deploy Apr 26–27 with 1-day buffer. |
| 2.2 | **Dashboard UI is REQUIRED** (not `adk web`) | User: "adk web is for development and testing only; for production we have to create our own UI." Saved to memory as `feedback_demo_needs_real_ui.md`. UI framework TBD — user will disclose. |
| 2.3 | **Demo scenarios = 1 flagship + 2 backups, scripted** | NH-48 Ramesh Kumar Hinglish (flagship), FSSAI regulatory (backup), safety override (backup). All three deterministically seeded + rehearsed. |
| 2.4 | **Cloud Run deploy window = Apr 26–27** | 1-day buffer before Apr 28 submission. |
| 2.5 | **Session structure = one continuous build session**, single "Sprint 3 trimmed" | Avoid handoff overhead. |

---

## 3. Firestore / permanent DB decisions

| # | Decision |
|---|---|
| 3.1 | **Permanent collections:** `companies`, `users`, `customers`, `routes`, `hubs`. All carry `company_id`. |
| 3.2 | **Historical exceptions:** full archive with retention policy (90-day hot / N-year cold, details in research doc). |
| 3.3 | **Multi-tenancy:** tenant-prefixed doc IDs + strict Firestore rules comparing `request.auth.token.company_id` to `resource.data.company_id`. |
| 3.4 | **Company profile fields (expanded):** escalation matrix (per-severity contact list) + business-hour/holiday calendar + preferred language/communication style. SLA templates by customer tier kept optional for Tier 2. |
| 3.5 | **Stub seed files to populate in Tier 1:** `companies.json`, `users.json`, `festival_calendar.json`. `monsoon_regions.json` deferred with Rule D. |
| 3.6 | **Seed strategy:** consolidate into ONE idempotent `scripts/seed_all.py`. Kills the 4-script duplication. |
| 3.7 | **Triage-result persistence:** write `exceptions/{id}` (or `triage_results/{id}`) on every pipeline run — powers dashboard history tab + audit archive + Tier 2 Supermemory substrate. |
| 3.8 | **Open user question:** "Are we 100% utilizing Firestore?" → answered in the `firestore-utilization-audit-tier1.md` research doc. Headline: ~60–70% today; `routes`/`hubs` have no rule coverage, 4 stub seed files, missing composite indexes on `customers`/`routes`/`hubs`. |

---

## 4. Agent / orchestration decisions

| # | Decision |
|---|---|
| 4.1 | **Coordinator pattern = `SequentialAgent(classifier, impact)` + `before_agent_callback` on each** for rule-based short-circuit. No extra LLM hop. Deterministic. A2A-exposable (still an agent). |
| 4.2 | **Rules in scope for Tier 1: B, C, F.** Rules A/D/E (WhatsApp urgency, festival/monsoon context, D2C reputation) deferred to Tier 2 with Supermemory. |
| 4.3 | **Rule B (safety override) placement:** `before_agent_callback` on Classifier (first in sequence). Keyword short-circuit + LLM safety net inside Classifier prompt (defense in depth). |
| 4.4 | **Safety-keyword languages v1:** English + Hindi-transliterated. LLM fallback covers fuzzier Hinglish / regional phrasings. |
| 4.5 | **Rule C (regulatory auto-escalate):** Impact's `before_agent_callback` reads `triage:classification.exception_type == "regulatory_compliance"` → force-runs Impact even on LOW severity (overrides Rule F). |
| 4.6 | **Rule F (LOW severity skip Impact):** same callback — if LOW and not regulatory, return Content to skip. Final TriageResult has `impact=None, status="complete"`. |
| 4.7 | **Conflict resolution order:** B > C > F. |
| 4.8 | **State contract:** `triage:classification` + `triage:event` namespacing (current pattern). |
| 4.9 | **Memory layer / Supermemory / UserContextProvider:** deferred to Tier 2 (explicit user instruction: "first build + test the agent, then add memory layer on top"). |
| 4.10 | **AgentRunner framework-portability abstraction:** deferred post-Apr-28. |
| 4.11 | **Impact live-test in `adk web`:** Day 1 of next sprint (burn down the biggest unverified surface). |

---

## 5. Error handling + streaming decisions

| # | Decision |
|---|---|
| 5.1 | **Classifier low confidence (<0.7):** `requires_human_approval=True`; Impact still runs; summary says "needs coordinator review". |
| 5.2 | **Impact failure:** return partial `TriageResult` with Classification only; `status="partial"`. Single `tenacity`-wrapped retry on Impact before falling back. |
| 5.3 | **SSE event types:** `agent_started`, `agent_completed` (both with name + duration), `tool_invoked`, `partial_result`. Plus `complete` + `error` + `done` terminators. |
| 5.4 | **Token-stream events:** deferred to Tier 2 (JSON-mode + streaming can conflict). |

---

## 6. API + auth decisions

| # | Decision |
|---|---|
| 6.1 | **Tier 1 endpoints:** `POST /api/v1/triage` (SSE streaming, prod path), `GET /api/v1/exceptions` (paginated history for dashboard). `GET /api/v1/exceptions/{id}` optional if time permits. |
| 6.2 | **Existing `/api/v1/classify` and `/api/v1/impact`:** keep as debug-only routes; new `/api/v1/triage` is the production path. |
| 6.3 | **Auth for demo:** Google OAuth + auto-seed into `comp_nimblefreight` tenant. Judge clicks Sign in with Google → we set `company_id` custom claim via Admin SDK → judge is in. |
| 6.4 | **Triage-run persistence:** every run writes to Firestore (see 3.7). |
| 6.5 | **Rate limiting:** research-driven. Plan: slowapi per-IP 10/min on `/api/v1/triage` + `max_output_tokens` hard cap + Gemini quota budget alerts. Detail in `llm-quotas-rate-limits.md`. |

---

## 7. LLM provider + model strategy

| # | Decision |
|---|---|
| 7.1 | **Demo provider = Gemini everywhere.** Groq+output_schema via LiteLLM is broken (ADK emits `tool_choice="json_tool_call"` unsupported by Groq). Groq stays as dev-only toggle. |
| 7.2 | **Model for all 4 sub-agents = `gemini-2.5-flash`** (current committed). Re-evaluate via evalset scores; switch specific agent to Pro only on quality gap. |
| 7.3 | **Gemini access path — direct API vs Vertex AI:** user still undecided. Default for Tier 1 demo: direct Gemini API (simplest; current wiring); Vertex AI migration documented in research doc as a 2-hour follow-up that can happen before or after Apr 28. |
| 7.4 | **Commit uncommitted LLM work FIRST** in next session, before any Coordinator work. Clean baseline. |
| 7.5 | **Per-request token cap:** `max_output_tokens=2048` on formatters, 1024 on fetchers. Hard bound on runaway generation. |

---

## 8. GCP + Cloud Run decisions

| # | Decision |
|---|---|
| 8.1 | **GCP project split:** `sct-dev` (existing) for day-to-day + `sct-prod` (fresh, $300 credits) for demo. Optional `sct-staging`. |
| 8.2 | **Cloud Run region:** `asia-south1` (Mumbai). Matches India logistics story. |
| 8.3 | **Cold-start handling:** `min-instances=1` during 48h demo window. ~$15 cost for a judge-instant first click. |
| 8.4 | **Secrets:** Secret Manager mounted via `--set-secrets`. No baked JSON keys. |
| 8.5 | **Auth:** Workload Identity on Cloud Run service account. |
| 8.6 | **Observability:** Cloud Logging (structlog JSON, already wired) + Cloud Trace (OTel spans per agent + tool) + Cloud Monitoring budget alerts. BigQuery log sink deferred. |
| 8.7 | **Budget alerts:** $10 / $25 / $50 email alerts on `sct-prod`. |
| 8.8 | **Deferred to Tier 2+:** Agent Engine, GKE, BigQuery, Pub/Sub, Dataflow. |

---

## 9. Evalsets + quality

| # | Decision |
|---|---|
| 9.1 | **Classifier evalset:** 15 cases (6 happy + 4 edge + 3 safety + 2 adversarial). |
| 9.2 | **Impact evalset:** 10 cases (lighter — Impact is downstream of Classifier). |
| 9.3 | **Coordinator evalset:** NOT created (ADK bug #3434 — sub-agent trajectory scoring unreliable on Coordinators). Instead, pytest smoke-test that asserts right leaf invoked. |
| 9.4 | **Coverage gate:** stays advisory through Apr 28; flip to `--cov-fail-under=90` at Tier 2 boundary. |

---

## 10. Demo UX decisions

| # | Decision |
|---|---|
| 10.1 | **Judge input:** scenario picker + "paste your own" textarea. Best of both. |
| 10.2 | **Result panel emphasis:** agent reasoning trace + structured TriageResult card + before/after narrative. Raw JSON behind "details" toggle. |
| 10.3 | **Realtime feel:** stream pipeline progress via SSE. |
| 10.4 | **Rollback plan:** **live or nothing** — no video fallback, no mock-mode. Means we MUST nail rehearsals + min-instances=1 + healthy Gemini quota. |
| 10.5 | **Languages:** English + Hinglish input. Devnagari deferred. |
| 10.6 | **Landing page content:** defer to future research session (happens after agent work is stable). |
| 10.7 | **UI framework:** pending user disclosure. Research doc written framework-agnostically with React + plain HTML snippets. |

---

## 11. Hygiene items for day 1 of next sprint

1. Commit uncommitted LLM-provider work (`core/llm.py` + tests + config) as its own commit.
2. Fix pre-existing `test_classification.py` failure (dict vs `list[KeyFact]`) in a second commit.
3. Live-test Impact in `adk web` with the full seed loaded (burn down the biggest unverified surface early).

---

## 12. Research docs produced in this session (in `docs/research/`)

1. `coordinator-orchestration-patterns.md` — SequentialAgent + callbacks, Rules B/C/F implementation, state contract, error handling, SSE event mapping, Runner wiring, gotchas, A2A compatibility, testing strategy, full code skeletons.
2. `firestore-utilization-audit-tier1.md` — current-state audit, gap analysis, target schema + rules + indexes, seed strategy, stub-file content, cost model.
3. `llm-quotas-rate-limits.md` — Gemini 2026 tier tables, Vertex vs AI Studio, Groq+LiteLLM bug, model-mix strategy, slowapi wiring, tenacity retry, budget alerts, cost model.
4. `gcp-proper-utilization.md` — the "proper GCP way" checklist: multi-project, Workload Identity, Secret Manager, Cloud Run playbook, Firebase Hosting, observability, budget guardrails, CI/CD with WIF for GitHub, $300 credits, rollback playbook, pre-demo checklist.
5. `fastapi-sse-api-design.md` — endpoint specs, SSE contract with exact event JSON, streaming runner skeleton, ADK event mapping, middleware stack, rate limiting, CORS, client-side EventSource patterns, Cloud Run SSE caveats, testing SSE.
6. `firebase-auth-oauth-multitenancy.md` — Google OAuth + Firebase Auth + custom-claim tenancy, end-to-end judge flow, auto-onboarding endpoint, claim-setting, token refresh UX, cross-origin + SSE auth, emulator testing.
7. `observability-otel-cloud-trace.md` — OTel init in lifespan, per-agent span wiring, GenAI semantic conventions, structlog + GCP JSON renderer, audit_event wiring, dashboards, budget alerts, SIGTERM span flush, testing.

---

## 13. User questions answered inline in this session

- **"Current status of our Firestore database?"** → Partial rules (7 collections), composite indexes on shipments + exceptions only, 4 stub seed files, 4 overlapping seeder scripts. Detail in `firestore-utilization-audit-tier1.md`.
- **"Why do we need a safety keyword list when the LLM can determine?"** → Latency (1ms vs 600-2000ms), cost/determinism on demo day, auditability (grep vs opaque LLM verdict), defense in depth. LLM still classifies safety internally; keyword list is an additional guardrail.
- **"What does cold-start / min-instances=1 mean?"** → Cloud Run shuts down unused apps to save money; next visitor waits 4–8s while Python boots. `min-instances=1` keeps 1 copy always running → instant click. ~$15 for 48h of warmth.
- **"Vertex AI vs direct Gemini API?"** → Vertex is the "proper GCP way" (Workload Identity, Cloud Trace integration, no API key in code); direct API is simpler + current. Decision deferred; Vertex migration is a 2-hour follow-up.
- **"Proper way to utilize GCP?"** → Full answer in `gcp-proper-utilization.md`: Workload Identity, Secret Manager, Cloud Run with min-instances, Firebase Hosting + Cloud Run rewrite rule, Cloud Trace + Cloud Logging via OTel, budget alerts, multi-project split, CI/CD with WIF.
- **"Are we properly using Firestore / 100%?"** → No. ~60–70% today. Full gap analysis in `firestore-utilization-audit-tier1.md`.
- **"Does ADK offer rate limiting?"** → No. ADK relies on the underlying SDK (Gemini's own per-project quota is the ceiling). We wire slowapi at FastAPI layer + tenacity retry at tool layer + `max_output_tokens` cap at agent config. Full answer in `llm-quotas-rate-limits.md`.

---

## 14. Deferred items (Tier 2+ post-Apr-28)

- Resolution agent (Generator-Judge).
- Supermemory + `UserContextProvider` + dynamic context injection.
- Rules A, D, E (WhatsApp voice urgency, festival/monsoon context, D2C reputation).
- `AgentRunner` framework-portability layer.
- Tamil / Telugu / Kannada multilingual.
- Vertex AI migration (if not done before Apr 28).
- Full BigQuery log sink + analytics.
- React dashboard (we're building minimum UI for Tier 1; full React dashboard is Tier 3 per ADR-007).
- Multi-turn Coordinator conversations.
- Gemini 2.5 context caching.
- Self-serve multi-tenant onboarding.

---

## 15. SDLC note

This session ran Research phase per `CLAUDE.md` SDLC (`Research → PRD → Build → Test → Push`). Next session begins with a **PRD update discussion** (trimmed Sprint 3 PRD reflecting decisions 4.1–4.11), then user approval gate, then Build.
