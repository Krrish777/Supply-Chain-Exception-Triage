---
title: "Sprint 6 Test Plan — Submission Package"
type: deep-dive
domains: [supply-chain, hackathon, testing]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[sprint-6/prd]]", "[[Supply-Chain-Sprint-Plan-Spiral-SDLC]]"]
---

# Sprint 6 Test Plan — Submission Package

> Companion to `sprint-6/prd.md`. Given/When/Then test cases for every acceptance criterion.
> No feature code is shipped this sprint — tests here validate **artifacts and the integration surface between artifacts and the Sprint 5 deployment.**

---

## Test Philosophy for a Packaging Sprint

Sprint 6 tests are qualitatively different from Sprints 0-5. There is no new business logic to exercise. The tests here answer three questions:

1. **Can a judge use what we built?** (Fresh-clone, live URL, video playback, deck export)
2. **Have we leaked anything we should not?** (Secrets, PII, real customer data)
3. **Does every artifact tell the same story?** (Coherence across video, brief, deck, README)

Tests are a mix of automated (shell scripts, pytest, CI) and manual checklists. Manual tests are first-class — they cannot be automated away because "does this video feel professional" is a judgement call.

---

## Test Matrix (Given/When/Then)

### TC-01: Problem statement word count + structure

**Given** `docs/submission/problem-statement.md` exists,
**When** word count is measured with `wc -w docs/submission/problem-statement.md`,
**Then** count is in the range **380-420**.

**Automated:** Yes. CI step: `test -$(wc -w < docs/submission/problem-statement.md) -ge 380 && test $(wc -w < docs/submission/problem-statement.md) -le 420`

**Additional manual check:** The statement must include (a) the 5-layer problem model, (b) at least 3 quantified pain metrics, (c) the Priya persona, (d) explicit SDG 9 mapping.

---

### TC-02: Solution brief word count + Google-service coverage

**Given** `docs/submission/solution-brief.md` exists,
**When** word count is measured and the file is grepped for required Google service names,
**Then** word count is 380-420 AND the brief mentions: `Gemini 2.5 Flash`, `ADK`, `Firestore`, `Cloud Run`, `Firebase Auth`.

**Automated:** Yes.
```bash
#!/bin/bash
set -e
COUNT=$(wc -w < docs/submission/solution-brief.md)
[ "$COUNT" -ge 380 ] && [ "$COUNT" -le 420 ]
grep -q "Gemini 2.5 Flash" docs/submission/solution-brief.md
grep -qE "ADK|Agent Development Kit" docs/submission/solution-brief.md
grep -q "Firestore" docs/submission/solution-brief.md
grep -q "Cloud Run" docs/submission/solution-brief.md
grep -qE "Firebase Auth|firebase-admin" docs/submission/solution-brief.md
```

---

### TC-03: Demo video script word count + beat coverage

**Given** `docs/submission/demo-video-script.md` exists,
**When** the script is parsed for beat headers and total word count,
**Then** exactly 5 beat headers (`#### Beat 1` through `#### Beat 5`) exist AND narration-column total word count is 450-560.

**Automated:** Partially. Beat header count is grep-able. Narration word count requires extracting the narration column from the table — a Python helper script at `scripts/count_script_words.py`.

---

### TC-04: Fresh-clone setup test

**Given** the public GitHub repo URL and a sandboxed Ubuntu 22.04 environment with only Python 3.13 and `uv` installed,
**When** `tests/submission/test_fresh_clone_setup.sh` runs,
**Then** it clones the repo, runs `uv sync`, runs `make test`, and exits 0 within 10 minutes.

**Automated:** Yes. Runs in a Docker container for reproducibility.

```bash
#!/bin/bash
# tests/submission/test_fresh_clone_setup.sh
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/USER/REPO.git}"
TIMEOUT_SECS=600

docker run --rm \
    -v "$(pwd)/scripts/fresh-clone-inner.sh:/test.sh:ro" \
    python:3.13-slim \
    bash -c "
        set -e
        apt-get update -q && apt-get install -y git curl make >/dev/null
        curl -LsSf https://astral.sh/uv/install.sh | sh
        export PATH=/root/.cargo/bin:\$PATH
        cd /tmp
        timeout ${TIMEOUT_SECS} git clone ${REPO_URL} repo
        cd repo
        uv sync
        make test
    "
```

**Expected:** Exit code 0, all tests green, total elapsed time reported at end.

**Failure modes to watch:**
- Private dependency not accessible without auth
- Firestore emulator binary download fails in sandbox
- `make test` relies on `.env` that does not exist in fresh clone

**Fix path:** Document any failure in `docs/onboarding/setup.md` under "Known Issues" and provide an alternative Docker-based quickstart.

---

### TC-05: Live URL smoke test

**Given** the Sprint-5 Cloud Run live URL is deployed,
**When** `tests/e2e/test_live_url_smoke.py` POSTs the NH-48 exception payload to `/triage/stream`,
**Then** the response streams the Classifier result (with `exception_type="carrier_capacity_failure"` and `severity="CRITICAL"`) followed by the Impact result (with `total_value_at_risk_inr=1850000`), total elapsed time is under 6 seconds.

