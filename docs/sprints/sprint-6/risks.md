---
title: "Sprint 6 Risks — Submission Package (Pre-Mortem)"
type: deep-dive
domains: [supply-chain, hackathon, risk-management]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[sprint-6/prd]]", "[[sprint-6/test-plan]]", "[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]"]
---

# Sprint 6 Risks — Pre-Mortem

> **Companion to `sprint-6/prd.md` and `sprint-6/test-plan.md`. Written using the Pre-Mortem technique: assume Sprint 6 has failed and the Apr 24 submission did not go out (or went out broken). Work backward through every plausible cause.**

---

## Pre-Mortem Framing

> *"It is April 25, 2026. The Google Solution Challenge submission either (a) did not get filed before the Apr 24 23:59 IST deadline, or (b) got filed but was rejected / scored poorly because of a packaging issue, not because the underlying code was bad. Why did this happen?"*

Every risk below is one answer to that question. For each, we record: probability (L/M/H), impact severity (L/M/H/Critical), primary mitigation (already in the plan), and residual risk (what survives after mitigation).

---

## R-01 — Demo video re-records blow the time budget

**Failure mode:** Solo builder spends 8 hours on Day 1 afternoon recording and re-recording the demo video. First takes have audio clipping, second takes have a browser notification pop up, third takes have the Cloud Run cold-start causing dead air. By 22:00 Day 1, the video is still not done, and Day 2 tasks slip into Day 3, pushing submission to the wire.

**Probability:** **High.** Solo video production with no prior experience is universally time-consuming.

**Severity:** **High.** Missed video = missed submission.

**Root causes:**
- No pre-stage checklist followed → notifications / unwanted tabs visible
- Recording voiceover and screen together instead of separately → every mistake forces re-takes of both
- No warm-up pass of the live URL → cold-start latency visible on camera
- Perfectionist loop on cosmetic details (a button slightly misaligned)

**Mitigations (in PRD):**
- Template G mandates separate audio and screen recording passes
- Pre-stage checklist disables notifications and closes every non-essential tab
- Warm the Cloud Run URL with `curl` twice before recording
- Day 1 has a hard soft-stop at 22:00 — if not done, accept "good enough v1" and continue Day 2

**Residual risk:** Medium. Mitigations reduce probability to ~40% but cannot eliminate it. Template G's biggest lever is the "separate audio/video" rule — first-timers who try to do both at once always lose.

**If it fires:** Fall back to the Rollback Plan §13 — static screenshots + voice-over slideshow. This takes 90 minutes to produce instead of 4 hours.

---

## R-02 — Live URL breaks on judge day

**Failure mode:** On Apr 25 a judge clicks the Cloud Run URL in the submission and gets a 502 or the app hangs. This happens because (a) Cloud Run cold-starts exceeded the judge's patience window, (b) a Firestore index build is in progress, (c) the service account hit a Gemini API quota, or (d) the deployed revision was accidentally rolled back.

**Probability:** **Medium.** Cloud Run with `min_instances=1` is reliable but not bulletproof.

**Severity:** **Critical.** Live URL is the single most-judged artifact after the video.

**Root causes:**
- `min_instances=1` costs money; might be accidentally set to 0 to save $5
- Gemini API free-tier quota exhausted silently
- Firebase Auth custom-claims misconfigured after sprint-5 frontend change
- CORS or CSP headers too strict for the judge's browser

**Mitigations (in PRD):**
- Sprint 5 verifies `min_instances=1` is persisted
- Day 3 morning (Apr 24 10:00) re-runs the smoke test before portal upload
- `docs/sprints/sprint-6/impl-log.md` records which revision is the "submission revision"
- Rollback plan documents how to restore the last-known-good revision

**Residual risk:** Medium-High even after mitigations, because the failure could happen hours or days AFTER submission when the builder is not watching.

**Extra mitigations to add to the PRD:**
- Uptime Kuma or GCP Cloud Monitoring alert on the `/health` endpoint pinging every 5 minutes from Apr 24 through May 29
- Sentry for runtime exceptions so post-submission failures are visible

**If it fires:** The demo video becomes the judge's primary evidence. Document the outage and restore ASAP.

---

## R-03 — Fresh clone test fails on a judge's OS

**Failure mode:** A judge who is technically curious (there are a few every year) clones the repo to a Mac laptop and `make setup` fails because of a path separator, a Homebrew missing dependency, or Python 3.13 not being the default on macOS. They score the project lower on "scalability potential" because the code does not even run on their machine.

**Probability:** **Medium.** Our test suite covers Linux; macOS is untested.

