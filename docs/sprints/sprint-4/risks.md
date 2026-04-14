---
title: "Sprint 4 Risks — Pre-mortem for API Layer + SSE Streaming + Security Hardening"
type: deep-dive
domains: [supply-chain, hackathon, sdlc, risk-management]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["./prd.md", "./test-plan.md", "[[Supply-Chain-Agent-Spec-Coordinator]]", "[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]"]
---

# Sprint 4 Risks — Pre-mortem

> **Exercise:** Imagine it is Apr 20, 2026. Sprint 4 failed. Why?
>
> This document enumerates the plausible failure modes for Sprint 4 (API Layer + SSE Streaming + Security Hardening), rank-orders them by probability × severity, and pre-commits mitigations. Run this BEFORE Sprint 4 starts so the engineer has named escape hatches.

---

## Table of Contents

1. [Pre-mortem Methodology](#1-pre-mortem-methodology)
2. [Top 10 Risks (Ranked)](#2-top-10-risks-ranked)
3. [Failure Mode Deep-Dives](#3-failure-mode-deep-dives)
4. [Mitigation Cross-Reference](#4-mitigation-cross-reference)
5. [Escalation Playbook](#5-escalation-playbook)
6. [Link to Rollback Plan](#6-link-to-rollback-plan)
7. [Risk Register Hand-off to Sprint 5](#7-risk-register-hand-off-to-sprint-5)

---

## 1. Pre-mortem Methodology

Gary Klein's pre-mortem: assume the sprint failed, then work backward to identify why. Each risk is scored on two axes:

- **Probability** (How likely is this to bite?): Low (< 15%), Medium (15–40%), High (> 40%)
- **Severity** (If it bites, how bad?): Low (fixable in < 1h), Medium (half-day loss), High (full day loss or rollback), Critical (sprint slip or demo-breaking)

The product `Probability × Severity` determines ranking. Anything Medium/High and above gets a named mitigation.

---

## 2. Top 10 Risks (Ranked)

| # | Risk | Prob | Severity | Score | Named Mitigation |
|---|------|------|----------|-------|------------------|
| 1 | ADK `streaming_mode="SSE"` doesn't yield per-subagent state deltas the way the spec assumes | M | High | 8 | Fallback polling in `CoordinatorStreamAdapter` (§3.1) |
| 2 | Prompt-injection heuristics have too many false positives, blocking legitimate Hinglish | M | High | 8 | 100-sample benign corpus test (U36–U40, S12) blocks sprint until FP ≤ 5% (§3.2) |
| 3 | Audit log middleware breaks `structlog.contextvars` propagation inside the streaming generator | M | High | 8 | Pure ASGI middleware (not `@app.middleware("http")`) + explicit test U43 (§3.3) |
| 4 | `sse-starlette` + async Coordinator generator deadlocks on client disconnect | M | Medium | 6 | `EventSourceResponse(ping=15)` + `asyncio.shield` + integration test I5 (§3.4) |
| 5 | Sprint 4 eats Sprint 5's runway (L1 rollback triggered) | M | High | 8 | Rollback L1 accepts 1 day of Sprint 5 budget; Rollback L2 cuts streaming if worse (§3.5) |
| 6 | Gemini stream API contract differs between local emulator and prod (chunk shape) | M | Medium | 6 | `adapt_gemini_stream` only reads `chunk.text`; integration tests use a fake with matching shape; smoke test hits real Gemini once (§3.6) |
| 7 | slowapi + `fakeredis` masks a race condition that real Redis exposes | L | Medium | 3 | Day 2 smoke test runs one test against real local Redis via Docker (§3.7) |
| 8 | OpenAPI frozen file drifts on every FastAPI version bump, false-failing contract test | M | Low | 3 | Pin FastAPI version; contract test failure message documents the `freeze_openapi.py` re-run (§3.8) |
| 9 | Multi-worker uvicorn causes per-company rate limit to be wrong with `memory://` backend | L | Medium | 3 | Sprint 4 uses single-worker uvicorn in dev; production Sprint 5 uses real Redis; risk is flagged (§3.9) |
| 10 | Cloud Run cold start breaks Sprint 5's `/health` probe budget (not Sprint 4 per se but blocks closure) | M | Medium | 6 | `/health` implemented with zero dependencies — returns in < 20ms local; measured in U51 (§3.10) |

### Secondary Risks (watchlist, no named mitigation beyond awareness)

| # | Risk | Prob | Severity |
|---|------|------|----------|
| 11 | Body size cap collides with real voice-note transcripts | L | M |
| 12 | `raw_content` SHA-256 hash is insufficient for debugging (can't reconstruct) | L | L |
| 13 | `firebase-admin` mock for tests diverges from real SDK behavior | L | M |
| 14 | httpx-sse version churn | L | L |
| 15 | Time-zone bugs in `freezegun`-based rate limit window reset tests | L | L |
| 16 | `fakeredis[lua]` compatibility with slowapi's `fixed-window` strategy | L | M |
| 17 | ASGI middleware ordering: rate limit must run AFTER auth but BEFORE prompt-injection defense | M | M |
| 18 | Bandit false positive on `unicodedata` / `re` calls | L | L |
| 19 | `sse-starlette` heartbeat ping interferes with ordering assertions in integration tests | L | M |
| 20 | `openapi_spec_validator` rejects FastAPI's OpenAPI 3.1 output for `text/event-stream` content type | M | L |

---

## 3. Failure Mode Deep-Dives

### 3.1 Risk #1 — ADK streaming mode doesn't yield per-subagent state deltas

**Failure narrative:** "Day 1 hour 8. `CoordinatorStreamAdapter` works in isolation but when we run it against the real Coordinator from Sprint 3, we see only `CoordinatorStartEvent` and `DoneEvent` — the specialist boundaries (`ClassificationReadyEvent`, `ImpactReadyEvent`) are swallowed because ADK's `Runner` coalesces sub-agent output into the top-level `is_final_response()`. The whole hybrid stream collapses to two events."

**Root cause hypothesis:** ADK's `streaming_mode="SSE"` is designed for Gemini token streaming, not for multi-agent state-delta streaming. Session-state deltas aren't exposed as stream events by default.

**Mitigation:**

1. **Primary path (preferred):** Use ADK's `before_model_callback` / `after_model_callback` on each sub-agent to push internal events into an `asyncio.Queue` that the stream adapter drains. Sprint 3's Coordinator spec already has `before_model_callback` for dynamic context injection — Sprint 4 adds `after_tool_callback` on the Classifier + Impact to emit `ClassificationReadyEvent` / `ImpactReadyEvent` from inside the agent lifecycle.

2. **Fallback path:** If callbacks don't give clean boundaries, the adapter runs `Runner.run_async()` without streaming, polls `session.state` at 100ms intervals, and emits events on state transitions (`session.state["classification"]` appeared → emit `ClassificationReadyEvent`). This loses the per-token `coordinator_thinking` drama but preserves the 7-event shape.

3. **Escape hatch:** Rollback L2 — drop streaming entirely, ship `/triage` JSON endpoint. Named in `prd.md` §13.

**Signals to trigger fallback path:** End of Day 1 hour 8 — if `test_coordinator_stream_adapter_nh48_happy_path` (U14) is still red with "missing ClassificationReadyEvent", switch to polling. Do not spend more than 90 minutes debugging ADK event internals.

### 3.2 Risk #2 — Prompt-injection false positives

**Failure narrative:** "Day 1 hour 4. We wrote the regex patterns and ran them against the benign corpus. 23% of Hinglish emergency texts match the `role_reassignment` pattern because `you are now` translates to very common phrases. The corpus test is red and the Coordinator refuses legitimate NH-48 events."

**Root cause hypothesis:** Heuristic patterns are too broad. Hinglish + Hindi script + romanized Hindi all interact poorly with English-tuned regex.

**Mitigation:**

1. Benign corpus (`tests/fixtures/benign_corpus.json`) has 100 samples:
   - 30 English operational texts
   - 30 romanized Hindi (Hinglish) emergency / routine texts
   - 20 Devanagari Hindi texts
   - 10 mixed-language texts (Hinglish + English)
   - 10 edge cases (short punctuation, technical IDs, JSON-ish content)
2. Test S12 blocks the sprint until FP ≤ 5/100.
3. Pattern tuning rule: if a benign sample triggers a pattern, either narrow the pattern (add a negative lookahead) OR add the sample as a soft-allowlist (whitelist hash).
4. **Last resort:** Drop the `high_entropy` check entirely (it's the lowest-value layer) and/or relax `role_reassignment` to require additional context (e.g. "you are now" followed by a proper noun within 5 words).
5. **Escape hatch:** If corpus tuning eats more than 2 hours, drop the layer to "length + zero-width + delimiter-injection only" (the 3 checks with near-zero FP risk) and document in ADR-015 that the full pattern catalogue is deferred to Tier 2.

**Signals to trigger escape hatch:** Day 1 hour 5 — if the corpus test hasn't converged below 10% FP, switch to minimal defense.

### 3.3 Risk #3 — Audit log breaks contextvar propagation in streaming generator

**Failure narrative:** "Day 2 hour 5. Unit tests for audit log pass. Integration test I1 passes. But in the smoke test, the log lines for the streaming requests show `correlation_id: null` for the events emitted inside the `event_source()` async generator. The top-level request log is correct but everything emitted from within the stream loses context."

**Root cause hypothesis:** FastAPI's `@app.middleware("http")` decorator runs middleware on a separate task that doesn't inherit contextvars correctly when yielding from an async generator. This is a known structlog + FastAPI interaction.

**Mitigation:**

1. Use `asgi-correlation-id`'s pure ASGI middleware (`CorrelationIdMiddleware`) installed via `app.add_middleware(CorrelationIdMiddleware, ...)` — NOT the decorator form.
2. Bind contextvars explicitly in the endpoint handler before starting the stream: `structlog.contextvars.bind_contextvars(correlation_id=..., user_id=..., company_id=...)`.
3. Test U43 — `test_audit_log_binds_correlation_id_to_structlog_context` — asserts that a log line emitted from deep inside the stream generator carries the correlation ID.
4. If propagation still breaks, fall back to passing `correlation_id` as a function argument into the stream adapter (explicit over implicit).

**Signals:** Day 2 hour 5 smoke test inspects logs — if correlation ID is missing on stream-internal lines, stop and fix before closing sprint.

### 3.4 Risk #4 — SSE deadlock on client disconnect

**Failure narrative:** "Day 2 hour 3. Integration test I5 hangs for 30 seconds then the test runner kills it. The server log shows the coordinator is still running after the client closed the connection. Zombie tasks accumulate."

**Root cause hypothesis:** `sse-starlette` doesn't propagate client disconnect to the upstream generator cleanly unless heartbeat is enabled. The Coordinator run continues draining Gemini tokens into an abandoned queue.

**Mitigation:**

1. `EventSourceResponse(event_source(), ping=15)` — heartbeat every 15s gives `sse-starlette` a chance to detect dead clients.
2. Wrap the event source generator in `asyncio.shield` where appropriate, but also listen for `asyncio.CancelledError` inside the Coordinator runner (`stream_triage`) and propagate a cancel to the underlying `Runner.run_async()`.
3. Test I5 asserts no zombie tasks via `asyncio.all_tasks()`.
4. Add a `await request.is_disconnected()` check inside the generator loop every iteration (FastAPI/Starlette API) as a second line of defense.

**Signals:** Test I5 hang or zombie task count > baseline after disconnect.

### 3.5 Risk #5 — Sprint 4 eats Sprint 5's runway

**Failure narrative:** "End of Apr 19. Integration test I1 is still red. Event ordering works but `done.triage_result.processing_time_ms` is 8,300 ms (above the 5,000 cap) because fake Gemini has 2s artificial delay and the Coordinator does too many sequential steps."

**Root cause hypothesis:** Optimistic timing estimate on the Coordinator pipeline + test overhead from fakeredis + Firestore emulator.

**Mitigation:**

1. **Rollback L1** — extend Sprint 4 into Apr 20 morning. Cost: Sprint 5 React frontend depth reduced from "polished" to "functional".
2. **Performance debug triage:**
   - Replace fake Gemini's `asyncio.sleep(2)` with `asyncio.sleep(0)` → eliminate artificial delay
   - Run Coordinator in streaming mode so classification + impact + summary overlap
   - Profile to identify the actual bottleneck
3. If Sprint 3 Coordinator's `processing_time_ms` measurement includes test fixture overhead, split it into `llm_ms` + `io_ms` + `overhead_ms` and gate on `llm_ms + io_ms` only.

**Signals:** End of Day 2 hour 4 (integration test phase) — if I1 is still red, declare L1.

### 3.6 Risk #6 — Gemini stream API contract differs across environments

**Failure narrative:** "Day 2 hour 6 smoke test. Works with fake Gemini. Against real Gemini, `chunk.text` is `None` for half the chunks because Google's SDK emits chunks with `.candidates[0].content.parts[0].text` instead. Our adapter skips them silently and we get 3 `coordinator_thinking` events instead of 15."

**Root cause hypothesis:** `google-genai` SDK chunk shape evolution. The `.text` attribute is a convenience method that only works for certain chunk types.

**Mitigation:**

1. `adapt_gemini_stream` uses `getattr(chunk, "text", None)` as the primary path.
2. Fallback extraction: if `.text` is None, try `chunk.candidates[0].content.parts[0].text` with a try/except `AttributeError`.
3. Fake Gemini fixture mirrors the real SDK's chunk shape using the same attribute structure.
4. Smoke test hits real Gemini ONCE (Day 2 hour 6) — if chunks are missing, the pattern is exposed immediately.

**Signals:** Smoke shows fewer `coordinator_thinking` events than expected.

### 3.7 Risk #7 — fakeredis masks a real Redis race

**Failure narrative:** "Sprint 5 deploy. Rate limit test passes locally with fakeredis but in Cloud Run with real Memorystore, we see counters going backwards for brief windows — the fixed-window strategy uses `INCR` + `EXPIRE` non-atomically. Two concurrent requests at the window boundary can both observe count=1."

**Root cause hypothesis:** slowapi's `fixed-window` uses `INCR` + `EXPIRE` as two ops. Fakeredis Python implementation might be more forgiving.

**Mitigation:**

1. Day 2 hour 6 smoke test runs `test_rate_limit_per_user_threshold` against a real Redis Docker container.
2. If behavior differs, switch slowapi strategy to `moving-window` (uses `ZADD` + `ZREMRANGEBYSCORE` atomically).
3. Document in ADR-014 consequences: "slowapi fixed-window has a benign race at window boundaries; acceptable for hackathon."

**Signals:** Smoke test shows intermittent 200s where 429s were expected.

### 3.8 Risk #8 — OpenAPI frozen file drifts on FastAPI version bump

**Failure narrative:** "Day 2 hour 5. Contract test fails with a diff in the `schemas.HTTPValidationError` field because FastAPI 0.136.0 changed how it emits the schema. We didn't change any code."

**Root cause hypothesis:** FastAPI internal schemas (not our own) shift between minor versions.

**Mitigation:**

1. Pin FastAPI version in `pyproject.toml`: `fastapi = "0.135.2"` (or whatever Sprint 0 chose).
2. Contract test `C6 - test_no_breaking_changes_vs_frozen` only checks OUR paths/methods/required fields — not internal schemas.
3. Failure message on C6 includes the literal command to regenerate: `python scripts/freeze_openapi.py`.
4. Escape hatch: If the diff is purely internal (not our contract), accept the re-freeze and document in `impl-log.md`.

### 3.9 Risk #9 — Multi-worker uvicorn + memory backend

**Failure narrative:** "Day 2 smoke test. Rate limit of 10/min gets bypassed because we're running `uvicorn --workers 4` and each worker has its own in-memory counter."

**Root cause hypothesis:** slowapi `memory://` backend is worker-local. Sprint 0 may have defaulted to multi-worker uvicorn.

**Mitigation:**

1. Sprint 4 local dev uses `uvicorn --workers 1 --reload`. Documented in `make run-api`.
2. slowapi is configured with `storage_uri=redis://...` (never `memory://`) even in dev.
3. Sprint 5 Cloud Run config will use `concurrency=80` single instance (Cloud Run terminology) — effectively single worker per container with multiple containers, and Memorystore shares state.

### 3.10 Risk #10 — `/health` too slow for Cloud Run probe budget

**Failure narrative:** "Sprint 5 Cloud Run deploy. `/health` takes 400ms on cold start because FastAPI boots the dependency tree. Cloud Run probe times out at 1s (first probe) and marks the service unhealthy."

**Root cause hypothesis:** `/health` endpoint doesn't actually depend on the full app tree but the first-ever request to it does because FastAPI lazy-initializes dependencies.

**Mitigation:**

1. `/health` has ZERO dependencies — no `Depends()`, no database, no Gemini, no Redis, no Firestore.
2. Test U51 asserts `/health` returns in < 200ms in-process.
3. Sprint 5 will add a startup probe that warms the app before the first liveness probe.
4. Cloud Run `min_instances=1` keeps the app warm (Sprint 5 concern, named in the master sprint plan).

---

## 4. Mitigation Cross-Reference

| Mitigation artifact | Risks it covers |
|---------------------|-----------------|
| `prd.md §13 Rollback Plan` | 1, 5 |
| Test U14 (`test_coordinator_stream_adapter_nh48_happy_path`) | 1 |
| Test U43 (`test_audit_log_binds_correlation_id_to_structlog_context`) | 3 |
| Test I5 (`test_stream_aborts_cleanly_on_client_disconnect`) | 4 |
| Test S11 + S12 (prompt injection corpus) | 2 |
| `asgi-correlation-id` middleware (pure ASGI) | 3 |
| `EventSourceResponse(ping=15)` | 4 |
| `CoordinatorStreamAdapter` polling fallback | 1 |
| Pinned FastAPI version | 8 |
| Single-worker `make run-api` | 9 |
| `/health` zero-dependency implementation | 10 |
| ADR-014 (SSE contract) | 1, 4, 7 |
| ADR-015 (prompt injection layer) | 2 |
| Day 2 hour 6 smoke test | 6, 7, 9 |

---

## 5. Escalation Playbook

**If at any time during Sprint 4 a test or component is red for more than 90 minutes without clear progress, escalate per this table.**

| Stuck on | Escalate to | Action |
|----------|-------------|--------|
| ADK streaming events | Risk 3.1 | Switch to polling fallback. Do NOT spend > 90 min on ADK event internals. |
| Prompt-injection FP rate | Risk 3.2 | Drop to minimal defense (length + zero-width + delimiter). Document in ADR-015. |
| Contextvar propagation | Risk 3.3 | Pass correlation_id as explicit arg. |
| SSE client disconnect | Risk 3.4 | Enable `ping=15`, add `request.is_disconnected()` poll. |
| Integration test I1 green | Risk 3.5 | Invoke Rollback L1. |
| Gemini chunk shape | Risk 3.6 | Add fallback extraction path. |
| Rate limit on real Redis | Risk 3.7 | Switch slowapi strategy to `moving-window`. |
| OpenAPI contract diff | Risk 3.8 | Re-freeze if diff is internal only. |
| Multi-worker rate limit | Risk 3.9 | Force `--workers 1`. |
| `/health` latency | Risk 3.10 | Strip dependencies from the endpoint. |

**Last resort:** If two or more of the above fire at once, invoke Rollback L2 (cut streaming, ship JSON `/triage`). If three or more, invoke Rollback L3 (use `adk web` for demo).

**Hard stop:** If Rollback L3 is triggered, Sprint 4 is closed at end of Apr 19 regardless of state. Don't sink more time into it.

---

## 6. Link to Rollback Plan

See `prd.md §13 Rollback Plan`. Summary:

- **L1:** Extend Sprint 4 into Apr 20 morning (eats 1 day of Sprint 5 budget).
- **L2:** Cut streaming; ship `/triage` JSON endpoint. Keep all security work.
- **L3:** Abandon Sprint 4 entirely; demo runs on `adk web` against Cloud Run.

Pre-commit: **L2 is the user-preferred escape.** L3 is absolute floor. L1 is only chosen if the remaining work is < 4 hours.

---

## 7. Risk Register Hand-off to Sprint 5

These risks are acknowledged by Sprint 4 but deferred to Sprint 5 for actual mitigation:

| # | Risk | Sprint 5 owner |
|---|------|----------------|
| S5-R1 | Cloud Run cold start exceeds probe budget | Deploy sprint: `min_instances=1`, startup probe, Cloud Run revision strategy |
| S5-R2 | Real Memorystore behavior differs from `fakeredis` | Deploy sprint: run `test_rate_limit_per_user_threshold` against Memorystore once after deploy |
| S5-R3 | Firebase ID token expiry during long-running client sessions | Frontend sprint: refresh token via Firebase Web SDK |
| S5-R4 | CORS allowlist for production domains | Deploy sprint: replace dev CORS config |
| S5-R5 | Cloud Logging log retention (default = 30 days, may be too short for audit) | Deploy sprint: log sink to BigQuery |
| S5-R6 | SIGTERM graceful drain for zero-downtime deploys | Deploy sprint: add signal handler |

Sprint 4 writes these into `sprints/sprint-5/risks.md` as starter content when Sprint 5 kicks off.

---

## 8. Post-mortem Template

If Sprint 4 actually fails, write a real post-mortem using this template (file lands in `sprints/sprint-4/post-mortem.md`):

1. **What happened?** (factual timeline, no blame)
2. **What did we expect?**
3. **Root cause** (5 whys)
4. **Which risk did we miss?** (cross-ref back to this document — was it in the top 10? Secondary? Not foreseen?)
5. **What did we do right?**
6. **Action items for Sprint 5+**

The point of keeping this template here is to speed up the post-mortem if we need one, not to predict it.

---

## Cross-References

- `./prd.md` — Sprint 4 PRD (source of truth for scope)
- `./test-plan.md` — Sprint 4 test matrix
- `./adr-014-sse-hybrid-streaming-contract.md` — SSE contract decision (covers Risks 1, 4, 7)
- `./adr-015-prompt-injection-heuristics-layer.md` — Heuristics layer decision (covers Risk 2)
- `./../sprint-0/prd.md` — Foundation (source of `main.py`, middleware stubs, Auth)
- `./../sprint-3/prd.md` — Coordinator PRD (upstream of Sprint 4 streaming)
- [[Supply-Chain-Agent-Spec-Coordinator]] — Canonical SSE event schema
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — Master risk register and Spiral governance
