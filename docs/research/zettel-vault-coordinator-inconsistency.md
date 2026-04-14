---
title: Vault Coordinator spec — UserContext markdown rendering inconsistency
type: zettel
tags: [vault-drift, coordinator, schemas, documentation-debt, zettel]
status: flagged
last_updated: 2026-04-14
confidence: high
sources:
  - "[[Supply-Chain-Agent-Spec-Coordinator]] vault note (lines 62-114 vs 191-213)"
  - "[[Supply-Chain-Agent-Spec-Classifier]] vault note line 200-209"
related:
  - "[[Supply-Chain-Agent-Spec-Coordinator]]"
  - "[[adr-003-prompt-format]]"
  - "[[zettel-adk-before-model-callback]]"
---

# Vault Coordinator spec — UserContext markdown rendering inconsistency

> **TL;DR.** The vault Coordinator spec describes UserContext markdown rendering in two contradictory ways across lines 62-114 and 191-213. One says `UserContext.to_markdown()` outputs 5 sections; the other says the XML dynamic blocks are 4 separate concepts (`<user_context>`, `<company_context>`, `<recent_history>`, `<learned_behaviors>`). Our implementation follows the XML-block split: `UserContext.to_markdown()` stays 3 sections; `CompanyProfile.to_markdown()` + `render_learned_preferences()` cover the rest.

## The drift

**Vault lines 62-114** describe `UserContext.to_markdown()` as a single function producing **5 sections**: Identity, Volume & Workload, Communication Preferences, **Business Context** (company size, regions, `avg_daily_revenue_inr`), **Learned Preferences** (override patterns, priority ordering, customer notes).

**Vault lines 191-213** describe the Coordinator prompt's XML-delimited dynamic injection blocks as **4 distinct blocks**:
- `<user_context>` — rendered from UserContext
- `<company_context>` — company profile markdown (separate block)
- `<recent_history>` — exception history markdown (separate block)
- `<learned_behaviors>` — learned preferences markdown (separate block)

Both accounts cannot both be true. If `UserContext.to_markdown()` already contains Business Context and Learned Preferences, why are `<company_context>` and `<learned_behaviors>` separate XML blocks in the same prompt?

## First-principles reading

Separate XML blocks exist for two reasons: different *sources* and different *prompt-injection surfaces*.

- **`<user_context>`** — user profile (identity, schedule, communication preferences) — sourced from Supermemory `users/{user_id}` + Firestore. Static per user across a session.
- **`<company_context>`** — company profile including `avg_daily_revenue_inr` — sourced from Firestore `companies/{company_id}`. Static per company.
- **`<recent_history>`** — last N exceptions this user handled — sourced from Firestore `exceptions` query. Changes per request.
- **`<learned_behaviors>`** — override patterns, priority preferences learned over time — sourced from Supermemory semantic memory. Changes as Supermemory accumulates.

**Sources differ → retrieval patterns differ → render functions should differ.** Conflating them into one `to_markdown()` couples the renderer to 4 data sources, making testing and fetching ugly.

## Resolution applied in our implementation

PRD v2 §8.5 keeps `UserContext.to_markdown()` rendering **3 sections** (Identity, Volume & Workload, Communication Preferences), matching the `<user_context>` XML block. Then:

- **`CompanyProfile.to_markdown()`** (new method, PRD v2 §8.6) outputs the Business Context section → feeds `<company_context>`.
- **`render_learned_preferences(user_context: UserContext) -> str`** (free helper, new) outputs the Learned Preferences section → feeds `<learned_behaviors>`.
- **`<recent_history>`** is rendered in the Coordinator's `before_model_callback` from a Firestore query; no standalone helper yet.

Test coverage bumps: PRD v2 test-plan adds **Test 1.10b** (learned preferences header present) and **Test 1.12b** (CompanyProfile.to_markdown emits `## Business Context` with `avg_daily_revenue_inr`). Total test count: 30 → 32.

## Why this matters beyond one function

**Classifier Rule 3 breaks if CompanyProfile.avg_daily_revenue_inr is missing.** Rule 3 = "if value_at_risk_inr > 0.05 * company_avg_daily_revenue_inr → HIGH severity." If we implement `UserContext.to_markdown()` per the 5-section interpretation but don't ensure `<company_context>` is actually rendered at runtime, the Classifier prompt doesn't see the revenue number, Rule 3 silently skips, severity under-reports. Silent failure in production.

The fix (explicit `CompanyProfile.to_markdown()` + test) makes the coupling loud: if `<company_context>` isn't injected, the agent evalset catches it because Rule 3 never fires.

## Gotchas flagged

- **Vault source-of-truth drift is a known risk.** 222 vault files with `[[wiki-link]]` cross-references; manual edits drift. Our project's `docs/research/` copies are snapshots — they won't auto-update from vault.
- **Whoever edits the vault next may not notice this drift.** Leave a note in the vault Coordinator spec pointing to this Zettel, OR raise as a vault-hygiene issue for the next session.
- **Our test 1.10 from PRD v1** only checks 3 headers (Identity, Volume & Workload, Communication Preferences). Matches the 3-section interpretation. Test-plan v2 adds 1.10b + 1.12b.

## Further research

- **Vault hygiene process.** How do we keep `docs/research/` in sync with the vault as it evolves? Manual refresh only when vault notes change significantly? A git hook in the vault to email the project? Open.
- **Drift between ADK spec notes and ADR decisions.** Are there other spec notes that contradict ADRs? Quick audit pass on the other 4 vault notes copied: Classifier, Impact, Firestore-Schema-Tier1, Sprint-Plan-Spiral-SDLC.
- **Should `<recent_history>` rendering have a dedicated helper too?** Currently implemented inline in the Coordinator callback. Extracting would simplify testing but adds an abstraction layer.

## Next action

Flag this inconsistency in the vault itself (future non-plan-mode session) with a pointer back to this Zettel. Resolve in PRD v2 as described above.