**Severity:** **Medium.** Most judges will not clone the repo at all; the few who do are disproportionately the technical ones whose opinion matters.

**Root causes:**
- No macOS CI matrix
- Assumed Python 3.13 is available (macOS default is older)
- Firestore emulator has different download mechanics on macOS

**Mitigations (in PRD):**
- TC-04 runs the test in a Docker container so results are reproducible
- `docs/onboarding/setup.md` includes a "Known Issues" section for macOS
- Alternative Docker-based quickstart documented in README

**Residual risk:** Low-Medium. If the Docker quickstart works, the macOS path is moot.

**Extra mitigation to add:** Add a macOS runner to `.github/workflows/ci.yml` in Sprint 6 Day 2 if time permits (NOT a blocker).

**If it fires:** Hope the judge reads the Known Issues section. No real-time fix possible after submission.

---

## R-04 — Secrets leaked in video, deck, repo, or git history

**Failure mode:** The demo video shows a `.env` file for 2 frames during a tab switch, revealing a Gemini API key. OR a committed `service-account.json` survives in git history. A scraper discovers the key within hours, the Gemini quota is exhausted, and the live URL starts returning quota errors before the Top-100 announcement. Worse case: the key is abused for unrelated purposes and GCP bills pile up.

**Probability:** **Low-Medium.** Pre-commit detect-secrets hook from Sprint 0 catches most cases, but video leaks are harder to catch automatically.

**Severity:** **Critical.** Financial + reputation loss.

**Root causes:**
- Video recording accidentally captures a terminal or file explorer window
- Old git commit contains a secret that was "fixed" in a later commit but not purged from history
- `.env.example` accidentally committed with real values instead of placeholders
- IAM policy too permissive on the exposed key

**Mitigations (in PRD):**
- Template G mandates closing VS Code and terminal before recording
- TC-10 runs `detect-secrets` and history grep as a hard gate
- Security considerations §6 in the PRD lists the full threat surface
- `.env` is in `.gitignore` from Sprint 0

**Residual risk:** Medium. Video capture leaks are the hardest to prevent because OBS sees the whole screen.

**Extra mitigation to add:**
- Before recording, run a "secret-free screen" audit: open every window you plan to show, verify none contains a key
- After video editing, scrub the timeline at 0.5× speed looking for any frame with suspicious content
- If a leak is discovered post-recording, rotate the key immediately and re-upload the video

**If it fires post-submission:** Rotate all keys within 1 hour. Force-push a clean git history. Re-deploy. File an amended submission if the portal allows.

---

## R-05 — Submission portal rejects files or has an unexpected field

**Failure mode:** It is Apr 24 21:00 IST. The builder opens the portal for final upload. A field asks for "Business model canvas PDF" (not on our checklist). Another field has a 10MB video file-size limit and our video is 95MB. The portal has a 500 error. The builder panics.

**Probability:** **Medium.** Portal specifics can change year-over-year without public warning.

**Severity:** **High.** Can delay submission past deadline.

**Root causes:**
- Portal updated after research was done (the 2026 portal at hack2skill.com may differ from historical Devpost/Google forms)
- Unexpected mandatory field discovered at the last moment
- File size or format validation stricter than expected

**Mitigations (in PRD):**
- Day 2 17:00-18:00 is dedicated to a portal dry-run. Walk through every field, save as draft.
- Video is hosted on YouTube + Drive so only a link (not a file) goes to the portal
- Deck is a Google Slides link with `.pptx` backup
- `docs/submission/portal-answers.md` is updated in real time during the dry-run

**Residual risk:** Low. Dry-run catches 90% of surprises.

**Extra mitigation to add:**
- Check the portal on Apr 22 **morning** (not just Apr 23 afternoon) — gives one more day to react to surprises
- Screenshot the full portal form for reference in case it changes mid-sprint

**If it fires Apr 24 night:** Rollback plan §13 — email the Solution Challenge team all artifacts with a "portal error" note. Screenshot the error for audit trail.

---

## R-06 — Final code review finds a Critical issue on Day 2 afternoon

**Failure mode:** At 15:30 Day 2 the `superpowers:code-reviewer` skill flags a Critical issue — say, a hardcoded service-account credential in a test fixture that accidentally ships in the pypi package (unlikely here but representative). The builder has 4 hours to fix, retest, redeploy, re-record video snippets if the fix changes visible behaviour.

**Probability:** **Medium.** Code review almost always finds something; the question is whether it is blocking.

**Severity:** **High.** Can cascade into video reshoots.

