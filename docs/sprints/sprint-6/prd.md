---
title: "Sprint 6 PRD — Submission Package (Google Solution Challenge 2026)"
type: deep-dive
domains: [supply-chain, hackathon, submission, sdlc]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]", "[[Supply-Chain-Product-Recap]]", "[[Supply-Chain-Demo-Scenario-Tier1]]", "[[Supply-Chain-Judging-Strategy]]", "[[Supply-Chain-Demo-Script]]", "[[Supply-Chain-Demo-Video-Strategy]]", "[[Supply-Chain-Video-Production-Hackathon-Demos]]", "[[Supply-Chain-Competitor-Analysis]]"]
---

# Sprint 6 PRD — Submission Package (Google Solution Challenge 2026)

> **Plan authored with:** `superpowers:writing-plans` skill
> **Sprint window:** Apr 22 – Apr 23, 2026 (2 days) + Apr 24 submission buffer
> **Deadline:** Solution Challenge Round 1 prototype submission — **Apr 24, 2026**
> **Feature code produced this sprint:** **Zero.** Code is locked after Sprint 5. This sprint is pure packaging + final review.
> **Audience:** A new developer should be able to execute Sprint 6 by following this PRD verbatim.

---

## Table of Contents

1. [Objective](#1-objective)
2. [Scope IN (file-by-file)](#2-scope-in-file-by-file)
3. [Out-of-Scope](#3-out-of-scope)
4. [Acceptance Criteria (Sprint Gate)](#4-acceptance-criteria-sprint-gate)
5. [Test Cases](#5-test-cases)
6. [Security Considerations](#6-security-considerations)
7. [Dependencies on Sprints 0-5](#7-dependencies-on-sprints-0-5)
8. [Day-by-Day Build Sequence](#8-day-by-day-build-sequence)
9. [Definition of Done per Artifact](#9-definition-of-done-per-artifact)
10. [Risks](#10-risks)
11. [Success Metrics](#11-success-metrics)
12. [Full Content Templates](#12-full-content-templates)
    - [A. Demo Video Script (beat-by-beat)](#a-demo-video-script-beat-by-beat)
    - [B. Problem Statement Template](#b-problem-statement-template-400-words)
    - [C. Solution Brief Template](#c-solution-brief-template-400-words)
    - [D. Project Deck Outline (7 slides)](#d-project-deck-outline-7-slides)
    - [E. README Template](#e-readme-template-final-polished)
    - [F. Architecture Diagram Specification](#f-architecture-diagram-specification)
    - [G. Demo Video Recording Checklist](#g-demo-video-recording-checklist-obs)
    - [H. Submission Portal Upload Checklist](#h-submission-portal-upload-checklist)
    - [I. Final Code Review Checklist](#i-final-code-review-checklist)
    - [J. SDG Alignment Statement](#j-sdg-alignment-statement)
13. [Rollback Plan](#13-rollback-plan)
14. [Cross-References](#14-cross-references)
15. [Research Citations](#15-research-citations)
16. [Open Assumptions](#16-open-assumptions)

---

## 1. Objective

Package the working prototype built across Sprints 0-5 into all seven Google Solution Challenge submission artifacts and ship them to the Round 1 portal by **Apr 24, 2026**.

**One-sentence goal:** Convert working code into a judge-ready submission package that maximises the 50-point rubric (Impact 25 / Technology 25) without touching any feature code.

**Why this sprint exists:** Per [[Supply-Chain-Demo-Video-Strategy]], *"judges do not evaluate your project — they evaluate your submission artifacts about your project"*. Round 1 is an asynchronous paper review where ~5-10 minutes of judge attention per submission decides the Top 100 cut. The package — not the code — is the interface to the judges.

**Strategic framing:** Per [[Supply-Chain-Judging-Strategy]], coherence matters more than isolated criterion optimisation. Every artifact in Sprint 6 must reinforce the same narrative: *supply-chain exceptions cost coordinators 40-60% of their day; a multi-agent ADK system autonomously triages the NH-48 truck breakdown scenario in <4 seconds; this directly supports SDG 9 (resilient infrastructure) and SDG 12 (responsible consumption/production).*

---

## 2. Scope (IN) — file-by-file

Every file below must exist, be version-controlled, and be referenced from the submission portal by end-of-day Apr 23.

### 2.1 Submission documents (`docs/submission/`)

| File | Purpose | Size/Length |
|------|---------|-------------|
| `docs/submission/demo-video-script.md` | Beat-by-beat narration + shot descriptions + timestamps (see Template A) | ~500 words, 5 beats |
| `docs/submission/demo-video-shotlist.md` | Recording shot list mapped to script beats, pre-stage checklist | ~1 page |
| `docs/submission/problem-statement.md` | 1-page problem statement (see Template B) | 400 words |
| `docs/submission/solution-brief.md` | 1-page solution brief (see Template C) | 400 words |
| `docs/submission/project-deck.pptx` or Google Slides export link | 7-slide deck per Template D | 7 slides |
| `docs/submission/sdg-alignment.md` | Explicit SDG 9 + SDG 12 mapping with quantified metrics (Template J) | ~300 words |
| `docs/submission/submission-checklist.md` | Portal-upload dry-run checklist (Template H) | Checklist |

### 2.2 README and architecture polish (`/README.md`, `docs/architecture/`)

| File | Change |
|------|--------|
| `README.md` | **Final polished version** per Template E — badges, quickstart, architecture diagram embed, live URL link, demo-video embed, SDG callout, license, contributing, acknowledgements |
| `docs/architecture/overview.md` | Updated with final (post-Sprint-5) system diagram; mermaid + exported PNG |
| `docs/architecture/diagram.excalidraw` or `docs/architecture/diagram.mermaid` | Source file for architecture diagram (Template F) |
| `docs/architecture/diagram.png` | Exported 1920×1080 PNG suitable for README and deck |
| `docs/onboarding/setup.md` | Verified fresh-clone instructions (no assumed env state) |
| `AGENTS.md` | Per 2026 convention — AI-agent-friendly project context; separates build/test/convention instructions from human README |

### 2.3 Smoke tests (`tests/submission/`, `tests/e2e/`)

| File | Purpose |
|------|---------|
| `tests/submission/test_fresh_clone_setup.sh` | Bash script that clones the public repo into a temp dir, runs `make setup && make test`, asserts exit 0 — simulates a judge running the repo |
| `tests/e2e/test_live_url_smoke.py` | Pytest that hits the Sprint-5-deployed Cloud Run URL, exercises the NH-48 exception endpoint, asserts Classifier + Impact agents respond with expected shape and latency <6s |
| `tests/submission/test_demo_video_quality.md` | Manual QA checklist for video (resolution, audio levels, length, no PII, no secrets visible) |

### 2.4 Architecture Decision Record

| File | Decision |
|------|----------|
| `docs/decisions/adr-018-submission-artifacts.md` | Documents: (a) video length (90s core / 2-3min max), (b) why 7-slide deck over 5, (c) why SDG 9 primary over SDG 13, (d) why defer user-interviews, (e) why Canva over raw Google Slides for deck |

Sprint 5 used ADR-016 (React frontend framework) and ADR-017 (Cloud Run region + min-instances). Sprint 6 continues the sequence at **ADR-018**.

### 2.5 Sprint-6 documentation artifacts (per Spiral SDLC convention)

Located in `10 - Deep Dives/Supply-Chain/sprints/sprint-6/` (these files — PRD, test-plan, risks) plus code-side artifacts under `docs/sprints/sprint-6/` (impl-log, test-report, review, retro) per the 9-artifact convention from [[Supply-Chain-Sprint-Plan-Spiral-SDLC]].

---

## 3. Out-of-Scope

| Item | Reason |
|------|--------|
| **Any new feature code** | Code is locked after Sprint 5 Evaluate phase. Touching code risks breaking the live URL. Bug fixes only via hotfix path (see Rollback). |
| **Three real-user interviews** | **Deferred by user decision.** Acknowledged gap — costs us ~5 rubric points on "three feedback points from real users" in Impact dimension. [[Supply-Chain-Judging-Strategy]] flags this explicitly. Will be addressed before May 29 Top-100 deadline per [[Supply-Chain-Product-Recap]] §"Deferred Blind Spots". |
| **Real production monitoring / uptime SLOs** | Out of scope for Round 1. Sprint 5 set `min_instances=1` which is sufficient for demo availability. |
| **Multi-region deployment** | Single-region (`asia-south1`) per ADR-017 is fine for Round 1. |
| **Formal security audit / pen test** | Bandit + safety + pip-audit from Sprint 0 suffice for Round 1 submission. |
| **Custom domain / branded URL** | Cloud Run default `*.run.app` URL is acceptable. Judges click links, they do not judge DNS. |
| **Marketing website** | Landing page is the live MVP Cloud Run URL, which is all the portal needs. |
| **Monetisation/pricing pages** | Not required by Solution Challenge rubric. |

---

## 4. Acceptance Criteria (Sprint Gate)

All 16 criteria must be green before the sprint closes. Any red blocks submission.

1. **AC-01** — `docs/submission/demo-video-script.md` exists and matches Template A beat-by-beat with total word count in 450-560 range.
2. **AC-02** — `docs/submission/problem-statement.md` exists, 380-420 words, includes 3+ quantified pain metrics.
3. **AC-03** — `docs/submission/solution-brief.md` exists, 380-420 words, explicitly names Gemini 2.5 Flash, Google ADK, Firestore, Cloud Run, Firebase Auth.
4. **AC-04** — Project deck exists as `.pptx` AND a public Google Slides view-link. 7 slides match Template D. Slide master uses Google brand-safe colours (no trademarked logos misused).
5. **AC-05** — **Demo video recorded, edited, uploaded** to YouTube (unlisted) AND to Google Drive (public-view). Length: core beats 90s, total including hook+impact ≤180s. Resolution ≥1080p. Audio peaks between -12dB and -6dB, no clipping.
6. **AC-06** — `README.md` passes Template E checklist: badges render, architecture diagram embedded as PNG, live URL is clickable and returns 200, setup section copy-pasteable.
7. **AC-07** — `docs/architecture/overview.md` updated with final diagram; PNG is ≥1600px wide for deck embedding.
8. **AC-08** — `AGENTS.md` exists and documents: (a) build commands, (b) test commands, (c) style conventions, (d) agent entry points, per 2026 AGENTS.md convention (>20k repos use it).
9. **AC-09** — `tests/submission/test_fresh_clone_setup.sh` runs on a fresh Ubuntu 22.04 VM or container, completes in <10 minutes, exits 0.
10. **AC-10** — `tests/e2e/test_live_url_smoke.py` runs against the Sprint-5 Cloud Run URL, asserts Classifier agent returns `exception_type="carrier_capacity_failure"` and Impact agent returns `total_value_at_risk_inr=1850000` for the NH-48 scenario.
11. **AC-11** — `adr-018-submission-artifacts.md` exists, references all 7 artifacts, documents the 5 key decisions.
12. **AC-12** — **Final code review passes** via `superpowers:code-reviewer` skill against the full Sprint-0-to-5 diff — no Critical or High severity findings remain unresolved. Medium/Low findings documented in `docs/sprints/sprint-6/review.md` with ship-or-fix decision.
13. **AC-13** — Secret scan clean: `detect-secrets scan` across the repo finds no new secrets. `.env` is gitignored. `git log -p | grep -E "(api_key|secret|password)"` returns nothing committed.
14. **AC-14** — No PII in demo video or deck — driver name, phone numbers, real customer names are either obviously fictional ("Priya", "Ramesh", "BlushBox Beauty") or redacted.
15. **AC-15** — Submission portal dry-run: every field in the Solution Challenge form has a prepared, copy-pasteable answer stored in `docs/submission/portal-answers.md`. File upload fields have the right files pre-staged in a local `submission-bundle/` directory.
16. **AC-16** — All 7 artifacts uploaded to the official Solution Challenge submission portal before **Apr 24, 23:59 IST**. Confirmation email received and archived to `docs/submission/confirmation.txt`.

---

## 5. Test Cases

### 5.1 Fresh-clone setup test (Given/When/Then)

**Given** a judge clones the public GitHub repo onto a machine with only Python 3.13 and `uv` installed,
**When** they run `make setup` followed by `make test`,
**Then** all unit tests pass, integration tests pass with Firestore emulator, and the command exits 0 within 10 minutes.

Implementation: `tests/submission/test_fresh_clone_setup.sh` uses `docker run --rm -it python:3.13-slim bash -c "..."` to sandbox the test.

### 5.2 Live URL smoke test

**Given** the Sprint-5-deployed Cloud Run URL and a valid test Firebase ID token,
**When** the test POSTs the NH-48 WhatsApp voice-note payload to `/triage/stream`,
**Then** the response stream contains (in order): `classifier.started` → `classifier.done` (with `exception_type="carrier_capacity_failure"`) → `impact.started` → `impact.done` (with `total_value_at_risk_inr=1850000`), and total streaming time is <6 seconds.

Implementation: `tests/e2e/test_live_url_smoke.py` with `httpx.AsyncClient`, parametrised on env var `LIVE_URL`.

### 5.3 Video quality manual QA checklist

- [ ] Resolution ≥1920×1080
- [ ] Duration ≤180 seconds (target: core beats 90s, total with hook/impact ≤180s)
- [ ] File size within Google Drive + YouTube upload limits (no practical cap, but keep <500MB for portability)
- [ ] Audio peaks -12dB to -6dB, no clipping, no background hum
- [ ] Narration is intelligible at 1.5× playback (judges commonly watch at accelerated speed)
- [ ] No visible PII (real customer names, phone numbers, employee identifiers)
- [ ] No visible secrets (API keys, service-account JSON, .env contents)
- [ ] No console errors visible in browser devtools during demo segments
- [ ] Mouse cursor movements are intentional (no "searching for the tab" moments)
- [ ] Opening 10 seconds pass the "would a tired judge keep watching?" test
- [ ] Closing frame holds for 3 seconds of silence after narration ends

### 5.4 README rendering test

**Given** the final `README.md` pushed to GitHub,
**When** the GitHub rendered page loads,
**Then** all badges display (CI, coverage, license, Python version, FastAPI version), the architecture PNG renders, the live URL is a clickable hyperlink, and the demo video embed thumbnail displays.

### 5.5 Deck export test

**Given** the 7-slide project deck in Google Slides,
**When** exported to `.pptx` and re-opened in LibreOffice Impress (simulating judge machines),
**Then** all fonts render, no broken images, slide order matches Template D, speaker notes preserved on slides 2-7.

### 5.6 Submission portal dry-run

**Given** a staging account on the Solution Challenge portal,
**When** the team walks through every form field with prepared answers,
**Then** every required field has content, every file upload has a staged file, and the "Save Draft" action succeeds without validation errors.

---

## 6. Security Considerations

This sprint is packaging — but packaging is where most security leaks happen. Artifacts are published publicly.

| Threat | Mitigation |
|--------|------------|
| API keys leaked in demo video screen recording | Pre-record checklist: close terminal tabs, use env-var redaction in VS Code, open `.env.example` not `.env` |
| Service-account JSON visible in repo | `detect-secrets` pre-commit hook already in place (Sprint 0). Run `detect-secrets scan --all-files` before push. |
| Real customer PII in demo data | NH-48 scenario uses fictional entities (NimbleFreight, BlushBox, Priya, Ramesh). Verify no real company names creep in from dev testing. |
| GitHub repo made public with dev commits containing secrets | Audit git history: `git log -p --all | grep -iE "api[_-]?key\|secret\|password\|token"`. If secrets are in history, rotate keys and use `git filter-repo` before publishing. |
| Live URL exposes unauthenticated endpoints | Confirm Sprint-4 auth middleware is active on all routes. Use `curl -i` against each endpoint without a token; 401 expected. |
| Firestore security rules permissive | Confirm `infra/firestore.rules` from Sprint 0 still enforces `request.auth != null` on read/write. |
| Deck contains internal architecture that reveals attack surface | Deck architecture is high-level; no ports, no IAM service account names, no bucket names. |
| YouTube video made public (not unlisted) before submission review | Upload as "Unlisted" explicitly. Only the portal URL link can access it. |

**Sprint-6 security sign-off:** Update `docs/security/threat-model.md` with a "Submission" section addressing each row above, mark resolved.

---

## 7. Dependencies on Sprints 0-5

Sprint 6 is a **pure packaging sprint**. It assumes every deliverable below is complete and functional. Any gap here blocks Sprint 6 entirely.

| Sprint | Must-exist artifact | Used by Sprint 6 for |
|--------|--------------------|----------------------|
| Sprint 0 | `pyproject.toml`, `Makefile`, CI workflows, docs templates, threat model, ADRs 001-007 | README badges, fresh-clone test, ADR numbering continuation |
| Sprint 1 | Classifier Agent (`src/agents/classifier.py`), classifier tests passing | Demo video Beat 3 (classifier reasoning trace), live URL smoke test |
| Sprint 2 | Impact Agent (`src/agents/impact.py`), Firestore schema, NH-48 seed data | Demo video Beat 3 (impact reasoning), solution brief value-at-risk claim |
| Sprint 3 | Coordinator Agent + full pipeline end-to-end | Demo video Beats 3-4, README "how it works" section |
| Sprint 4 | `/triage/stream` SSE endpoint, Firebase Auth middleware, rate limiting | Live URL smoke test, security considerations section |
| Sprint 5 | Cloud Run deployment, live URL, React frontend (or `adk web` fallback), ADRs 016-017 | Live URL in README + deck + portal, demo video recording (actual screen capture from deployed URL), fresh-clone setup docs |

**If Sprint 5 is late:** submission uses `adk web` screenshots + localhost URL note. Judge experience degrades but submission still ships. See Rollback Plan §13.

---

## 8. Day-by-Day Build Sequence

### Day 1 — Apr 22, 2026 (Wednesday)

**Morning (09:00-13:00): Documents + script**

| Time | Task | Output |
|------|------|--------|
| 09:00-09:30 | Read this PRD top-to-bottom. Pre-mortem check: re-read `risks.md`. | Mental model |
| 09:30-10:30 | Write `docs/submission/problem-statement.md` using Template B. | 400-word doc |
| 10:30-11:30 | Write `docs/submission/solution-brief.md` using Template C. | 400-word doc |
| 11:30-13:00 | Write `docs/submission/demo-video-script.md` using Template A. Rehearse read-aloud twice with a stopwatch. Tighten overlong beats. | Script, ≤180s read-aloud |

**Afternoon (14:00-19:00): Video recording**

| Time | Task | Output |
|------|------|--------|
| 14:00-14:30 | Pre-stage demo environment per Template G. Warm Cloud Run (`curl` the live URL twice to skip cold-start). Seed NH-48 fixture in Firestore. | Demo-ready browser tabs |
| 14:30-15:30 | Record voiceover in 5 segments (one per beat) using OBS + decent USB mic. Multiple takes. Cleanest take wins. | `voiceover/beat-1.wav` through `beat-5.wav` |
| 15:30-17:00 | Record screen capture in 5 segments matching each voiceover beat. OBS 1080p 30fps, browser zoom 110%, cursor highlights enabled. | `screen/beat-1.mp4` through `beat-5.mp4` |
| 17:00-18:30 | Edit in DaVinci Resolve (free) or CapCut. Layer voiceover over screen capture. Normalise audio levels. Add title card + closing card. | `demo-video-v1.mp4` |
| 18:30-19:00 | Self-review against Template G checklist. If fail, list reshoots; else upload to YouTube (Unlisted) and Google Drive. | YouTube link + Drive link |

**Evening (20:00-22:00): README polish**

| Time | Task | Output |
|------|------|--------|
| 20:00-21:00 | Rewrite `README.md` per Template E. Embed YouTube thumbnail. Embed architecture PNG. Update badges. | Final README |
| 21:00-22:00 | Write `AGENTS.md`. Update `docs/architecture/overview.md`. | AGENTS.md + arch doc |

### Day 2 — Apr 23, 2026 (Thursday)

**Morning (09:00-13:00): Deck + tests**

| Time | Task | Output |
|------|------|--------|
| 09:00-11:00 | Build 7-slide deck per Template D in Google Slides. Export to `.pptx`. Share view-link. | Deck .pptx + link |
| 11:00-12:00 | Write `tests/submission/test_fresh_clone_setup.sh`. Run it in a Docker container. | Passing script |
| 12:00-13:00 | Write `tests/e2e/test_live_url_smoke.py`. Run against Sprint-5 URL. | Passing e2e test |

**Afternoon (14:00-18:00): Review + upload**

| Time | Task | Output |
|------|------|--------|
| 14:00-15:30 | Run `superpowers:code-reviewer` skill on the full Sprint-0-to-5 diff. Triage findings into Critical / Medium / Low. Fix Critical only. Document the rest in `review.md`. | `review.md` |
| 15:30-16:00 | Run `detect-secrets scan --all-files`. Run `bandit -r src/`. Run `safety check`. Fix blockers. | Security sign-off |
| 16:00-17:00 | Write `adr-018-submission-artifacts.md`. Write `docs/submission/sdg-alignment.md` (Template J). Write `docs/submission/portal-answers.md`. | ADR + SDG + portal answers |
| 17:00-18:00 | Submission portal dry-run: paste every answer, attach every file, preview. Do NOT submit yet. Save as draft. | Portal draft ready |

**Evening (19:00-22:00): Buffer + retro**

| Time | Task | Output |
|------|------|--------|
| 19:00-20:00 | Retrospective (`docs/sprints/sprint-6/retro.md`): Start/Stop/Continue. | Retro |
| 20:00-21:00 | Buffer for reshoots, edit passes, or any blocker fixes. | Resolved blockers |
| 21:00-22:00 | Git tag `v1.0.0-submission`, push, confirm CI green on main. | Tagged release |

### Day 3 — Apr 24, 2026 (Friday) — Submission day

| Time | Task | Output |
|------|------|--------|
| 10:00-10:30 | Final live-URL health check: `curl` the Cloud Run URL, run smoke test once more. | Health confirmation |
| 10:30-11:30 | Submission portal upload: complete every field from portal-answers.md in one sitting. Attach final video link, deck link, GitHub link, live MVP link, problem statement, solution brief. Submit. | Submission confirmation |
| 11:30-12:00 | Save confirmation email + portal confirmation page screenshot to `docs/submission/confirmation.txt` and `docs/submission/confirmation.png`. | Archived confirmation |
| 12:00+ | **Done.** No more code, no more pushes. Silent observation until Top-100 announcement (May 29). | Waiting mode |

---

## 9. Definition of Done per Artifact

### 9.1 Demo video
- [ ] Core beats recorded: Hook (0-30s), System (30s-1:15), Disruption (1:15-2:00), Response (2:00-2:30), Impact (2:30-3:00)
- [ ] Total runtime: core 90s minimum / 180s maximum
- [ ] 1080p, 30fps, H.264 MP4
- [ ] Voiceover recorded separately from screen capture (audio+visual sync in post)
- [ ] Audio: -12 to -6 dB peak, normalised, no clipping, background noise suppressed
- [ ] Uploaded to YouTube as **Unlisted** and Google Drive with **link-sharing = anyone with link can view**
- [ ] Video manual QA checklist (§5.3) green
- [ ] Script word count 450-560 range per Template A
- [ ] Closing frame holds 3 seconds silent

### 9.2 Problem statement
- [ ] 380-420 words
- [ ] Names the 5-layer problem model (fragmentation, manual bottleneck, tribal knowledge, reactive loop, scale breaks people)
- [ ] Cites at least 3 quantified pain metrics (2-4 hours per exception, 40-60% of coordinator day, 90+ hours/month, $1T annual logistics admin, 83% cannot respond in 24h)
- [ ] Names the persona (Priya, small 3PL coordinator, Mumbai)
- [ ] Specifies SDG 9 as primary alignment
- [ ] Ends with a one-sentence thesis

### 9.3 Solution brief
- [ ] 380-420 words
- [ ] Names every Google service used: ADK, Gemini 2.5 Flash, Firestore, Cloud Run, Firebase Auth (+ Firebase Hosting if React shipped in Sprint 5)
- [ ] Describes the 3-agent architecture: Coordinator → Classifier → Impact
- [ ] Describes the NH-48 exemplar scenario concretely (WhatsApp voice note, 4 shipments, ₹18.5L value at risk)
- [ ] Quantifies the outcome: triage time <4 seconds vs 2-4 hours manual
- [ ] Links to live MVP URL
- [ ] Ends with "next steps" pointing to Tier 2 (Resolution Agent + Route Optimization API)

### 9.4 Project deck
- [ ] Exactly 7 slides
- [ ] Slide 1: Title + one-line tagline + team/solo name
- [ ] Slide 2: Problem (with 3 stat overlays)
- [ ] Slide 3: Solution (one mermaid/architecture diagram + one-line thesis)
- [ ] Slide 4: Demo screenshots (3 screens: classifier output, impact output, dashboard)
- [ ] Slide 5: Architecture (final diagram from §F)
- [ ] Slide 6: Impact + SDG alignment (SDG 9 primary, SDG 12 secondary with metric targets)
- [ ] Slide 7: Future / tier progression (Tier 2 resolution, Tier 3 communication)
- [ ] Exported as `.pptx` AND Google Slides public-view link
- [ ] Speaker notes on slides 2-7
- [ ] No trademark-violating logos; Google brand assets used per Google Brand Guidelines

### 9.5 GitHub README
- [ ] Top-of-file badges: Python version, License (MIT), CI status, coverage %, FastAPI version
- [ ] H1 = project name + tagline
- [ ] "What it does" paragraph (3 sentences)
- [ ] Live MVP link (clickable)
- [ ] Demo video embed (YouTube thumbnail with link)
- [ ] Architecture diagram embedded as PNG
- [ ] Quickstart (5 commands max, copy-pasteable)
- [ ] "How it works" section (NH-48 example, 2 paragraphs)
- [ ] Tech stack list (6 Google services)
- [ ] SDG alignment paragraph
- [ ] Testing section (`make test`, coverage instructions)
- [ ] Contributing (link to CONTRIBUTING.md)
- [ ] License (MIT)
- [ ] Acknowledgements (Google Developer Student Clubs, Solution Challenge)
- [ ] Passes §5.4 rendering test on GitHub

### 9.6 Live MVP link
- [ ] Cloud Run URL from Sprint 5 returns 200 on `/health`
- [ ] NH-48 demo scenario is the landing scenario (no judge setup required)
- [ ] `min_instances=1` confirmed (no cold-start penalty for judges)
- [ ] URL is copy-pasted into: README, deck, portal, problem-statement, solution-brief
- [ ] Manual curl smoke test passes within 24h of submission

### 9.7 User feedback evidence
- [ ] **DEFERRED.** Acknowledged gap in §3 Out-of-Scope. Placeholder note in `docs/submission/user-feedback-gap.md` explains the plan to close this before Top-100 deadline (May 29).

---

## 10. Risks

See `risks.md` for the full pre-mortem. Summary:

| Risk | P | Severity | Mitigation |
|------|---|----------|-----------|
| Demo video re-records blow the time budget | High | High | Record in 5 segments, not one take; script enforces 90-180s cap; Template G pre-stages everything |
| Live URL breaks on judge day | Medium | Critical | Sprint 5 sets `min_instances=1`; Sprint 6 runs smoke test morning of Apr 24; fallback is pre-recorded screen capture in the video |
| Fresh-clone setup fails on judge's OS | Medium | Medium | Docker-based test in §5.1 covers Linux; test manually on macOS if time |
| Secrets leaked in video or repo | Low | Critical | Pre-record checklist closes dev tabs; detect-secrets scan before push; git history audit |
| Submission portal validation rejects file sizes | Medium | Medium | Video uploaded to YouTube+Drive (unlimited), deck as Google Slides link (unlimited), only the small text artifacts go to the portal as attachments |
| Code review finds Critical issue at 17:00 on Apr 23 | Medium | High | Run code review at 14:00 leaving 4h for fixes; only Critical blocks submission, Medium/Low ship with documented caveats |
| User interview gap costs Top-100 placement | High | Medium | Accepted trade-off per user decision; compensate by over-investing in Technical Merit narrative coherence |
| Solo-builder fatigue on Day 2 | High | Medium | Day 1 evening is soft-stop at 22:00; Day 2 buffer at 20:00-21:00; sleep is part of the plan |
| GitHub repo public-flip exposes an older dev commit | Low | Critical | Squash-merge feature branches through Sprints 0-5; final check `git log --all --source` before flipping visibility |
| Judges cannot play `.pptx` deck correctly | Low | Low | Ship Google Slides link as primary; `.pptx` as fallback; both tested via §5.5 |

---

## 11. Success Metrics

**Primary (measurable by Apr 24 23:59 IST):**
- ✅ All 7 artifacts uploaded to portal (binary: yes/no)
- ✅ Confirmation email archived (binary)
- ✅ Live URL returns 200 at time of submission (binary)

**Secondary (measurable May 29 Top 100 announcement):**
- Top 100 advancement (binary) — primary desired outcome of Sprint 6
- If not advanced, retrospective identifies whether the gap was (a) scope/depth (fix in Tier 2) or (b) submission artifact quality (fix by re-reading this PRD)

**Tertiary (qualitative, assessed immediately post-submission):**
- Every artifact reinforces the same narrative (coherence test)
- Demo video has zero "dead frames" (per Principle 3 of [[Supply-Chain-Video-Production-Hackathon-Demos]])
- Problem statement would make a non-logistics judge lean forward within 10 seconds
- Solution brief names every Google service used, no decorative mentions

**Rubric-point self-assessment (pre-submission):**

| Rubric area | Weight | Self-score target | Why |
|-------------|--------|-------------------|-----|
| Problem statement clarity | 5 pts | 5/5 | 5-layer model, quantified, Priya persona |
| SDG alignment explanation | 5 pts | 4/5 | SDG 9 + 12 mapping explicit; SDG 13 omitted for focus |
| User feedback documentation | 5 pts | 1/5 | Acknowledged gap; deferred |
| Solution effectiveness metrics | 5 pts | 4/5 | Triage latency <4s, value-at-risk quantified |
| Future scaling plan | 5 pts | 5/5 | Tier 2 + Tier 3 progression well documented |
| Architecture + Google tech explanation | 5 pts | 5/5 | ADR series + architecture doc + deck slide 5 |
| Complete technical implementation | 5 pts | 5/5 | 3 agents + pipeline + UI + deploy all shipped Sprints 1-5 |
| Code challenges and solutions | 5 pts | 4/5 | Impl-logs across sprints document trade-offs |
| Working demo + features | 5 pts | 5/5 | Live URL + video |
| Scalability potential | 5 pts | 5/5 | Cloud Run + Firestore inherent; Module-Ready Orchestrator pattern |
| **Total estimate** | **50** | **43/50** | User-interview gap is the biggest loss |

43/50 is competitive for Top 100 advancement per historical winner analysis in [[Supply-Chain-Competitor-Analysis]] (past top-3 winners scored ~46-48/50).

---

## 12. Full Content Templates

### A. Demo Video Script (beat-by-beat)

> **Targeting: 90-second core (Beats 3-4) wrapped in 30s hook + 30s system context + 30s impact = 180s total.** This tightens the [[Supply-Chain-Demo-Script]] 3-minute version for the Tier 1 NH-48 anchor scenario. Narration total: ~460 words at 140 WPM = 197 seconds; edit for 180s.

#### Beat 1 — The Hook (0:00 – 0:30)

| Time | Narration | Visual |
|------|-----------|--------|
| 0:00-0:08 | "At any small 3PL in India, an exception coordinator spends 2 to 4 hours on every broken shipment." | Black screen. Single stat appears in white: "2-4 hours per exception." Pause, then: "90+ hours per month." |
| 0:08-0:18 | "Across 4 to 10 disconnected systems. 25 emails. 8 roles involved. 83% of teams cannot respond within 24 hours." | Montage: WhatsApp group screenshot, Excel sheet, carrier portal, inbox — 4 quick cuts, 2 seconds each. |
| 0:18-0:30 | "Meet Priya. NimbleFreight Logistics, Mumbai. Tuesday, 2:15 PM. Her driver just sent a voice note from NH-48." | Cut to title card: project name, tagline "AI exception triage for small 3PLs," Google Solution Challenge 2026 logo. Hold 3 seconds. |

**Words:** ~85. **Tone:** Grounded, specific, stakes-first. Do not start with the tech.

#### Beat 2 — The System (0:30 – 1:15)

| Time | Narration | Visual |
|------|-----------|--------|
| 0:30-0:45 | "We built a multi-agent exception triage system on Google's Agent Development Kit. A Coordinator agent receives the exception, delegates to two specialists: a Classifier that uses Gemini 2.5 Flash to identify exception type and severity, and an Impact agent that queries Firestore to compute who is affected and what the revenue risk is." | Clean architecture animation: Coordinator (centre), Classifier (left), Impact (right). Google service logos next to each: ADK, Gemini, Firestore. 15 seconds max on this slide. |
| 0:45-0:55 | "Here is the live system, deployed on Cloud Run. Priya's dashboard is empty — four shipments in transit, no exceptions open." | Cut to live dashboard (Sprint 5 React frontend OR `adk web`). Map of Mumbai→Pune route. Four shipment cards in sidebar. |
| 0:55-1:15 | "She drags in the WhatsApp voice note from driver Ramesh. Gemini multimodal transcribes the Hinglish in one second." | Drag-drop gesture. Voice note waveform renders. Transcript appears below: "Priya madam, truck mein problem ho gaya..." with English translation. |

**Words:** ~130. **Tone:** Confident, technical but grounded by the scenario.

#### Beat 3 — The Disruption (1:15 – 2:00) — CENTREPIECE

| Time | Narration | Visual |
|------|-----------|--------|
| 1:15-1:22 | "The Coordinator fires. Watch the reasoning trace appear in real time." | Click "Triage" button. Right-side panel starts streaming text. |
| 1:22-1:40 | "The Classifier reasons: vehicle breakdown on NH-48, driver safe, mechanic ETA 4 hours. Exception type: carrier_capacity_failure. Severity: CRITICAL. Confidence: 94%. All in 1.2 seconds." | Zoom on Classifier panel. Text streams in. Key fields highlight as they arrive: exception_type, severity, confidence. Timer in top-right: 1.2s. |
| 1:40-2:00 | "The Impact agent picks up the hand-off. It reads Firestore, identifies 4 affected shipments, computes 18.5 lakh rupees at risk, and flags the critical path: BlushBox Beauty's influencer campaign goes live in 19 hours." | Impact panel streams in. Shipments list populates: BlushBox 🔴, KraftHeaven 🟡, CoreCloud 🟢, FitHaus 🟢. Total value card animates to "₹18,50,000." Critical path label lights up. |

**Words:** ~130. **Tone:** Dramatic but evidence-first. Show the actual reasoning, not a fake toast notification.

#### Beat 4 — The Response (2:00 – 2:30)

| Time | Narration | Visual |
|------|-----------|--------|
| 2:00-2:15 | "Total triage time: under 4 seconds. What used to take Priya two to four hours of frantic WhatsApp and Excel work is now a prioritised action list. BlushBox first — brand reputation. KraftHeaven second — Diwali cultural deadline. CoreCloud third, FitHaus last." | Action-list card appears with the 4 shipments in priority order. Timer: 3.8s total. |
| 2:15-2:30 | "She has the next 19 hours to act on an informed picture — not the next 19 hours to build the picture." | Zoom out. Full dashboard view. Coordinator agent badge turns green. Pause 2 seconds. |

**Words:** ~80. **Tone:** Pay-off. Let the viewer feel the time savings.

#### Beat 5 — The Impact (2:30 – 3:00)

| Time | Narration | Visual |
|------|-----------|--------|
| 2:30-2:42 | "This directly supports Sustainable Development Goal 9 — resilient infrastructure for small logistics operators who serve the D2C and SMB economy. And SDG 12 — reducing the cascading waste from missed deadlines, spoiled goods, and failed campaigns." | SDG 9 + SDG 12 icons appear with one-line descriptions. |
| 2:42-2:52 | "Built on Google ADK, Gemini 2.5 Flash, Firestore, Cloud Run, and Firebase Auth. Source code, live URL, and full architecture in the repo." | Tech stack strip: 5 logos with labels. |
| 2:52-3:00 | "Supply chain exceptions do not have to eat a coordinator's day. With the right agents watching, they become a 4-second triage — not a 4-hour scramble." | Closing title card: project name, live URL, repo URL. Hold 3 seconds silent. |

**Words:** ~95. **Tone:** Vision-forward closing line crafted to be memorable.

**Total narration:** ~520 words. At 140 WPM: 3:42 runtime. Tighten in editing to 3:00 by cutting filler words. The core beats 3+4 alone are 75 seconds — this is the 60-90 second core the brief requires. Beats 1+2+5 wrap it into the 2-3 minute total the Solution Challenge allows.

**Non-negotiable phrases** (must appear verbatim): "Under 4 seconds," "no human intervention," "SDG 9," "SDG 12," "₹18,50,000 at risk," "4-second triage — not a 4-hour scramble."

---

### B. Problem Statement Template (400 words)

```
Title: Supply Chain Exception Triage for Small Logistics Operators

The small and medium 3PL (third-party logistics) segment in India and across emerging markets
serves the bottom 80% of shippers that enterprise logistics platforms ignore. These operators —
with 20 to 100 employees, 15 to 50 trucks, and clients ranging from D2C brands to SMB
manufacturers — are responsible for the last mile of every consumer goods flow that touches
daily life. And they run on fragmented, manual, tribal-knowledge-driven systems.

When a shipment breaks — a truck breakdown on a highway, a carrier delay, a customer escalation,
a weather event — the exception coordinator becomes the single point of failure for the company.
Our research from 163 source notes and the five-layer problem model synthesises the pain:

1. Information Fragmentation: 4 to 10 disconnected systems per coordinator. 80% of small 3PLs
   lack any real-time visibility tool.
2. Manual Processing Bottleneck: One disruption triggers 34 manual updates across 6 systems,
   25 emails, 8 roles involved.
3. Tribal Knowledge Trap: Over 4,000 uncodified rules live inside experienced coordinators'
   heads. When they leave, the playbook leaves with them.
4. Reactive Response Loop: Industry average response time is 5 days. 83% of small 3PLs cannot
   respond to an exception within 24 hours.
5. Scale Breaks People: Global logistics administration costs $1 trillion per year. Overhead
   grows non-linearly with shipment volume — coordinators become the ceiling.

Meet Priya. She is 28, a three-year exception coordinator at NimbleFreight Logistics in Mumbai.
Her company serves D2C beauty brands with campaign deadlines, SMB manufacturers with thin
margins, and B2B enterprise clients with SLA penalties. Every day she spends two to four
hours per broken shipment — chasing drivers on WhatsApp, cross-referencing Excel, calling
customers, updating carrier portals. Ninety-plus hours per month lost to the manual mechanics
of triage, not the judgement of triage.

The judgement is where the value is. The mechanics are where the time goes.

This is the problem we solve. Our system automates the mechanics — ingesting unstructured
exception signals, classifying them, computing who and what is affected — and returns the
judgement decision to the coordinator in under 4 seconds. It directly addresses UN Sustainable
Development Goal 9 (resilient, inclusive, sustainable industrial infrastructure) by giving
the underserved 80% of logistics operators the kind of decision-support tooling that is
currently locked behind $100,000-per-year enterprise contracts.

Small 3PLs deserve the same intelligence that keeps global shipping running. We built it
for them.
```

**Word count:** ~395. Adjust ±20 to land in 380-420 window.

---

### C. Solution Brief Template (400 words)

```
Title: Module-Ready Multi-Agent Exception Triage — Tier 1 Prototype

We built an autonomous exception triage system for small 3PL coordinators, powered by Google's
Agent Development Kit orchestrating three specialised AI agents on a clean, modular architecture
we call the "Module-Ready Orchestrator with Progressive Enhancement" (D+F approach, documented
in our Architecture Decision Analysis across 5 thinking-framework reviews — SWOT, pre-mortem,
decision matrix, six hats, MECE).

The Tier 1 prototype runs live on Google Cloud Run at [LIVE_URL]. Source and architecture
diagrams are in [REPO_URL]. A 3-minute demo walkthrough is at [VIDEO_URL].

Architecture, from exception to action:

1. Coordinator Agent (ADK LlmAgent, Gemini 2.5 Flash): Receives the exception event from the
   API layer, enriches with user+company context from Firestore, delegates to specialists.

2. Classifier Agent: Reads the raw exception payload (including transcribed WhatsApp voice
   notes processed by Gemini multimodal), classifies exception_type (carrier_capacity_failure,
   customer_escalation, weather_disruption, etc.), assigns severity and urgency_hours,
   emits a structured ClassificationResult with reasoning trace.

3. Impact Agent: Queries Firestore for shipments affected by the exception, computes
   total_value_at_risk, identifies the critical path based on deadlines and customer tier,
   returns a prioritised action list.

4. Firestore: Multi-tenant data isolation by company_id, real-time state, push-based updates
   for the React dashboard.

5. Firebase Auth: Google Sign-In, verified via firebase-admin SDK server-side with
   custom-claims multi-tenant enforcement.

6. Cloud Run: min_instances=1 for zero cold-start latency during judging, asia-south1
   region for Indian target-market latency under 50ms.

Our anchor demo scenario, the "NH-48 Truck Breakdown": a driver sends a 24-second Hinglish
WhatsApp voice note — "Priya madam, truck mein problem ho gaya..." — from kilometre marker 72
on the Mumbai-Pune highway. Four shipments onboard: a BlushBox Beauty lipstick launch (campaign
goes live in 19 hours), KraftHeaven brass lamps for a Diwali boutique display, CoreCloud server
racks for an enterprise install, and routine FitHaus protein box replenishment. Total value at
risk: ₹18,50,000 (~$22,000 USD). Without our system, Priya spends the next two hours on WhatsApp
and Excel figuring out what to save first. With our system, the prioritised action list is on
her screen in under four seconds: BlushBox first (brand reputation), KraftHeaven second (Diwali
cultural deadline), CoreCloud third, FitHaus last.

Next steps (Tier 2): Resolution Agent with Generator-Judge reasoning, Route Optimization API
integration for automatic carrier-switch proposals, Communication Agent for stakeholder
notifications. Each module is independently testable and platform-ready.
```

**Word count:** ~395. Adjust ±20 to land in window.

---

### D. Project Deck Outline (7 slides)

**Slide 1 — Title**
- Project name: "Supply Chain Exception Triage"
- Tagline: "A 4-second triage — not a 4-hour scramble"
- Builder: [your name], [university], [GDSC chapter]
- Google Solution Challenge 2026 badge
- Live URL + QR code bottom-right

**Slide 2 — Problem**
- Headline: "Exception coordinators spend 40-60% of their day triaging broken shipments"
- 3 stat blocks: "2-4 hrs per exception | 34 manual updates | 83% can't respond in 24h"
- Small persona photo/illustration: "Priya, NimbleFreight Logistics, Mumbai"
- Footer: "The bottom 80% of 3PLs — underserved by $100K+/yr enterprise tools"

**Slide 3 — Solution**
- Headline: "Multi-agent triage on Google ADK"
- Thesis: "Coordinator → Classifier → Impact. 3 agents. 1 pipeline. Under 4 seconds."
- Mermaid/architecture sketch (horizontal flow)
- Tech badges strip: ADK, Gemini, Firestore, Cloud Run, Firebase Auth

**Slide 4 — Demo Screenshots**
- 3 screenshots left-to-right: (a) WhatsApp voice note + transcript panel, (b) Classifier reasoning trace with severity badge, (c) Impact panel with prioritised action list
- Caption: "NH-48 anchor scenario — ₹18.5L value at risk, 4-second triage"
- YouTube thumbnail link bottom-right

**Slide 5 — Architecture**
- Full architecture diagram (from §F) taking 80% of slide real estate
- Labels: data flow, security boundaries, multi-tenant isolation
- Footer: "Module-Ready Orchestrator pattern — see ADR-001 through ADR-018 in repo"

**Slide 6 — Impact + SDG Alignment**
- Left half: SDG 9 icon + "Resilient infrastructure for underserved 3PLs"
- Right half: SDG 12 icon + "Reduced waste from cascading exception failures"
- Bottom strip: 3 target metrics: "Triage time: 4hr → 4s | Coordinator capacity: +60% | Missed SLA reduction: 40%"
- Small italic: "User interviews planned before Top-100 gate (May 29)"

**Slide 7 — Tier Progression + Team**
- Tier 1 (shipped): "Classifier + Impact on NH-48 scenario"
- Tier 2 (May-Jun): "Resolution Agent + Route Optimization API"
- Tier 3 (Jun): "Communication Agent + live ops rollout"
- Team: solo builder info, GDSC affiliation
- Call-to-action footer: "Live URL + repo + video in top navigation"

**Speaker notes** on slides 2-7 provide 1-2 sentences of context that a judge can read if they advance past the video.

---

### E. README Template (final polished)

```markdown
# Supply Chain Exception Triage

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/USER/REPO/actions/workflows/ci.yml/badge.svg)](https://github.com/USER/REPO/actions/workflows/ci.yml)
[![Security](https://github.com/USER/REPO/actions/workflows/security.yml/badge.svg)](https://github.com/USER/REPO/actions/workflows/security.yml)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Google ADK](https://img.shields.io/badge/Google-ADK-4285F4?logo=google)](https://google.github.io/adk-docs/)
[![Gemini](https://img.shields.io/badge/Gemini-2.5_Flash-8E75B2)](https://ai.google.dev/)

> **A 4-second triage — not a 4-hour scramble.** An autonomous AI exception triage system
> for small 3PL logistics coordinators, built on Google's Agent Development Kit.

[**Live MVP**](https://LIVE_URL) · [**Demo Video**](https://YOUTUBE_URL) · [**Deck**](https://SLIDES_URL)

---

## What it does

Small 3PL coordinators spend 40-60% of their day triaging broken shipments across 4-10
disconnected systems. This project automates the mechanics of exception triage — ingesting
unstructured signals, classifying severity, computing impact — and returns a prioritised
action list in under 4 seconds, so coordinators focus their judgement on decisions that
actually matter.

Built for the **Google Solution Challenge 2026**, aligned with **SDG 9** (resilient
infrastructure) and **SDG 12** (responsible production).

## Demo

![Demo](docs/architecture/diagram.png)

Watch the 3-minute walkthrough: **[YouTube](https://YOUTUBE_URL)**

## Architecture

![Architecture](docs/architecture/diagram.png)

Three ADK agents orchestrated by a Coordinator:

- **Classifier Agent** — classifies exception type + severity via Gemini 2.5 Flash
- **Impact Agent** — queries Firestore for affected shipments, computes value at risk
- **Coordinator Agent** — delegates, enriches context, returns unified triage result

Runs on **Google Cloud Run** (asia-south1), real-time state via **Firestore**, auth via
**Firebase** + **Google Sign-In**, React frontend on **Firebase Hosting**.

See [docs/architecture/overview.md](docs/architecture/overview.md) for the deep dive and
[docs/decisions/](docs/decisions/) for the 18 ADRs documenting every decision.

## Quickstart

Requires Python 3.13 and [uv](https://github.com/astral-sh/uv).

```bash
git clone https://github.com/USER/REPO.git
cd REPO
uv sync
cp .env.template .env  # fill in your GCP project id + Gemini API key
make test              # run unit + integration tests
make run               # launch `adk web` locally on :8000
```

See [docs/onboarding/setup.md](docs/onboarding/setup.md) for full environment setup,
Firebase project creation, and Firestore emulator configuration.

## How it works (NH-48 example)

At 2:15 PM Tuesday, a driver sends a 24-second Hinglish WhatsApp voice note from
kilometre marker 72 on NH-48: *"Priya madam, truck mein problem ho gaya..."* Engine
overheat, mechanic 4 hours away, 4 shipments on board worth ₹18,50,000.

The Coordinator fires the Classifier — Gemini 2.5 Flash transcribes, detects
`carrier_capacity_failure / vehicle_breakdown_in_transit`, severity `CRITICAL`, confidence
94%. The Impact agent queries Firestore, surfaces the 4 affected shipments, flags BlushBox
Beauty's influencer campaign (19 hours to deadline) as the critical path.

Total wall-clock triage time: under 4 seconds. Priya now spends the next 19 hours acting
on an informed picture — not building it.

See [docs/onboarding/nh48-scenario.md](docs/onboarding/nh48-scenario.md) for the full
walkthrough with expected agent outputs.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Agent orchestration | Google ADK (multi-agent Coordinator pattern) |
| AI reasoning | Gemini 2.5 Flash |
| Real-time state | Firestore (asia-south1) |
| Authentication | Firebase Auth + Google Sign-In (firebase-admin SDK) |
| API | FastAPI + Server-Sent Events streaming |
| Deployment | Cloud Run (min_instances=1) |
| Frontend | React + Firebase Hosting |
| Secrets | Google Secret Manager |

## SDG Alignment

**SDG 9 — Industry, Innovation and Infrastructure** (primary): Gives small 3PLs
decision-support tooling previously locked behind $100K+/year enterprise contracts.
Directly supports Target 9.1 (quality, reliable, sustainable, resilient infrastructure).

**SDG 12 — Responsible Consumption and Production** (secondary): Reduces cascading waste
from missed SLAs, spoiled perishables, and failed marketing campaigns. Every prevented
late delivery is reduced demurrage, less emergency freight, less carbon.

User interviews with three real coordinators planned before Top-100 advancement (May 29)
per our [deferred-gap tracker](docs/submission/user-feedback-gap.md).

## Testing

```bash
make test             # unit + integration with Firestore emulator
make coverage         # coverage report (target: 80%+)
make lint             # ruff + mypy + bandit
```

Security scanning runs nightly via `.github/workflows/security.yml`.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). For AI coding agents, see [AGENTS.md](AGENTS.md).

## License

MIT — see [LICENSE](LICENSE).

## Acknowledgements

Built for the [Google Solution Challenge 2026](https://developers.google.com/community/gdsc-solution-challenge)
as a Google Developer Student Clubs submission. Research foundation of 163+ notes across
6 supply chain sub-domains.
```

---

### F. Architecture Diagram Specification

**Purpose:** Single diagram that communicates the full Tier 1 prototype architecture at a glance. Used in README, deck slide 5, problem statement header, and portal submission.

**Tool:** **Excalidraw** (primary) or Mermaid (fallback). Excalidraw chosen because:
- Hand-drawn aesthetic feels human and memorable (anti-generic)
- Exports to PNG at any resolution
- Version-controllable as `.excalidraw` JSON
- The vault already has Excalidraw MCP tooling set up

**Resolution:** 1920×1080 PNG minimum (for slide fill). Vector export (SVG) for README embedding.

**Content layers (top to bottom):**

1. **User layer** — browser icon labelled "Priya / React Dashboard (Firebase Hosting)"
2. **Edge layer** — Firebase Auth icon, Google Sign-In callout, arrow labelled "ID Token"
3. **API layer** — Cloud Run rectangle containing FastAPI + SSE streaming box
4. **Agent layer** — 3 rounded rectangles inside a "Google ADK" dashed boundary:
   - Coordinator (centre, top) — Gemini 2.5 Flash
   - Classifier (left) — Gemini 2.5 Flash, labelled "exception_type + severity"
   - Impact (right) — Gemini 2.5 Flash, labelled "value at risk"
5. **Data layer** — Firestore cylinder (asia-south1), labelled collections: `companies/{id}/exceptions`, `companies/{id}/shipments`, `companies/{id}/users`
6. **Secrets layer** — Google Secret Manager lock icon connected dashed-line to API layer

**Arrows:**
- Browser → Firebase Auth (authenticate)
- Browser → Cloud Run (POST /triage/stream, bearer token)
- Cloud Run → Coordinator (invoke)
- Coordinator ⇄ Classifier (delegate + result)
- Coordinator ⇄ Impact (delegate + result)
- Impact ⇄ Firestore (read shipments)
- Coordinator → Cloud Run → Browser (SSE stream)

**Colours:** Google brand-inspired but not logo-infringing:
- Coordinator: `#4285F4` (Google blue)
- Classifier: `#34A853` (Google green)
- Impact: `#34A853` (Google green)
- Firestore: `#FBBC05` (Google yellow)
- Cloud Run: `#4285F4` (Google blue)
- Firebase: `#FFA000` (Firebase amber)

**Labels:** Every arrow has a verb. Every component has a one-word role. No unexplained acronyms.

**Save to:**
- Source: `docs/architecture/diagram.excalidraw`
- Export PNG: `docs/architecture/diagram.png` (1920×1080)
- Export SVG: `docs/architecture/diagram.svg` (scalable for deck)

---

### G. Demo Video Recording Checklist (OBS)

**Environment pre-stage (30 min before recording):**

- [ ] Close Slack, Discord, email — any notification source
- [ ] Enable Do Not Disturb on OS
- [ ] Close all browser tabs except: (a) live dashboard, (b) architecture diagram tab for Beat 2, (c) closing title card tab for Beat 5
- [ ] Browser zoom 110% for readability at 1080p
- [ ] Dev tools closed (no red console badges)
- [ ] Fullscreen browser on the recording display
- [ ] Warm the Cloud Run URL twice with `curl` to skip cold-start
- [ ] Seed NH-48 fixture into Firestore via `scripts/seed_nh48.py`
- [ ] Open architecture PNG in preview tool at native resolution
- [ ] Close VS Code, terminal windows, file explorer — only the browser is visible

**OBS Studio configuration:**

- [ ] Output resolution: **1920×1080** (1080p)
- [ ] FPS: **30** (60 is overkill for screen recording and doubles file size)
- [ ] Encoder: **x264**, CPU preset **medium**, rate control **CBR** 8000 Kbps
- [ ] Audio sample rate: **48 kHz**
- [ ] Audio bitrate: **192 Kbps**
- [ ] Mic-Aux channel: your USB mic (NOT laptop built-in) — test with "Test Audio" meter, peaks should land -12 to -6 dB
- [ ] Recording format: **MP4** (not FLV — MP4 is portable and YouTube-friendly)
- [ ] Scene 1: "Browser full" — Display Capture of primary monitor, cropped to browser if needed
- [ ] Scene 2: "Voiceover only" — no video source, just microphone (for separate audio-only passes)
- [ ] Hotkey for "Start/Stop Recording" set to a key you will not hit accidentally

**Audio recording (5 passes, one per beat):**

- [ ] Record Beat 1 voiceover in Scene 2. Do 3 takes. Save cleanest as `beat-1.wav`.
- [ ] Repeat for Beats 2-5.
- [ ] Listen back to all 5 tracks back-to-back. Verify consistent tone, volume, pace.
- [ ] Run each through Audacity Noise Reduction + Normalise to -3 dB peak.

**Screen recording (5 passes, one per beat, matching voiceover):**

- [ ] For each beat, play the voiceover in one earpiece, perform the on-screen actions in time with the narration. Do NOT speak.
- [ ] 3 takes per beat, keep cleanest. Save as `screen-1.mp4` through `screen-5.mp4`.
- [ ] For Beat 3 (Disruption centrepiece), budget extra takes — this is the most complex sequence.

**Edit pass (DaVinci Resolve free OR CapCut):**

- [ ] Import all voiceover and screen clips onto a 1080p 30fps timeline
- [ ] Layer each beat's voiceover over its matching screen clip
- [ ] Trim dead air at beat boundaries
- [ ] Add 0.5s fade-in/fade-out between beat transitions
- [ ] Overlay title card PNG for first 3 seconds
- [ ] Overlay closing card PNG for last 3 seconds
- [ ] Normalise master audio track to -14 LUFS (YouTube standard) or -16 LUFS (conservative)
- [ ] Export: MP4, H.264, 1080p, AAC audio, **CRF 23** (good quality, reasonable file size)
- [ ] Target file size: ≤100 MB for 3-minute video (aggressive) or ≤200 MB (comfortable)

**Upload pass:**

- [ ] YouTube: upload as **Unlisted**, title = project name + "— Google Solution Challenge 2026 demo", description = one-paragraph pitch + live URL + repo URL
- [ ] Google Drive: upload to a dedicated `submission/` folder, set sharing to **Anyone with the link can view**
- [ ] Copy both URLs into `docs/submission/portal-answers.md`

---

### H. Submission Portal Upload Checklist

Based on historical Solution Challenge submission forms and the [vision.hack2skill.com Solution Challenge 2026 portal](https://vision.hack2skill.com/event/solution-challenge-2026). Exact fields may vary — verify against the live portal on Apr 22.

**Pre-upload preparation (Apr 23 evening):**

- [ ] Create `submission-bundle/` local directory
- [ ] Copy `problem-statement.md` → `submission-bundle/problem-statement.pdf` (export from markdown)
- [ ] Copy `solution-brief.md` → `submission-bundle/solution-brief.pdf`
- [ ] Export `project-deck.pptx` → also save as PDF (portal may require PDF)
- [ ] Save final `demo-video.mp4` → `submission-bundle/demo-video.mp4` (backup if portal upload fails)
- [ ] Create `submission-bundle/links.txt` with:
  ```
  Live MVP: https://LIVE_URL
  GitHub Repo: https://github.com/USER/REPO
  Demo Video (YouTube): https://youtu.be/XXXX
  Demo Video (Drive): https://drive.google.com/XXXX
  Project Deck (Google Slides): https://docs.google.com/presentation/XXXX
  Problem Statement: link to GitHub file
  Solution Brief: link to GitHub file
  ```

**Portal fields (ordered by typical submission form):**

- [ ] **Team/Participant name** — verify matches GDSC chapter records
- [ ] **Team email** — use the one linked to your Google Developer profile
- [ ] **GDSC chapter** — exact chapter name, case-sensitive
- [ ] **Project title** — "Supply Chain Exception Triage"
- [ ] **Short tagline** (1 line, ≤100 chars) — "A 4-second triage, not a 4-hour scramble — multi-agent ADK for small 3PLs"
- [ ] **Problem category / SDG primary** — SDG 9 (Industry, Innovation and Infrastructure)
- [ ] **Problem category / SDG secondary** — SDG 12 (Responsible Consumption and Production)
- [ ] **Problem statement** (text box or file upload) — paste problem-statement.md content or upload PDF
- [ ] **Solution brief** — paste or upload
- [ ] **Demo video link** — YouTube URL (primary), Drive URL (backup in notes field)
- [ ] **GitHub repo link** — https://github.com/USER/REPO (verify public)
- [ ] **Live MVP link** — Cloud Run URL (verify returns 200 right before submitting)
- [ ] **Project deck link** — Google Slides public-view URL (verify access in incognito browser first)
- [ ] **Google technologies used** — checkbox list: ADK, Gemini, Firestore, Cloud Run, Firebase Auth, Firebase Hosting, Secret Manager
- [ ] **Team size** — 1 (solo) or whatever your actual team count is
- [ ] **Country** — India (or as applicable)
- [ ] **Any additional notes** — mention: "Live URL cold-start-optimised with min_instances=1; demo-video also hosted on Drive as backup: [link]"

**Submit action:**

- [ ] Click "Submit" **one time only**
- [ ] Wait for success page — do NOT refresh
- [ ] Screenshot the success page (Snipping Tool / Shift+Win+S)
- [ ] Save screenshot as `docs/submission/confirmation.png`
- [ ] Save confirmation email as PDF → `docs/submission/confirmation.txt`
- [ ] Git commit these confirmation artifacts: `git commit -m "docs: archive submission confirmation"`
- [ ] Tag release: `git tag v1.0.0-submission && git push --tags`

**Post-submit:**

- [ ] Do NOT modify the GitHub repo for 24 hours (judges may clone at any time)
- [ ] Do NOT change deployment (live URL must stay up)
- [ ] Monitor Cloud Run logs for incoming judge traffic (optional signal)

---

### I. Final Code Review Checklist

Run via `superpowers:code-reviewer` skill on the full Sprint-0-to-5 diff (`git diff v0.0.0..HEAD`). Triage findings into 3 buckets:

**Critical — must fix before submission:**

- [ ] Any secret committed to git history (API keys, service account JSON, passwords)
- [ ] Any unauthenticated endpoint that exposes PII or write access
- [ ] Firestore security rules missing `request.auth != null` enforcement
- [ ] CORS wildcarded to `*` in production config
- [ ] `debug=True` or dev-mode flag shipping in production build
- [ ] Any TODO with "hardcoded" or "temporary" in the body
- [ ] Broken test in the main branch CI

**Medium — document in review.md, ship with caveat:**

- [ ] Test coverage below 70% on new Sprint-1-to-4 code
- [ ] Any ADR not yet written for a decision that was made
- [ ] Docstrings missing on public API surface
- [ ] Any pytest warning that was not addressed
- [ ] Dependency older than one minor version behind latest

**Low — retrospective follow-up:**

- [ ] Code style nits (ruff-autofixable)
- [ ] Minor duplication that does not affect behaviour
- [ ] Variable naming inconsistencies
- [ ] Logs that are too verbose

**Manual additional checks beyond the automated skill:**

- [ ] `git log -p | grep -iE "api[_-]?key|secret|password|token|private"` returns nothing incriminating
- [ ] `detect-secrets scan --all-files` clean
- [ ] `bandit -r src/` no high-severity
- [ ] `safety check` no known CVEs
- [ ] `pip-audit` no CVEs
- [ ] `ruff check src/ tests/` clean
- [ ] `mypy src/` clean (or documented ignores)
- [ ] `pytest` all green in CI on main branch

---

### J. SDG Alignment Statement

```markdown
## SDG Alignment — Supply Chain Exception Triage

### SDG 9 — Industry, Innovation and Infrastructure (PRIMARY)

**Target 9.1:** Develop quality, reliable, sustainable and resilient infrastructure to
support economic development and human well-being, with a focus on affordable and equitable
access for all.

**How our solution contributes:** Small and medium 3PL logistics operators serve the bottom
80% of shippers — D2C brands, SMB manufacturers, local retailers — who are priced out of
enterprise exception-management platforms (FourKites, project44, Kinaxis all starting at
$100,000+ per year). Our system brings autonomous triage within reach of a solo exception
coordinator running on a cloud instance that costs under $30/month to operate. This
directly advances equitable access to resilient logistics infrastructure in emerging markets
where small 3PLs are the backbone of the consumer goods supply chain.

**Target metric (pre-user-interview estimate):** Reduce average triage time per exception
from 2-4 hours to under 4 seconds for structured inputs, increasing coordinator capacity by
approximately 60% (based on time-motion analysis from the research corpus).

### SDG 12 — Responsible Consumption and Production (SECONDARY)

**Target 12.3:** Halve per capita global food waste at the retail and consumer levels and
reduce food losses along production and supply chains.

**Target 12.5:** Substantially reduce waste generation through prevention, reduction,
recycling and reuse.

**How our solution contributes:** Missed shipment SLAs cascade into waste — spoiled
perishables, expired marketing windows, returned goods, emergency air-freight with 10×
the carbon footprint of sea-freight. Faster exception response means fewer cascading
failures. When Priya can identify the BlushBox Beauty campaign deadline as the critical
path in 4 seconds instead of 2 hours, the probability of a successful reroute stays high
and the cascading waste of a failed campaign (product write-offs, media ad spend loss,
emergency replacement shipments) is prevented.

**Target metric (pre-user-interview estimate):** 40% reduction in missed-SLA cascading
failures through earlier triage on exceptions, measured over a 3-month rolling window.

### SDG framing notes

We intentionally chose SDG 9 as primary over the more-common SDG 3 (Health) and SDG 4
(Education) submissions per our competitor analysis of past Solution Challenge winners:
SDG 9 is underrepresented in submissions, which means our entry fills a diversity gap the
judges are actively looking for. Our secondary SDG 12 anchors the environmental story
without overreaching into SDG 13 (Climate Action), which our Tier 1 prototype does not yet
quantify (Tier 2's Route Optimization API integration will add that).

### User feedback evidence

**Status: Deferred gap.** Per our sprint plan's explicit acknowledgement, three real-user
interviews were deferred past the Round 1 submission in favour of building a complete
working prototype. We commit to completing three interviews with real small-3PL exception
coordinators before the Top-100 advancement gate on May 29, 2026. Our target interviewees
are Mumbai-based small 3PL operators sourced via the Supply Chain and Logistics Council
of India and personal network referrals. Interview questions and output format are
specified in `docs/submission/user-feedback-plan.md`.
```

---

## 13. Rollback Plan

**If the live URL is broken on Apr 24 morning:**
1. Rollback to last-known-good Cloud Run revision via `gcloud run services update-traffic`
2. If that fails, redeploy from the `v1.0.0-submission` tag
3. If deployment fails, submit with the video as the "live evidence" and note in portal that "live URL intermittent — full recorded walkthrough in video"

**If the demo video cannot be recorded cleanly (audio issues, OBS crash, time budget blown):**
1. Use static screenshots from the live dashboard + voice-over only as a 2-minute slideshow
2. Produce via Google Slides → record with OBS in Slide Show mode
3. Trade polish for completion — a working submission beats a missing video

**If the fresh-clone test fails on your OS:**
1. Document the workaround in `docs/onboarding/setup.md` with a `Known Issues` section
2. Pre-provision a public Docker image that contains the working environment
3. Add the Docker `docker run` command as an alternative quickstart path

**If `superpowers:code-reviewer` finds a Critical issue at 17:00 Apr 23:**
1. Hotfix only the Critical issue on a single branch
2. Run minimum test suite (unit + live URL smoke)
3. Deploy the hotfix
4. If hotfix takes >2 hours, revert and submit with the issue documented in the ADR

**If the submission portal fails to accept uploads:**
1. Document the error with screenshot
2. Fall back to emailing the GDSC Solution Challenge team with all artifacts attached
3. Save the email as proof-of-submission-attempt

**If the user-interview gap becomes a hard blocker (unlikely for Round 1):**
1. Run 3 lightning-fast interviews via WhatsApp with personal network contacts on Apr 23 evening
2. Capture 3 quotes (can be 1-2 sentences each)
3. Add them to `docs/submission/user-feedback.md` and reference in the solution brief

---

## 14. Cross-References

### Vault context
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — 7-sprint plan that this sprint concludes
- [[Supply-Chain-Product-Recap]] — Living product overview; source for problem-statement content
- [[Supply-Chain-Demo-Scenario-Tier1]] — NH-48 anchor scenario; source for all demo examples
- [[Supply-Chain-Judging-Strategy]] — Rubric analysis; guides artifact coherence strategy
- [[Supply-Chain-Demo-Video-Strategy]] — 5-beat video structure; parent of Template A
- [[Supply-Chain-Demo-Script]] — 3-minute beat-by-beat base script; Template A is the Tier 1 adaptation
- [[Supply-Chain-Video-Production-Hackathon-Demos]] — OBS production techniques; source for Template G
- [[Supply-Chain-Competitor-Analysis]] — Past winner DNA; guides differentiation framing
- [[Supply-Chain-SDG-Impact]] — SDG 9 + 12 framing; source for Template J
- [[Supply-Chain-Innovation-Differentiation]] — novelty-of-approach framing
- [[Supply-Chain-Google-Ecosystem-Leverage]] — Google service selection rationale

### Prior sprint PRDs
- `sprint-0/prd.md` — Foundation + Security + Docs Infrastructure (ADRs 001-007)
- `sprint-1/prd.md` — Classifier Agent
- `sprint-2/prd.md` — Impact Agent + Firestore
- `sprint-3/prd.md` — Coordinator + Full Pipeline
- `sprint-4/prd.md` — API Layer + Streaming + Security Hardening
- `sprint-5/prd.md` — Cloud Run Deploy + React Frontend (ADRs 016-017)

### Related documents
- `docs/decisions/adr-018-submission-artifacts.md` — this sprint's ADR
- `docs/decisions/adr-001-framework-choice.md` through `adr-017` — cited in README and deck

---

## 15. Research Citations

Every non-obvious claim in this PRD and its templates is backed by a citation below.

### Google Solution Challenge 2026 — official

1. [Google Solution Challenge Official Page](https://developers.google.com/community/gdsc-solution-challenge) — program overview
2. [Google Solution Challenge Timeline](https://developers.google.com/community/gdsc-solution-challenge/timeline) — deliverables, rubric, deadlines
3. [Solution Challenge Terms & Conditions](https://developers.google.com/community/gdsc-solution-challenge/terms) — submission requirements
4. [2023 Solution Challenge FAQ](https://developers.google.com/community/gdsc-solution-challenge/faq) — historical submission process
5. [GDSC Solution Challenge Winners](https://developers.google.com/community/gdsc-solution-challenge/winners) — past winner analysis
6. [Solution Challenge 2026 — Hack2skill portal](https://vision.hack2skill.com/event/solution-challenge-2026) — submission portal (2026)
7. [Google Solution Challenge 2026 — PromptWars overview](https://promptwars.in/solutionchallenge2026.html) — program summary
8. [Google Solution Challenge 2026 — EduLinkUp blog](https://edulinkup.dev/blog/google-solution-challenge-2026-your-chance-at-bagging-1000000) — eligibility and process
9. [2024 Solution Challenge Blog](https://developers.googleblog.com/solution-challenge-2024-using-google-technology-to-address-un-sustainable-development-goals/) — 2024 evaluation approach
10. [Meet the 2024 Winners](https://blog.google/technology/developers/meet-the-students-that-are-changing-the-world-through-technology/) — winning patterns

### Past winner analysis

11. [Announcing the 2023 Top 3](https://blog.google/technology/developers/google-student-developer-clubs-solution-challenge-2023/) — Wonder Reader, BuzzBusters, HeadHome
12. [Wonder Reader analysis — Binus International](https://international.binus.ac.id/computer-science/2023/08/03/wonder-reader-indonesias-first-representative-in-the-top-3-of-google-solution-challenge-2023/) — what made Wonder Reader win
13. [Wonder Reader — Tempo](https://tekno.tempo.co/read/1756173/wonder-reader-wakil-indonesia-pertama-pada-top-3-google-solution-challenge-2023) — technical details
14. [Top 3 Winning Strategies — Country Director of Google Korea](https://medium.com/@cliceleee/google-solution-challenge-top-3-winning-strategies-praised-by-the-country-director-of-google-korea-f5496f70e910) — winning strategy patterns

### Demo video production

15. [6 Tips for making a winning hackathon demo video — Devpost](https://info.devpost.com/blog/6-tips-for-making-a-hackathon-demo-video) — canonical Devpost tips
16. [Video-making best practices — Devpost Help Center](https://help.devpost.com/article/84-video-making-best-practices) — production specifics
17. [Creating the Best Demo Video for a Hackathon — Hackathon.com](https://tips.hackathon.com/article/creating-the-best-demo-video-for-a-hackathon-what-to-know) — 60-90 second narrative structure
18. [How to Give a Killer Pitch or Hackathon Demo — Nader Dabit gist](https://gist.github.com/dabit3/caef5eee4753dd7d23767bc31e70da28) — pitch structure
19. [How to Win a Hackathon Pitch — LinkedIn](https://www.linkedin.com/pulse/how-win-hackathon-pitch-david-beckett) — narrative arc tactics
20. [I Let AI Produce My Entire Hackathon Demo Video — Tamir Dresher](https://www.tamirdresher.com/blog/2026/03/05/ai-produced-demo-video) — 2026 AI-assisted production techniques
21. [Perfecting Your Hackathon Submission — Colosseum](https://blog.colosseum.com/perfecting-your-hackathon-submission/) — submission workshop insights
22. [Pitch Perfect — BizThon](https://medium.com/@BizthonOfficial/pitch-perfect-how-to-present-your-hack-like-a-pro-1104430a5d93) — pitch structure for judges

### Pitch deck structure

23. [How to Create a Winning Hackathon Pitch in 5 Steps — TAIKAI](https://taikai.network/en/blog/how-to-create-a-hackathon-pitch) — 5-step pitch structure
24. [Hackathon Pitch Deck Best Practices — Free Power Point Templates](https://www.free-power-point-templates.com/articles/how-to-make-a-hackathon-presentation/) — slide structure
25. [Problem Slide Pitch Deck Best Practices — OpenVC](https://www.openvc.app/blog/problem-slide) — problem slide patterns
26. [Pitch Deck — Inter-University GenAI Hackathon for SDGs](https://www.hack4sdg.com/pitch-deck/) — SDG-aligned pitch structure

### README and AGENTS.md conventions

27. [AGENTS.md — a README.md for agents — Medium](https://medium.com/@ramunarasinga/agents-md-a-readme-md-for-agents-1c22bf447635) — AGENTS.md 2026 convention
28. [How to teach your coding agent with AGENTS.md — Eric J. Ma](https://ericmjl.github.io/blog/2025/10/4/how-to-teach-your-coding-agent-with-agentsmd/) — AGENTS.md structure
29. [Your AI Agent Doesn't Care About Your README — DAPLab Columbia](https://daplab.cs.columbia.edu/general/2026/03/31/your-ai-agent-doesnt-care-about-your-readme.html) — separation of human vs agent docs
30. [Crafting README Files for Efficient AI-Assisted Coding — Ben Houston 3D](https://benhouston3d.com/blog/crafting-readmes-for-ai) — AI-friendly README structure
31. [ReadMe.LLM arXiv paper](https://arxiv.org/html/2504.09798v2) — framework for LLM-friendly library docs
32. [shields.io](https://shields.io/) — badge service reference
33. [GitHub README Badges Guide — GitBlend](https://gitblend.com/kb/github-readme-badges-guide) — badge conventions
34. [Coverage Badge with GitHub Actions — DEV Community](https://dev.to/thejaredwilcurt/coverage-badge-with-github-actions-finally-59fa) — coverage badge tutorial

### Problem statement and SDG alignment

35. [Crafting Effective Problem Statements for Hackathons — HackerEarth](https://www.hackerearth.com/blog/developers/how-to-create-effective-problem-statements-for-idea-challenges-and-hackathons/) — problem statement structure
36. [Top Hackathon Problem Statements 2026 — The New Views](https://thenewviews.com/problem-statement-for-hackathon/) — 2026 problem statement patterns
37. [What are Hackathon Problem Statements — Unstop](https://unstop.com/blog/hackathon-problem-statements-samples) — problem statement guide
38. [UN Sustainable Development Goals Framework](https://sdgs.un.org/goals) — SDG 9 and SDG 12 target definitions

---

## 16. Open Assumptions

Items that need user confirmation before Day 1 (Apr 22) begins:

1. **Sprint 5 output assumption** — This PRD assumes Sprint 5 ships (a) a working Cloud Run live URL with NH-48 as the default scenario, (b) either a React frontend OR an `adk web` instance judges can interact with, (c) ADRs 016 and 017 documented. If any of these is missing, Sprint 6 Day 1 needs 2 extra hours for Sprint-5-fallback work.

2. **Video length interpretation** — The PRD targets 90s core + 180s total. If the 2026 portal specifies a hard "2-minute maximum" (historical value from 2024), cut Beats 1 and 5 to tighten to 120s total. If the portal allows 3 minutes (2023 allowance), keep 180s. **Verify on the portal the morning of Apr 22.**

3. **Deck format** — Google Slides view-link + `.pptx` export is the assumption. If the portal requires PDF-only, export both and upload the PDF to the portal while linking the Google Slides version in the notes field.

4. **Solo vs team** — This PRD assumes solo builder (matches user profile in MEMORY.md). If teammates join by Apr 22, split the Day 1 morning doc work across people and still record the video together Day 1 afternoon.

5. **GDSC chapter** — The portal will ask for your GDSC chapter. Verify the exact chapter name and that you are an active member as of Apr 22. The submission is invalid without active GDSC membership per [Solution Challenge Terms](https://developers.google.com/community/gdsc-solution-challenge/terms).

6. **Live URL min-instances cost** — `min_instances=1` on Cloud Run costs ~$5/month. This PRD assumes the user has already agreed to this cost in Sprint 5. If budget becomes an issue, lower to `min_instances=0` and accept a ~3-5 second cold-start for judges (acceptable trade-off, but degrades live-URL smoke test margin).

7. **User interview last-minute rescue** — If the user decides on Apr 22 morning to close the user-interview gap, Rollback Plan §13 provides a 3-WhatsApp-interview fast path. Flag this decision explicitly to avoid scope creep.

8. **OBS vs alternative recording tools** — Template G assumes OBS Studio. If the user prefers Loom, Screen Studio, or CapCut for recording, the principles (separate audio/video tracks, 1080p30, pre-staged environment) remain the same — only the tool mapping changes.

9. **Cloud Run region** — asia-south1 (Mumbai) per ADR-017. This is the right call for Indian target market but adds ~150ms latency for US judges. If the judge mix is known to be primarily US, consider a secondary deployment — but this is Tier 2 work, not Sprint 6.

10. **Repo public-flip timing** — When does the private GitHub repo become public? This PRD assumes it happens Day 2 afternoon after the detect-secrets scan. Confirm the exact time so the live URL environment variables (e.g., API keys referenced from Secret Manager) do not become discoverable via the repo history.

---

**End of Sprint 6 PRD.**
