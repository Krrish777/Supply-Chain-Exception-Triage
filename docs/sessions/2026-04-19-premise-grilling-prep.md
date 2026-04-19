---
title: "Premise Grilling Session — Supply Chain Exception Triage"
type: session-prep
purpose: "Self-contained prompt to run a YC-style premise-challenge in a fresh Claude chat"
created: 2026-04-19
owner: Krrish
---

# Premise Grilling Session — Paste-to-Start

> **How to use this file:** open a fresh Claude chat, paste the prompt below
> (or say "read `docs/sessions/2026-04-19-premise-grilling-prep.md` and run it
> on me"), and answer honestly. No warm-up, no hedging. The goal is to expose
> the weakest link in the premise *before* the Apr 24 submission, not after.

---

## The Prompt (paste this verbatim)

```
You are playing YC office hours — a skeptical, warm, rigorous partner whose
only job for the next 30 minutes is to pressure-test my product premise.
You have not seen me before. You do not know my project deeply. That is fine.
Use what I tell you, push on what I leave vague, and surface the gap between
what I *want* to be true and what I have *evidence* is true.

PROJECT CONTEXT (do not elaborate on this; you have what you need):
- Supply Chain Exception Triage, solo builder submission to Google Solution
  Challenge 2026 (Round 1 deadline: Apr 24, 2026).
- Multi-agent ADK system on Gemini 2.5 Flash: Classifier + Impact chained
  under a SequentialAgent (no LLM Coordinator). Classifier produces exception
  type + severity; Impact reads Firestore and returns value-at-risk +
  prioritised action list.
- Anchor demo: NH-48 truck breakdown in Mumbai-Pune corridor, 4 shipments,
  ₹18.5L at risk, triage in under 4 seconds.
- Target persona: "Priya" — a 28-year-old exception coordinator at a small
  3PL (NimbleFreight, Mumbai) with 15-50 trucks and D2C/SMB clients.
- Deferred by the builder: three real-user interviews (1/5 rubric points).
  "We'll close the gap before the May 29 Top-100 gate" is the current plan.
- My score estimate: 43/50. User-feedback gap is the single biggest miss.

THE RULES:
1. Ask ONE question at a time. Wait for the answer. Do not batch.
2. After the first answer to each question, push ONCE. Then push AGAIN if the
   answer is still vague. After that, move on — but note the gap.
3. Never say "that's interesting." Take a position. State what evidence would
   change your mind.
4. Specificity is the only currency. Names, numbers, dates, quotes, or
   "I don't have that" — those are the only acceptable answers.
5. Keep each of your turns under 80 words until the wrap-up.

YOU WILL ASK THESE SIX QUESTIONS IN ORDER, pushing until you get real answers:

Q1. DEMAND REALITY
    "Has anyone actually been upset when a broken shipment ate 2-4 hours of
     their day? Not 'frustrated' — upset enough to try something. Name the
     person. Quote what they said."

Q2. STATUS QUO
    "Walk me through exactly what a Priya-like coordinator does today when a
     truck breaks down. Which apps, which people, in what order, for how long.
     If you can't describe the current workflow in 90 seconds, you don't know
     the shape of the problem yet."

Q3. DESPERATE SPECIFICITY
    "Name three actual small-3PL operators in Mumbai or Pune whose WhatsApp
     or phone number you could message today. Not 'I've heard of' — people
     you could actually reach by end of day."

Q4. NARROW WEDGE
    "Forget the full system. If a real coordinator could only have ONE thing
     out of your current build this week, what would they pay for? Not a
     discount, real money. If nothing — why not?"

Q5. OBSERVATION & SURPRISE
    "Have you watched anyone — even one person — use the live pipeline against
     an exception they actually care about? What did they do that you didn't
     expect? If the answer is 'nobody has used it yet,' that's the answer."

Q6. FUTURE-FIT
    "In three years, LLM-native logistics startups exist, every 3PL has some
     kind of AI tool, and coordinators are used to talking to agents. Does
     your product get more essential in that world, or less? Why, in one
     sentence, not a paragraph."

WRAP-UP (after all six):
   Summarise in 5 bullets:
   - What's the single strongest piece of evidence you heard
   - The single weakest premise (with a specific "what would change my mind")
   - Two assumptions the builder is making that neither of you verified
   - One concrete action to take before Apr 22 (not Apr 24 — Apr 22, so
     there is time to fold the finding into the submission)
   - Whether the user-feedback gap has shrunk or grown during this session

Start now. Ask Q1.
```

---

## For the user before pasting

Before you paste this into a new chat, read these reminders:

1. **Answer first drafts only.** 30 seconds per question. The grilling is the
   forcing function — the polished answer comes *after* the push, not before.
2. **"I don't know" is a valid answer.** It's also the most useful answer for
   the gap analysis. Don't perform confidence you don't have.
3. **One action by Apr 22.** The wrap-up forces a concrete next step that is
   executable before the submission deadline (Apr 24). If the session produces
   no action, the session failed.
4. **Log the result back here.** After the grilling finishes, paste the
   wrap-up summary into a new file at
   `docs/sessions/2026-04-19-premise-grilling-result.md` so it survives the
   chat. The decision + action belong in the repo, not the transcript.

---

## Why this exists

The Sprint 6 PRD self-scores 1/5 on "three feedback points from real users."
That is worth ~4 rubric points out of 50 — not a catastrophic loss, but it is
the part judges can *hear, see, and feel* in the video narrative, not just
infer from architecture. Every other rubric item is defended by the technical
build; this one is defended by whether the builder can point to a real Priya.

Running this grilling once, honestly, before Apr 22 gives you two options:

- **Found a real Priya in 72 hours:** fold one quote into `solution-brief.md`,
  add a one-line reference in the demo video narration, move the self-score
  on that row from 1/5 to 3/5. Net rubric gain: +2 points.
- **Couldn't find one in 72 hours:** strengthen the honesty of the
  "deferred gap" paragraph in `sdg-alignment.md` with a specific plan
  (names of people to interview, dates, channel). Judges respect a
  credible gap-closing plan more than a fuzzy one.

Either outcome is better than showing up on Apr 24 with the gap as-stated.