**Root causes:**
- Sprint 0-5 reviews did not catch everything
- The full-diff review is a different lens than per-sprint reviews and may find cross-sprint issues
- Time-pressure in earlier sprints tolerated "we'll fix it in Sprint 6"

**Mitigations (in PRD):**
- Day 2 schedule places code review at 14:00 leaving 4 hours for fixes
- Per-sprint reviews in Sprints 0-5 reduce the Critical-finding count to near zero by Sprint 6
- Medium/Low findings ship with documentation, only Critical blocks

**Residual risk:** Low. The main protection is diligent per-sprint reviews making Sprint 6's review a formality.

**If it fires:** Work the hotfix path. If the fix is visible in the video, reshoot only the affected beat. The separated-track recording approach (Template G) makes single-beat reshoots cheap.

---

## R-07 — User interview gap costs Top 100 placement

**Failure mode:** The Top 100 are announced May 29. We are not in the list. Post-hoc analysis shows the Impact dimension (25 points) was our weak point — specifically the "three feedback points from real users" criterion (5 points) where we scored 1/5. If we had scored 4/5 there, we would have made Top 100.

**Probability:** **High** that we lose points here. **Medium** that it becomes the deciding factor.

**Severity:** **Medium.** Not a submission failure, but a rubric failure.

**Root causes:**
- User explicitly deferred interviews to preserve building time
- The 5-layer problem model and Priya persona are derivative (based on research), not real interview data
- The SDG alignment statement admits the gap

**Mitigations (in PRD):**
- Acknowledged in §3 Out-of-Scope and §11 Success Metrics self-assessment (43/50 target)
- SDG alignment statement explicitly notes the gap and commits to closing it before May 29
- Judging strategy compensates by over-investing in Technical Merit narrative

**Residual risk:** High. The 5-point loss is baked in.