**Automated:** Yes.

```python
# tests/e2e/test_live_url_smoke.py
import os
import time
import pytest
import httpx
import json

LIVE_URL = os.environ.get("LIVE_URL", "https://REPLACE.run.app")
TEST_TOKEN = os.environ.get("TEST_ID_TOKEN")

NH48_PAYLOAD = {
    "source": "whatsapp_voice",
    "raw_text": (
        "Priya madam, namaste. Truck mein problem ho gaya hai. "
        "NH-48 pe, Lonavala ke paas, kilometre marker 72. "
        "Engine overheat ho gaya, smoke bhi aa raha tha. "
        "Maine roadside pe park kar diya hai. "
        "Mechanic ko phone kiya, woh bola 3-4 ghante lagega minimum."
    ),
    "driver_id": "MH-04-XX-1234",
    "timestamp": "2026-04-10T14:15:00+05:30",
}

@pytest.mark.asyncio
async def test_nh48_live_smoke():
    assert TEST_TOKEN, "Set TEST_ID_TOKEN environment variable"
    start = time.perf_counter()
    classifier_done = False
    impact_done = False
    classification = None
    impact = None

    async with httpx.AsyncClient(timeout=10.0) as client:
        async with client.stream(
            "POST",
            f"{LIVE_URL}/triage/stream",
            json=NH48_PAYLOAD,
            headers={"Authorization": f"Bearer {TEST_TOKEN}"},
        ) as response:
            assert response.status_code == 200
            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue
                event = json.loads(line[5:])
                if event.get("type") == "classifier.done":
                    classification = event["payload"]
                    classifier_done = True
                if event.get("type") == "impact.done":
                    impact = event["payload"]
                    impact_done = True

    elapsed = time.perf_counter() - start
    assert classifier_done, "Classifier did not complete"
    assert impact_done, "Impact agent did not complete"
    assert classification["exception_type"] == "carrier_capacity_failure"
    assert classification["severity"] == "CRITICAL"
    assert impact["total_value_at_risk_inr"] == 1850000
    assert elapsed < 6.0, f"Triage took {elapsed:.1f}s, expected <6s"
```

**Run pre-submission:** morning of Apr 24 before the portal upload.

**Failure action:** If the assert on `elapsed < 6.0` fails but the classifier/impact fields are correct, log it as a soft fail and continue. If the fields are wrong, block submission.

---

### TC-06: README renders correctly on GitHub

**Given** the polished README is pushed to the public GitHub repo,
**When** a fresh browser (incognito mode) loads the repo page,
**Then** all badges render (not broken image icons), the architecture PNG displays, the live URL is clickable, the YouTube thumbnail shows, and no markdown syntax is exposed.

**Automated:** Partially. The badge URLs can be checked with `curl` for 200 responses. PNG presence is file-test-able.

```bash
#!/bin/bash
# scripts/check_readme_badges.sh
set -e
BADGES=$(grep -oE 'https://img\.shields\.io[^)]*' README.md)
for url in $BADGES; do
    code=$(curl -s -o /dev/null -w "%{http_code}" "$url")
    if [ "$code" != "200" ]; then
        echo "BROKEN BADGE: $url ($code)"
        exit 1
    fi
done
test -f docs/architecture/diagram.png
grep -q "https://LIVE_URL" README.md || echo "WARNING: LIVE_URL placeholder not replaced"
```

**Manual check:** Open the repo in incognito browser and visually scan top-to-bottom. Compare against Template E in the PRD.

---

### TC-07: Deck exports correctly to .pptx + PDF

**Given** the 7-slide deck exists as Google Slides,
**When** exported to `.pptx` and re-opened in LibreOffice Impress,
**Then** all 7 slides render with correct order, fonts, images, and speaker notes preserved.

**Manual test:**
1. Download Google Slides → File → Download → Microsoft PowerPoint (.pptx)
2. Open the .pptx in LibreOffice Impress on a clean machine
3. Walk through all 7 slides, verify each matches Template D
4. Check speaker notes on slides 2-7
5. Export to PDF from LibreOffice and re-check font rendering

**Failure action:** If fonts fail to embed, switch deck to use Google's default web fonts only (Roboto, Open Sans).

---

### TC-08: Video quality checklist

**Manual checklist.** See `sprint-6/prd.md` §5.3 for the full list. Run before uploading to YouTube.

Key checks (abbreviated):
- [ ] 1080p minimum
- [ ] ≤180 seconds total
- [ ] Audio peaks -12 to -6 dB, no clipping
- [ ] Intelligible at 1.5× playback speed
- [ ] No visible PII or secrets
- [ ] No console errors visible in browser devtools
- [ ] Opening 10 seconds pass the "tired judge" test
- [ ] Closing 3 seconds are silent hold

---

### TC-09: Submission portal dry-run

**Given** a draft session in the Solution Challenge portal,
**When** every field is filled from `docs/submission/portal-answers.md` and every file is attached,
**Then** the portal's "Save Draft" action succeeds without validation errors.

**Manual test:** Walk through the portal end-to-end, do NOT click final submit. Save as draft. Log any field that raised a validation error (character limits, file size limits, file format limits).