**Extra mitigation (optional, flagged in PRD §16 assumption #7):**
- If user wants to close the gap at the last minute, Rollback Plan §13 provides a 3-WhatsApp-interview fast path. 90 minutes of effort, 3 real quotes, converts 1/5 to 3/5 on that criterion.

**If it fires (not selected for Top 100):** Complete the user interviews properly in May-June for Tier 2 iteration. Solution Challenge gives feedback to non-advancing teams.

---

## R-08 — Solo-builder fatigue causes quality drop on Day 2

**Failure mode:** 14 days of sprints have burned the builder out. Day 2 afternoon they are running on 4 hours of sleep and 6 cups of coffee. The deck slides have typos. The ADR writes itself into incoherence. The submission email is riddled with spelling mistakes. Judges open the submission and see sloppy work that undermines the polish of Sprints 0-5.

**Probability:** **High.** Solo hackathon sprints always end in fatigue.

**Severity:** **Medium.** Does not block submission but degrades perceived quality.

**Root causes:**
- 14 consecutive days of intense work
- No handoff to a teammate for quality review
- End-of-sprint push mentality

**Mitigations (in PRD):**
- Day 1 soft-stop at 22:00
- Day 2 has a 19:00-21:00 buffer specifically for fatigue recovery
- Retrospective scheduled before the buffer so it is written fresh
- Self-review checklists on every artifact (§9 DoD per Artifact)

**Residual risk:** Medium. Mitigations help but cannot eliminate fatigue.

**Extra mitigation to add:**
- Schedule sleep: Day 1 and Day 2 have hard 22:00 stop times. Day 3 starts at 10:00 not 06:00.
- Run every artifact through a spell-checker (Grammarly or built-in) before committing
- Ask an outside reader (family member, friend) to skim the problem statement + solution brief for typos

**If it fires:** Accept the cost, ship anyway. Sloppy > missing.

---

## R-09 — Deck format incompatibility

**Failure mode:** The 7-slide deck was built in Google Slides. Exported to .pptx for portal upload. A judge opens the .pptx in PowerPoint 2019 and fonts do not render, images are misaligned, or the slide master is broken. The deck looks amateur.

**Probability:** **Medium.** Google Slides → .pptx round-trip is imperfect especially with custom fonts and embedded images.

**Severity:** **Low-Medium.** Deck is the lowest-weight artifact; damage is cosmetic.

**Root causes:**
- Custom font not embedded in export
- Image positioning drift
- Animation incompatibility (but we avoid animations by design)

**Mitigations (in PRD):**
- TC-07 tests the .pptx export in LibreOffice Impress
- Deck uses Google default web fonts (Roboto, Open Sans) which export reliably
- Both Google Slides public-view link AND .pptx are submitted (link is primary)

**Residual risk:** Low.

**If it fires:** Portal response by uploading a PDF export, which renders identically everywhere.

---

## R-10 — GitHub repo public-flip exposes old commits with problems

**Failure mode:** The repo was private during Sprints 0-5. On Day 2 afternoon it gets flipped to public. Someone discovers a commit from Sprint 2 that contained a dummy API key (flagged and fixed in the next commit but never squashed). Or a debug log with PII. The repo's git history becomes an embarrassment.

**Probability:** **Low-Medium.** Depends on Sprint 0-5 hygiene.

**Severity:** **High** if a real secret is found; **Low** if it is just code-quality concerns.

**Root causes:**
- Per-sprint pre-commit hooks may have missed a transient secret
- Debug logs committed and then deleted (still in history)
- Exploratory commits with slurs or profanity (extremely unlikely but has happened)

**Mitigations (in PRD):**
- TC-10 runs history audit: `git log -p | grep -iE "(api[_-]?key|secret|password|token)"`
- Pre-commit `detect-secrets` active from Sprint 0
- Squash-merge discipline on feature branches through Sprints 0-5

**Residual risk:** Low-Medium.

**Extra mitigation to add:**
- Day 2 morning: clone the repo into a separate directory as if a judge did it, and scan the cloned copy
- If anything questionable is found, use `git filter-repo` to clean history before flipping public

**If it fires post-flip:** Rotate any exposed secrets immediately. Clean history with filter-repo. Force-push (accept the risk of broken external clones — unlikely any exist).

---

## R-11 — Video exceeds portal size or duration limit

**Failure mode:** The portal enforces a hard 2-minute video length (reverting to the 2024 limit, tighter than the 2023 3-minute allowance). Our video is 3:00. It gets truncated or rejected.

**Probability:** **Medium.** Portal specs change yearly without announcement.

**Severity:** **High.** Cannot submit without a compliant video.

**Root causes:**
- Research relied on 2024 + 2023 data; 2026 spec may differ
- Video was structured for 180s assuming 3-minute allowance

**Mitigations (in PRD):**
- §16 Open Assumption #2 flags this explicitly
- Portal check on Day 1 morning verifies the 2026 limit before recording
- Script Template A is structured so Beats 1 and 5 can be cut independently to tighten to 120s total

**Residual risk:** Low IF the Day 1 morning portal check happens.

**If it fires post-recording:** Edit the video to cut Beat 1 (the hook) and trim Beat 5 (the impact) to fit 120s. The core Beats 2-4 (the actual demo) stay intact.

---

## R-12 — GDSC membership invalid at submission time

**Failure mode:** The submission requires active GDSC (Google Developer Student Club) membership at time of submission per Terms. If the builder's chapter is inactive, or they left the chapter, or the chapter lost GDSC status, the submission is disqualified.

**Probability:** **Low.** Builder is presumed to be an active GDSC member (implied by participating).

**Severity:** **Critical.** Disqualification.

**Mitigations (in PRD):**
- §16 Open Assumption #5 flags this for user verification on Apr 22

**If it fires:** Find a GDSC chapter that will sponsor the submission. Last-resort only.

---

## R-13 — Cloud Run quota / billing surprises

**Failure mode:** On Apr 24 morning, Cloud Run has stopped the service because the GCP project billing hit a soft cap. The live URL is dead. The builder discovers this at 10:00 during the morning health check with 14 hours until deadline.

**Probability:** **Low.** `min_instances=1` costs ~$5/month which is well within free tier if no other services burn budget.

**Severity:** **Critical.** Live URL dead.

**Root causes:**
- Gemini API usage spikes during testing
- Firestore reads from aggressive integration tests
- Billing alerts not set up

**Mitigations (in PRD):**
- Sprint 0 ADR-005 sets up billing alerts
- Sprint 5 validates `min_instances=1` cost

**Extra mitigation to add:**
- Enable a GCP billing alert at $20 total project spend — email the builder if hit
- Check GCP billing dashboard on Apr 22 morning to confirm current spend

**If it fires:** Increase billing cap via GCP console (takes <5 minutes). Service resumes.

---

## R-14 — Coherence failure across artifacts

**Failure mode:** The video says "under 4 seconds." The problem statement says "2-4 hours to 4 seconds." The solution brief says "under 6 seconds." The deck says "3 seconds." A judge comparing artifacts notices the inconsistency and downgrades the credibility of every claim.

**Probability:** **Medium.** Solo builder writing 7 artifacts in 2 days will produce inconsistencies without deliberate cross-checking.

**Severity:** **Medium.** Does not block submission but erodes rubric points.

**Root causes:**
- No single source of truth for key numbers
- Each artifact was drafted independently

**Mitigations (in PRD):**
- §9 DoD per artifact specifies the key numbers each must include
- Template B and Template C both reference `₹18,50,000`, `under 4 seconds`, `2-4 hours manual baseline`

**Extra mitigation to add:**
- Maintain a "canonical facts" file: `docs/submission/canonical-facts.md` with every key number, and grep each artifact against it during Day 2 afternoon review
- Example canonical facts: "triage_latency_seconds: 4", "baseline_triage_hours: 2-4", "value_at_risk_inr: 1850000", "affected_shipments_count: 4"

**If it fires:** Day 2 late afternoon pass with `grep` across all artifacts comparing against canonical facts. Fix mismatches before submission.

---

## R-15 — "AGENTS.md" added without purpose → judges question it

**Failure mode:** The PRD introduces `AGENTS.md` as a 2026 convention. A non-AI-native judge sees an unfamiliar file, opens it, sees "Build commands" + "Style conventions" and thinks "this is just a rehash of README". They mark it as evidence of over-engineering.

**Probability:** **Low.** Most Solution Challenge judges are developers who have heard of AGENTS.md.

**Severity:** **Low.** Cosmetic.

**Mitigations:** Template E explicitly cross-links README and AGENTS.md with a short "For AI coding agents" note.

**If it fires:** Accept the cost; the benefit of agent-friendly documentation outweighs the risk of confusion.

---

## Summary Risk Matrix

| Risk | P | Severity | Blocker? | Mitigation Strength |
|------|---|----------|----------|---------------------|
| R-01 Video re-record budget blown | H | H | No (rollback) | Medium |
| R-02 Live URL broken | M | Critical | Yes | Medium |
| R-03 Fresh clone fails (macOS) | M | M | No | Medium |
| R-04 Secret leak | L-M | Critical | Yes | High |
| R-05 Portal field surprise | M | H | No (rollback) | High |
| R-06 Code review Critical finding | M | H | Yes | High |
| R-07 User interview gap | H | M | No (baked in) | Low |
| R-08 Solo fatigue | H | M | No | Medium |
| R-09 Deck format incompatibility | M | L-M | No | High |
| R-10 Repo history exposure | L-M | H | Yes | High |
| R-11 Video length limit change | M | H | Yes if fires | High |
| R-12 GDSC membership invalid | L | Critical | Yes | Low |
| R-13 Cloud Run billing surprise | L | Critical | Yes | Medium |
| R-14 Coherence failure | M | M | No | Medium |
| R-15 AGENTS.md confusion | L | L | No | N/A |

**Top-3 risks to actively watch during the sprint:**

1. **R-01 Video re-records** — biggest time-budget risk. Enforce Template G separation discipline.
2. **R-02 Live URL breaking** — biggest post-submission failure risk. Set up monitoring on Day 2.
3. **R-04 Secret leak** — biggest financial + reputation risk. Run TC-10 twice (Day 2 morning + Day 2 end).

---

## Pre-Mortem Action Items (to add to PRD if not already)

From this pre-mortem, the following items need to be inserted or confirmed in the PRD:

- [ ] **Day 1 morning portal check** — verify video length limit and portal field list on Apr 22 09:00 (R-11, R-05)
- [ ] **GDSC membership verification** — confirm active status by Apr 22 09:00 (R-12)
- [ ] **GCP billing alert** — set alert at $20 project spend before Apr 24 (R-13)
- [ ] **Canonical facts file** — create `docs/submission/canonical-facts.md` Day 1 morning (R-14)
- [ ] **macOS runner** — optional CI addition Day 2 if time (R-03)
- [ ] **Uptime monitor** — add Cloud Monitoring alert on `/health` by Day 2 evening (R-02)
- [ ] **Post-video frame scrub** — add to Template G checklist (R-04)
- [ ] **Clone-to-separate-dir audit** — Day 2 morning pre-public-flip step (R-10)

All of these are incorporated by reference into `prd.md` §16 Open Assumptions or the relevant template sections.

---

## Cross-References

- `sprint-6/prd.md` — Source PRD
- `sprint-6/test-plan.md` — Test cases that validate mitigations
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — Cross-sprint risk register
- [[Supply-Chain-Judging-Strategy]] — Rubric analysis informing R-07 severity
- [[Supply-Chain-Competitor-Analysis]] — Past winner data informing self-score targets