**Post-test action:** Fix any validation failures in the source documents BEFORE Apr 24 morning.

---

### TC-10: Secret leak audit

**Given** the final repo state at tag `v1.0.0-submission`,
**When** `detect-secrets scan --all-files` and `git log -p | grep -iE "api[_-]?key|secret|password|token|private"` run,
**Then** no secrets are found in the working tree or git history.

**Automated:**
```bash
#!/bin/bash
set -e
detect-secrets scan --all-files --baseline .secrets.baseline
git log -p --all | grep -iE "(api[_-]?key|secret|password|token|private)[[:space:]]*[:=][[:space:]]*['\"]?[A-Za-z0-9/_+-]{20,}" && exit 1 || true
echo "Secret audit clean"
```

**If history contains a secret:** rotate the key immediately, then use `git filter-repo` to remove the commit, then force-push. This is a Critical blocker.

---

### TC-11: Code review — Critical findings resolved

**Given** the `superpowers:code-reviewer` skill has run on `git diff v0.0.0..HEAD`,
**When** the review output is triaged,
**Then** zero Critical findings remain open AND all Medium/Low findings have a documented ship-or-fix decision in `docs/sprints/sprint-6/review.md`.

**Manual test:** Run the skill, record output, fix Critical, document remainder.

---

### TC-12: ADR-018 exists and is linked

**Given** `docs/decisions/adr-018-submission-artifacts.md`,
**When** the file is opened,
**Then** it references all 7 submission artifacts, documents 5 key decisions (video length, deck size, SDG primary, user-interview deferral, Canva/Slides choice), and is linked from the README ADR index.

**Automated check:**
```bash
test -f docs/decisions/adr-018-submission-artifacts.md
grep -q "adr-018-submission-artifacts" README.md || grep -q "adr-018-submission-artifacts" docs/decisions/README.md
```

---

### TC-13: Live URL morning-of health check

**Given** Apr 24 morning (10:00 IST),
**When** `curl -i https://LIVE_URL/health` runs,
**Then** response is HTTP 200 AND `content-type: application/json` AND body contains `"status": "ok"`.

**Manual step:** Run this as the absolute last step before opening the portal.

**Failure action:** Rollback Plan §13 applies.

---

### TC-14: Confirmation archive exists post-submission

**Given** the submission has been filed via the portal,
**When** `docs/submission/confirmation.txt` and `docs/submission/confirmation.png` are checked,
**Then** both exist AND `confirmation.txt` includes the submission timestamp AND `confirmation.png` is a screenshot of the portal success page.

**Automated check:** `test -f docs/submission/confirmation.txt && test -f docs/submission/confirmation.png`

---

### TC-15: Git tag + push verification

**Given** the sprint has closed,
**When** `git tag -l | grep v1.0.0-submission` runs AND `git ls-remote --tags origin | grep v1.0.0-submission` runs,
**Then** both return the tag name, confirming local tag and remote push.

---

### TC-16: AGENTS.md convention check

**Given** `AGENTS.md` exists at repo root,
**When** the file is read,
**Then** it contains sections: "Build commands", "Test commands", "Style conventions", "Agent entry points", matching the 2026 AGENTS.md emerging convention.

**Automated:**
```bash
grep -q "^## Build" AGENTS.md
grep -q "^## Test" AGENTS.md
grep -q "^## Style" AGENTS.md
grep -q "^## Agent" AGENTS.md
```

---

## Test Execution Schedule

| Test | When to run | Automated | Blocker if fails? |
|------|-------------|-----------|-------------------|
| TC-01 | End of Day 1 morning | Yes | Yes (AC-02) |
| TC-02 | End of Day 1 morning | Yes | Yes (AC-03) |
| TC-03 | End of Day 1 morning | Partial | Yes (AC-01) |
| TC-04 | Day 2 morning | Yes | Medium — document workaround if fails |
| TC-05 | Day 2 morning AND Day 3 morning | Yes | Yes if morning-of fails |
| TC-06 | Day 1 evening | Partial | Yes (AC-06) |
| TC-07 | Day 2 morning | Manual | Yes (AC-04) |
| TC-08 | Day 1 evening | Manual | Yes (AC-05) |
| TC-09 | Day 2 late afternoon | Manual | Yes (AC-15) |
| TC-10 | Day 2 afternoon | Yes | Critical — blocks submit |
| TC-11 | Day 2 afternoon | Semi | Critical findings block submit |
| TC-12 | Day 2 afternoon | Yes | Yes (AC-11) |
| TC-13 | Day 3 morning (Apr 24 10:00) | Manual | Critical — rollback if fails |
| TC-14 | Day 3 after submission | Yes | Yes (AC-16) |
| TC-15 | Day 3 end of day | Yes | No (housekeeping) |
| TC-16 | Day 1 evening | Yes | Yes (AC-08) |

---

## Cross-References

- `sprint-6/prd.md` — Source for acceptance criteria
- `sprint-6/risks.md` — Pre-mortem informing test prioritisation
- [[Supply-Chain-Sprint-Plan-Spiral-SDLC]] — 9-artifact-per-sprint convention
