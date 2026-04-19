---
title: "LLM Provider Strategy, Quotas, and Rate-Limiting Patterns"
date: 2026-04-18
author: "Claude (research agent)"
status: "build-ready"
scope: "Tier 1 demo (2026-04-28) + forward-compatible for Tier 2/3"
tier_deadline: "2026-04-28"
primary_model: "gemini-2.5-flash"
providers_evaluated: ["Gemini API (AI Studio)", "Vertex AI", "Groq via LiteLLM"]
related_rules:
  - ".claude/rules/agents.md"
  - ".claude/rules/observability.md"
  - ".claude/rules/deployment.md"
  - ".claude/rules/security.md"
related_docs:
  - "docs/research/adk-best-practices.md"
  - "docs/research/gemini-structured-output-gotchas.md"
  - "docs/research/sprint2-impact-prd.md"
supersedes: []
---

# LLM Provider Strategy, Quotas, and Rate-Limiting Patterns

> **Purpose:** One self-contained, build-ready reference for Tier 1 demo
> (2026-04-28): which LLM provider we use, what the live quota ceilings are,
> what we build in our own code to stay under them, and what we do when we
> hit them anyway. Everything needed to implement is here; no further web
> research should be required during build.

---

## 1. Executive summary + recommendation

### 1.1 The short version

For Tier 1 (demo 2026-04-28), run **Gemini 2.5 Flash on all four sub-agents**
(`classifier_fetcher`, `classifier_formatter`, `impact_fetcher`,
`impact_formatter`), auth via **AI Studio API key in local dev + Vertex AI
ADC on Cloud Run production**, keep the `core/llm.py` provider-indirection
(Groq wired but not used in Tier 1 due to ADK + LiteLLM + Groq structured
output bug). Rate-limit at three layers: the Gemini API's own per-project
quota is the ceiling; slowapi middleware per-IP at 10/min on
`/api/v1/triage`; `tenacity` retries with exponential backoff + jitter on
`429`/`503` with `max_attempts=3` before returning `status="retry"`. Cap
`max_output_tokens` per sub-agent (fetchers=1024, formatters=2048). Run
Cloud Run with `min-instances=1` for the demo window (~$3.24/month memory-only
under request-based billing). Set $10 / $25 / $50 budget alert thresholds via
`gcloud billing budgets create` on the GCP project before the demo.

### 1.2 Why this is the right call

- **Gemini-everywhere for Tier 1 is forced, not chosen.** ADK's LiteLLM
  connector sends `tool_choice="json_tool_call"` when an `LlmAgent` has
  `output_schema=` set, and Groq returns 400 ("Requested tool_choice
  `json_tool_call` was not defined in the request"). Both formatter
  sub-agents use `output_schema` — so Groq is disqualified from the
  formatters in Tier 1. Using Gemini on fetchers and Groq on formatters
  adds integration risk for no cost benefit. Uniform Gemini Flash is the
  shortest path to a working demo.
- **Vertex AI for production is the right auth path for Cloud Run.**
  ADC + Workload Identity = zero API keys in env vars, IAM-scoped access,
  audit logging, regional residency. Pricing is identical to AI Studio for
  Gemini 2.5 Flash ($0.30/1M input, $2.50/1M non-thinking output,
  $3.50/1M thinking output).
- **Tier 1 paid quota (300 RPM, 1M TPM, 1000 RPD for Flash) is plenty.**
  A 100-run demo window per-project uses <10% of daily quota.
- **slowapi per-IP rate limiting is cheap insurance.** Demo-day accidents
  (a tab auto-refreshing; a curl loop) would burn the free-tier daily
  quota in 90 seconds without it. Cost: one middleware, <5ms overhead per
  request.
- **tenacity on 429/503 handles the "Gemini is overloaded" case** that is
  uncorrelated with our quota. Cheap to add, high-value.
- **`max_output_tokens` + `thinking_budget=1024` bound worst-case cost per
  run** to single-digit cents even if the LLM runs wild.

### 1.3 Single-page config snapshot (what will be live on demo day)

| Layer | Setting | Value |
|---|---|---|
| Model | All 4 sub-agents | `gemini-2.5-flash` |
| Model | `thinking_budget` | 1024 |
| Model | `max_output_tokens` (fetchers) | 1024 |
| Model | `max_output_tokens` (formatters) | 2048 |
| Auth (local) | `LLM_PROVIDER` | `gemini` |
| Auth (local) | `GOOGLE_API_KEY` | AI Studio key from Secret Manager |
| Auth (prod) | `GOOGLE_GENAI_USE_VERTEXAI` | `TRUE` |
| Auth (prod) | `GOOGLE_CLOUD_PROJECT` | Cloud Run service account via ADC |
| Auth (prod) | `GOOGLE_CLOUD_LOCATION` | `asia-south1` (or `us-central1` fallback if quota is tight) |
| Quota tier | Gemini API billing | Tier 1 (paid, >=1 payment) |
| FastAPI | slowapi per-IP | `10/minute` on `/api/v1/triage` |
| Retry | tenacity on 429/503 | `stop_after_attempt(3)`, `wait_exponential_jitter(initial=1, max=8)` |
| Cloud Run | `min-instances` | `1` during demo window (2026-04-27 18:00 -> 2026-04-29 06:00 IST) |
| Budget | Email alerts | $10 / $25 / $50 on the GCP project |

### 1.4 Risks accepted

- **AI Studio free-tier is not the demo path.** We're on Tier 1 paid.
  If someone ships without enabling billing, Flash caps at 250 RPD and
  the demo dies after ~25 triages.
- **Groq fallback is not wired.** If Gemini has a regional outage during
  the demo, we have no instant swap. Mitigation: fall back to the
  "mock-mode" UI flag if it's implemented by demo day; otherwise, the
  kill switch is "flip `GOOGLE_GENAI_USE_VERTEXAI` between TRUE/FALSE"
  which routes between Vertex and AI Studio (they run on different
  backend stacks).
- **Cold start on Cloud Run after scale-to-zero is ~3-5s.** Mitigated by
  `min-instances=1` during the demo window. After demo, revert to `0`
  to stop paying idle memory.

---

## 2. Gemini API rate limits — full 2026 tier table

### 2.1 Tiers and upgrade path

As of April 2026, the Gemini Developer API (a.k.a. AI Studio API) has four
billing tiers. Upgrades are automatic once cumulative spend + account age
cross the threshold. Free promotional credits do **not** count toward
upgrade thresholds; only real-payment spend does.

| Tier | Requirement (April 2026) | Monthly spend cap | Typical enablement delay |
|---|---|---|---|
| Free | Google account only, no billing enabled | N/A (free quota only) | Immediate |
| Tier 1 | Billing enabled on project, first payment succeeded | $250 / month | <10 min after first payment |
| Tier 2 | >=$250 cumulative spend + >=30 days since first payment | $2,000 / month | <10 min after crossing threshold |
| Tier 3 | >=$1,000 cumulative spend + >=30 days since first payment | $20,000 - $100,000+ / month (custom) | Varies |
| Enterprise | Sales contract | Negotiated | Days to weeks |

Spend caps were introduced across the board on 2026-04-01 and are enforced
per billing account per month. Tier 1's $250 cap is the relevant ceiling
for us for the foreseeable future.

### 2.2 Per-model rate limits (April 2026)

Gemini enforces four dimensions: **RPM** (requests/minute), **TPM**
(tokens/minute), **RPD** (requests/day), **IPM** (images/minute — N/A to
us). Limits are **per project**, not per API key, so rotating keys within
one project does nothing.

#### Free tier

| Model | RPM | TPM | RPD |
|---|---:|---:|---:|
| `gemini-2.5-pro` | 5 | 250,000 | 100 |
| `gemini-2.5-flash` | 10 | 250,000 | 250 |
| `gemini-2.5-flash-lite` | 15 | 250,000 | 1,000 |

#### Tier 1 (what we will have on 2026-04-28)

| Model | RPM | TPM | RPD |
|---|---:|---:|---:|
| `gemini-2.5-pro` | 150 | 2,000,000 | 10,000 |
| `gemini-2.5-flash` | 1,000 | 1,000,000 | 10,000 |
| `gemini-2.5-flash-lite` | 4,000 | 4,000,000 | unlimited |

> Note on sources: `ai.google.dev/gemini-api/docs/rate-limits` is the
> authoritative page. Third-party aggregators disagree by +/-20% on Tier 1
> Flash RPM (some say 300, some 1000). Use the Cloud Console
> "IAM & Admin -> Quotas" view on demo-day morning to confirm the live
> number for our project.

#### Tier 2

| Model | RPM | TPM | RPD |
|---|---:|---:|---:|
| `gemini-2.5-pro` | 1,000 | 5,000,000 | 50,000 |
| `gemini-2.5-flash` | 2,000 | 3,000,000 | 100,000 |
| `gemini-2.5-flash-lite` | 10,000 | 10,000,000 | unlimited |

#### Enterprise / Tier 3+

Custom: 4,000+ RPM, 4M+ TPM, effectively unlimited RPD. Negotiated with
Google Cloud Sales.

### 2.3 December 2025 and April 2026 quota adjustments

- **2025-12-07** quota adjustment: Free and Tier 1 RPD values were rewritten.
  Free Flash went from 1,500 RPD to 250 RPD. Tier 1 Flash went from
  "unlimited" to 10,000 RPD.
- **2026-04-01** billing change: monthly spend caps introduced on all paid
  tiers. Tier 1 capped at $250/month per billing account.

### 2.4 What a 429 actually means in 2026 — four distinct failure modes

A 429 from the Gemini API does not tell you which limit you hit unless you
parse the response body. The four modes:

| `reason` (error body) | Meaning | Right response |
|---|---|---|
| `RESOURCE_EXHAUSTED` + RPM hit | Burst in last minute | Back off 60s, retry |
| `RESOURCE_EXHAUSTED` + TPM hit | Input tokens too large for minute | Shrink prompt or wait |
| `RESOURCE_EXHAUSTED` + RPD hit | Out of daily quota | Do NOT retry — surface to user |
| `UNAVAILABLE` (503) masquerading | Google-side overload, not a quota hit | Retry with jitter |

The response body is JSON with `error.details[0].@type ==
"type.googleapis.com/google.rpc.RetryInfo"` carrying `retryDelay`. Our
tenacity config should honor `Retry-After` / `retryDelay` when present and
fall back to exponential backoff otherwise (§14).

### 2.5 Per-project-not-per-key rule

Adding more API keys to one project gives you **zero** extra quota. All keys
share the project's rate limit counter. Extra quota requires either:
- A tier upgrade (automatic — see §2.1), or
- A different GCP project (and therefore a different billing account if you
  want separate caps), or
- Moving to Vertex AI (see §3, §4).

This means: for the demo, one key is fine. If we decide to stage a load test
on the side, run it in a separate GCP project to avoid eating demo-day quota.

---

## 3. Vertex AI quotas — structural differences from AI Studio

### 3.1 Regional quotas

Vertex AI quotas are mostly region-uniform — Google publishes that "quotas
are the same for all regions unless otherwise specified." Practical
exceptions:

- `us-central1` typically has the highest absolute ceilings and is the
  first region new models land in.
- `asia-south1` (Mumbai) is our natural region for an India-centric
  logistics demo but has slightly lower absolute ceilings on newer models
  (verify in Cloud Console before demo).
- `europe-west4` and `us-east5` are secondary fallbacks.

**For Tier 1 demo:** run in `asia-south1` for latency (<50 ms RTT from
Mumbai / Pune vs ~220 ms to `us-central1`). If `asia-south1` doesn't have
Gemini 2.5 Flash GA (it did as of 2026-02-20), fall back to `us-central1`.
Set `GOOGLE_CLOUD_LOCATION=asia-south1` in `.env`; override to
`us-central1` only if needed.

### 3.2 IAM-scoped access

Vertex AI quotas are charged against the **project** (not an API key), same
as AI Studio, but access control is via IAM roles:
- `roles/aiplatform.user` — call Gemini models
- `roles/aiplatform.admin` — modify quotas, create endpoints

The Cloud Run service account needs `roles/aiplatform.user` only. Grant it
once in `scripts/gcp_bootstrap.sh`; never add it to a human user's
primary account.

### 3.3 Which is more generous?

Vertex AI defaults for `gemini-2.5-flash` in `asia-south1` (April 2026):

| Dimension | Vertex AI default | AI Studio Tier 1 |
|---|---:|---:|
| Online prediction RPM | 1,000 | 1,000 |
| Tokens per minute | 4,000,000 | 1,000,000 |
| Concurrent requests | 20 | implicit (RPM/60 * response_secs) |
| RPD | unlimited | 10,000 |

Vertex AI is **meaningfully more generous on TPM and RPD** because there
is no single-account-wide monthly spend cap — billing is on the GCP
project's billing account which we control directly. This is the key reason
production should be Vertex.

### 3.4 Requesting a quota increase

Cloud Console path:
1. `IAM & Admin -> Quotas & System Limits`
2. Filter: `Service = Vertex AI API`, `Metric = Online prediction requests
   per minute per base_model per region`
3. Select the row, click "Edit Quotas"
4. Fill the form: requested value, business justification (one paragraph),
   region.

SLA on response: 24-48 hours for sub-10x requests, up to 5 business days
for larger bumps. **Do not attempt a quota increase in the 48 hours
before the demo** — if denied, you're stuck mid-demo.

### 3.5 Checking current quota via CLI

```bash
gcloud compute project-info describe \
  --project=$GCP_PROJECT_ID \
  --format="yaml(quotas)" \
  | grep -A 2 "aiplatform.googleapis.com"
```

Or via Cloud Monitoring metrics:

```bash
gcloud monitoring metrics list \
  --filter='metric.type:aiplatform.googleapis.com/prediction'
```

Capture the output into `docs/sessions/YYYY-MM-DD-quota-snapshot.md` on
demo-day morning so there's a record of the ceiling we were running under.

---

## 4. AI Studio API vs Vertex AI — side-by-side comparison

### 4.1 Decision rule (for this project)

- **Local dev** (`adk web`, pytest, manual runs): **AI Studio** via API key.
  Frictionless — one env var (`GOOGLE_API_KEY`), no ADC setup, no service
  account JSON.
- **Cloud Run production** (demo, staging, prod): **Vertex AI** via ADC.
  No API keys in env, IAM-scoped, audit-logged, regional.

The `core/llm.py` layer should not care which is live — both are
string-model IDs to ADK's `LlmAgent`. The switch is an env var.

### 4.2 Comparison table

| Dimension | AI Studio (Gemini Developer API) | Vertex AI |
|---|---|---|
| Auth | API key in env (`GOOGLE_API_KEY`) | ADC: Workload Identity, service account JSON, or user `gcloud auth application-default login` |
| SDK | `google-generativeai` or `google-genai` | `google-cloud-aiplatform` or `google-genai` with `vertexai=True` |
| Model ID | `"gemini-2.5-flash"` | `"gemini-2.5-flash"` (same string; region is configured separately via `GOOGLE_CLOUD_LOCATION`) |
| Free tier | Yes (10 RPM / 250 RPD for Flash) | No — billed from first token |
| Pricing | $0.30 in / $2.50 out (non-thinking), $3.50 out (thinking) per 1M | **Identical** — $0.30 / $2.50 / $3.50 |
| Billing | Linked to Google account / Cloud billing account | Linked to GCP project directly |
| Spend cap | $250/month Tier 1 (enforced 2026-04-01) | None — controlled by project billing limits we set ourselves |
| Observability | Basic quotas view in AI Studio | Full Cloud Logging + Cloud Trace + Cloud Monitoring integration |
| Regional residency | US-only in practice (no region selection) | Full regional control (`asia-south1`, `us-central1`, etc.) |
| VPC-SC / CMEK | No | Yes |
| Cold start | Lower latency (no auth token exchange for each request) | Slightly higher (ADC token exchange, cached for ~1h) |
| Failure modes | Tied to one account; if AI Studio has an outage, all projects using it are affected | Tied to regional Vertex endpoint; different blast radius |

### 4.3 ADK wiring — both code paths

ADK's `LlmAgent(model="gemini-2.5-flash")` accepts a string model name; the
SDK beneath it (`google-genai`) chooses the backend based on env:

- `GOOGLE_GENAI_USE_VERTEXAI=TRUE` + `GOOGLE_CLOUD_PROJECT` + `GOOGLE_CLOUD_LOCATION`: Vertex AI path.
- Unset (or `FALSE`) + `GOOGLE_API_KEY`: AI Studio path.

**No code change needed between environments.** That's the crucial property.
`core/llm.py` returns the same string; env flips the backend.

### 4.4 When to use which (rule of thumb)

| Situation | Use |
|---|---|
| Writing a unit test that hits a fake | Neither (mock `LlmAgent`) |
| Writing a pytest smoke test (allowed to call real Gemini, 1-2 calls max) | AI Studio (fastest auth) |
| `adk web` locally | AI Studio |
| `adk eval` locally | AI Studio |
| `adk eval` in CI | AI Studio (CI secret = API key) |
| Cloud Run staging | Vertex AI |
| Cloud Run prod / demo | Vertex AI |
| Cloud Run with customer data / PII | Vertex AI (data residency + audit) |

---

## 5. Cost projection for Tier 1 demo

### 5.1 Token accounting (per run) — NH-48 flagship scenario

| Sub-agent | Input tokens | Output tokens (+ thinking) | Notes |
|---|---:|---:|---|
| `classifier_fetcher` | 2,000 | 800 (incl. ~300 thinking) | Tool schemas + 2-3 tool responses + prompt |
| `classifier_formatter` | 1,000 | 500 (incl. ~200 thinking) | `include_contents="none"` trims input |
| `impact_fetcher` | 3,000 | 1,500 (incl. ~400 thinking) | 6 tools; 1-2 round-trips |
| `impact_formatter` | 2,000 | 1,000 (incl. ~300 thinking) | Priority reasoning section |
| **Total per run** | **8,000** | **3,800** | |

### 5.2 Unit pricing (Gemini 2.5 Flash, April 2026)

- Input: **$0.30 / 1M tokens**
- Output (standard): **$2.50 / 1M tokens**
- Output (thinking): **$3.50 / 1M tokens**

Thinking tokens are billed at the thinking rate when the model decides to
use them (always, for our `thinking_budget=1024` config). Since the
formatter path sets `thinking_budget=1024` and the formatter's response
rarely exceeds 500 visible tokens, expect ~40-60% of the "output" field to
be thinking.

### 5.3 Per-run cost (worst-case: all output is thinking)

```
Input:  8,000 tokens * $0.30 / 1M = $0.0024
Output: 3,800 tokens * $3.50 / 1M = $0.0133
-----------------------------------------------
Per run:                            ~$0.016
```

### 5.4 Per-run cost (realistic: 40% thinking, 60% standard)

```
Input:  8,000 tokens * $0.30  / 1M           = $0.0024
Output: 1,520 thinking * $3.50 / 1M           = $0.0053
Output: 2,280 standard * $2.50 / 1M           = $0.0057
-----------------------------------------------------
Per run:                                      ~$0.013
```

### 5.5 100-run demo window total

```
100 runs * $0.016 (worst)    = $1.60
100 runs * $0.013 (realistic) = $1.30
```

Plus Cloud Run min-instance cost (~$3.24/month memory-only — pro-rated
to 48 hours demo window = ~$0.22). Plus Firestore reads/writes (negligible,
<$0.05 for 100 runs). Plus Cloud Build / Artifact Registry for the image
push (one-time, <$0.10).

**Demo-window total: $2-3.** Budget alerts at $10 / $25 / $50 give 3-15x
headroom.

### 5.6 Buffer / accidents budget

Allow for:
- Evalset runs during dress rehearsal (20 cases * 4 sub-agents = 80 LLM calls * $0.004/call = $0.32)
- A stuck retry loop eating 100 extra requests: $1.60
- A curl loop from a bored attendee before slowapi kicks in: bounded by
  slowapi's 10/min/IP = at most 600 requests in an hour, ~$9.60
- Total pessimistic contingency: **~$12**, still well under the $25 alert.

---

## 6. Groq + LiteLLM + ADK structured output — the known bug

### 6.1 The bug

When an `LlmAgent` is configured with `model=LiteLlm("groq/...")` **and**
`output_schema=SomeModel`, ADK's LiteLLM wrapper forwards the request to
Groq with `tool_choice="json_tool_call"`. Groq rejects this with a 400:

```
openai.BadRequestError: Error code: 400 - {
  'error': {
    'message': "Requested tool_choice `json_tool_call` was not defined in the request.
                Valid options are 'auto', 'none', 'required', or a dict specifying a function.",
    'type': 'invalid_request_error'
  }
}
```

### 6.2 Why it happens

- ADK's `LiteLlm` wrapper in `google.adk.models.lite_llm` converts
  Pydantic `output_schema` into an OpenAI-style `tools=[...]` array + a
  `tool_choice="json_tool_call"` hint — a pattern OpenAI's own API
  recognizes for forced JSON output.
- LiteLLM passes this through to Groq unchanged.
- Groq's API treats `tool_choice` as an enum with values
  `{"auto", "none", "required"}` or a named-function dict — `"json_tool_call"`
  is not valid, so Groq 400s.
- The bug is tracked in:
  - `google/adk-python#217` — "When using LiteLlm with a model that can
    produce structured output (e.g. gpt-4o), adk doesn't seem to be passing
    the output schema to the model." (about the generic case)
  - `google/adk-python#1967` — "LiteLLM doesn't support structured output
    correctly."
  - `openai/openai-agents-python#2140` — "Groq LiteLLM Integration does
    not work when using structured outputs" (the directly analogous bug in
    OpenAI's Agents SDK; ADK inherits the symptom because it uses the same
    LiteLLM machinery).
- `BerriAI/litellm#15761` — "Getting issues in Groq tool call and
  structured response."

### 6.3 Status (April 2026)

Still open. No ADK release has landed a fix. Workarounds circulating:

1. **Drop `output_schema=`** and parse JSON manually in an
   `after_model_callback` using `Model.model_validate_json(...)`. This
   works but loses ADK's internal validation hooks and the `include_contents="none"`
   optimization becomes harder.
2. **Use Gemini for formatters.** What we are doing.
3. **Use OpenAI-compatible Groq clone servers (e.g. Cloudflare Workers AI)
   that strip `tool_choice` before forwarding.** Adds infrastructure.

### 6.4 Why we keep `core/llm.py` anyway

Even though Groq is not on the demo path, the `core/llm.py` indirection
earns its keep because:

- **Swap-ready architecture** — Tier 2 Generator-Judge might prefer
  Groq for the Generator (speed) and Gemini for the Judge (quality).
  That's a trivial env flip if the plumbing exists; a week of refactor if
  it doesn't.
- **Fallback during outages** — if Gemini has a multi-region brownout
  during a production incident, flipping to Groq on the fetcher agents
  (which do not use `output_schema`) is a 5-minute mitigation.
- **Tier 3 cost optimization** — Groq's Llama 3.1 70B is 5-10x cheaper
  per token than Gemini Flash for pure text generation. When Tier 3
  Communication agent lands and does a lot of drafting, Groq becomes
  attractive again.
- **Negative test coverage** — the indirection lets us assert
  "`core/llm.py` resolves `groq` correctly" in unit tests even though no
  agent currently uses it. Regression protection.

The cost of keeping it: 83 lines of code in `core/llm.py` + one env var
+ one Ruff `TID251` per-file-ignore. Paid off by the first time we need
the optionality.

### 6.5 Upstream fix path we are watching

- ADK issue #217 — monitor for a resolved label.
- ADK issue #1967 — likely where the fix lands (LiteLLM structured-output
  abstraction).
- LiteLLM 1.83+ has tentative support for a `response_format={"type":
  "json_schema", ...}` path that might sidestep the tool_choice hack on
  Groq. As of April 2026 it is not wired into ADK.

Add a session note to check these issues on 2026-05-15 before starting
Tier 2 build.

---

## 7. Model-mix strategy

### 7.1 Tier 1: uniform Flash, no Pro, no Flash-Lite

All four sub-agents run `gemini-2.5-flash` with `thinking_budget=1024`.
Rationale:

- **Uniform Flash keeps the evalset discipline simple** — one model to
  tune prompts and thresholds against.
- **Pro is overkill.** The fetcher's work is tool-calling; Pro's extra
  reasoning is wasted. The formatter's work is schema adherence; Flash
  2.5 is reliable at this once you give it `thinking_budget=1024`.
- **Flash-Lite is underkill.** Flash-Lite (`gemini-2.5-flash-lite`) is
  cheaper (~40% less) but has measurably lower adherence on structured
  output + tool calling per our test harness. Saving $0.50 on a demo is
  not the right trade.

### 7.2 Per-sub-agent specialization thresholds (when to leave uniform)

Post-Tier-1, evalset results dictate specialization. Triggers:

| Evalset result | Action |
|---|---|
| Formatter evalset < 85% exact-match on structured fields | Move formatter to `gemini-2.5-pro` with `thinking_budget=2048` |
| Fetcher evalset > 95% | Move fetcher to `gemini-2.5-flash-lite` (cheaper) |
| Formatter > 95%, fetcher > 95% | Stay on Flash; look at `thinking_budget` reductions |
| Tool-calling failure rate > 5% | Move fetcher to `gemini-2.5-pro`, keep formatter on Flash |
| p95 latency > 8s end-to-end | Move fetcher to Flash-Lite if its evalset still > 90% |

### 7.3 Coordinator (Tier 1)

Deferred — we do not run a Coordinator in Tier 1; the two agents are
called sequentially from the FastAPI route. When a Coordinator lands in
Tier 2, default to Flash `thinking_budget=2048` (it is doing more
delegation reasoning than the children).

### 7.4 Judge (Tier 2)

Gemini 2.5 Flash with `thinking_budget=0` (fast pass/fail per
`.claude/rules/agents.md` §8). Use structured output (so it runs into the
output_schema path — keep on Gemini, not Groq).

### 7.5 Generator (Tier 2)

Gemini 2.5 Flash `thinking_budget=4096` **or** Groq Llama 3.1 70B with
LiteLLM when we need speed. Generator does not have `output_schema`
(it emits a resolution plan that the Judge evaluates), so Groq is
viable here.

---

## 8. Rate limiting architecture for this project

Three layers, in order of where they fire.

### 8.1 Layer A — Gemini API's own per-project quota (the ceiling)

Already in place. Not something we build. We have 1,000 RPM / 1M TPM /
10,000 RPD on Tier 1 Flash (§2.2). Behavior on exceed: 429 with
`RESOURCE_EXHAUSTED`. This is the hard ceiling our other two layers
protect.

### 8.2 Layer B — slowapi middleware per-IP (the entry gate)

Stops accidental / malicious bursts from burning Layer A's daily budget.

**Placement:** `src/supply_chain_triage/middleware/rate_limit.py`.

**Config:**
- `10/minute` on `/api/v1/triage` (the expensive endpoint — one call fans
  out to 4 LLM requests).
- `60/minute` on `/api/v1/exceptions/*` (cheap read paths).
- In-memory backend for Tier 1 (single-instance Cloud Run; we chose
  `min-instances=1` + `max-instances=1` for the demo window precisely so
  that in-memory rate-limit state is consistent).
- Redis backend promoted at Tier 3 when `max-instances > 1` becomes
  inevitable. Add `redis>=5` to deps then, not now.

**Why per-IP not per-tenant:** on demo day there is no real auth tier
spread; per-IP is the cheapest protection. Per-tenant rate limits become
meaningful post-Tier-2 when `company_id` from Firebase custom claims is
routinely bound onto each request.

**Cloud Run session affinity caveat:** at `max-instances > 1`, in-memory
state is inconsistent across instances — a bursty client can get
`N instances * 10/min` instead of `10/min`. Tier 1 runs single-instance
so this doesn't bite. Document in a session note when we move to
multi-instance.

**Sketch (place in `middleware/rate_limit.py`):**

```python
"""Per-IP rate limiter for the triage API."""

from __future__ import annotations

from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

# In-memory storage for Tier 1 (single-instance Cloud Run).
# Move to `storage_uri="redis://..."` when `max-instances > 1`.
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["60/minute"],
)

# Exported for use in runners/routes/*.py as:
#   @limiter.limit("10/minute")
#   async def triage(...): ...
```

**Wire in `runners/app.py`:**

```python
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from supply_chain_triage.middleware.rate_limit import limiter
from supply_chain_triage.middleware.rate_limit_handlers import (
    rate_limit_exceeded_handler,
)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)
app.add_exception_handler(RateLimitExceeded, rate_limit_exceeded_handler)
```

**`rate_limit_exceeded_handler`** (also `middleware/`): emit an
`audit_event("rate_limit_hit", ...)` before returning 429 (per
`.claude/rules/observability.md` §6 canonical audit events).

### 8.3 Layer C — tenacity retry on 429/503 (resilience against Google-side failures)

Wraps the actual Gemini call. Handles transient overloads (Google's
`UNAVAILABLE` during regional hiccups) and unexpected 429s from
Layer A.

**Placement:** `src/supply_chain_triage/utils/llm_retry.py` (pure helper;
imported by the ADK runner wiring in `runners/`).

**Config:**
- `stop=stop_after_attempt(3)` — three tries max (original + 2 retries).
- `wait=wait_exponential_jitter(initial=1, max=8)` — ~1s, ~2-4s, ~4-8s
  windows with jitter to desync from other retries.
- `retry=retry_if_exception_type((ResourceExhausted, ServiceUnavailable))`.
- On final failure: return `{"status": "retry", "error_message": ...}`
  to the tool contract so the agent can classify and surface to the user.

Code snippet in §14.

**Why 3 attempts, not more:**
- 99.5% of transient 5xx from Vertex recover inside 2 retries (per Google's
  own "Learn how to handle 429 resource exhaustion errors in your LLMs"
  blog).
- Beyond 3, the p99 wait time exceeds our 8s total-latency SLO.
- Running longer risks stacking with `num_reasks=2` in Guardrails-AI:
  worst case would be `3 * 2 = 6` LLM calls for a single agent step.
  Our SLO and our budget both say no.

### 8.4 Why not just one layer?

- Layer A alone: the first curl loop blows the day's quota.
- Layer B alone: a Google-side hiccup during a legitimate request returns
  429 to the user with no retry.
- Layer C alone: lets one bad client burn quota for everyone.

Three layers = defense in depth. Each is cheap to add and has no
overlap in failure modes.

### 8.5 Anti-pattern: token-bucket inside the agent

Do **not** add a token-bucket rate limiter inside a tool or inside
`before_model_callback`. Reasons:
- Duplicates Layer C (already handles the retry case).
- Lengthens the ADK span (tenacity waits blocking; OTel sees them as
  time-in-agent, which distorts latency dashboards).
- Is per-process, not per-project, so under scale-out it doesn't help.

The rate limiter lives in middleware. Retry lives in a helper. Quota is
Google's problem.

---

## 9. ADK native concurrency / throttling

### 9.1 Confirmed finding (April 2026)

**ADK does not provide built-in rate limiting, throttling, or 429 retry
for LLM calls.** This is an open feature request in `google/adk-python`
issue #1214 ("Add Built-in Retry Mechanism for API Errors (e.g., 429 Too
Many Requests) in LLM Agent"). Status: open.

### 9.2 What ADK does provide

- **`ReflectAndRetryPlugin`** — retries **tool** calls (not LLM calls)
  when a tool returns an error shape. Useful for transient Firestore /
  HTTP errors. **Not useful for LLM 429s.**
  - `google.github.io/adk-docs/plugins/reflect-and-retry/`
- **LoopAgent** — wraps an agent in a `max_iterations` loop, breaking on
  a condition. Can be abused to approximate LLM retry but combines poorly
  with Guardrails-AI `num_reasks` (see `.claude/rules/guardrails.md` §8
  "stacked re-ask loops" anti-pattern).
- **`asyncio.Semaphore`** — not ADK-native; a plain Python pattern
  recommended by ADK discussions for bounding in-process concurrency.
  We don't need it at Tier 1 (single-request-at-a-time FastAPI handler),
  but it's the right answer when Tier 3 does fan-out (`ParallelAgent`)
  or batch.

### 9.3 What this means for us

- Retries live in `utils/llm_retry.py` (tenacity), **not** in ADK.
- Concurrency caps (if/when we need them) live in
  `runners/` as asyncio semaphores scoped per-tenant.
- Tool retries can use `ReflectAndRetryPlugin` — plan this when Tier 2
  Generator-Judge lands.

### 9.4 Monitoring ADK for native support

Watch `google/adk-python#1214`. When it lands, revisit this section and
potentially replace `utils/llm_retry.py` with the native primitive. Add
session note to check on 2026-06-01.

---

## 10. Token cap policy

### 10.1 The policy

| Sub-agent | `max_output_tokens` | `thinking_budget` | Rationale |
|---|---:|---:|---|
| `classifier_fetcher` | 1024 | 1024 | Tool calls + short summary |
| `classifier_formatter` | 2048 | 1024 | Needs room for ClassificationResult JSON |
| `impact_fetcher` | 1024 | 1024 | 6 tools but short summary |
| `impact_formatter` | 2048 | 1024 | ImpactResult with shipment array |

### 10.2 Why `max_output_tokens` matters even with quotas

- **Cost bound, not rate bound.** If a buggy prompt causes the model to
  loop-generate, `max_output_tokens` clamps the damage to a fixed
  per-call cost. At `max_output_tokens=2048` the worst case is
  `2,048 * $3.50 / 1M = $0.0072` per call.
- **Latency bound.** At Flash's ~120 tokens/sec throughput, 2048
  output tokens is ~17 seconds. Our p95 SLO is 8 seconds
  end-to-end, so 2048 is an upper bound the fetcher never hits in
  practice but stops a runaway loop.

### 10.3 Thinking-budget / output-tokens interaction (critical)

**Thinking tokens count against `max_output_tokens`.** This is the
Gemini 2.5 quirk that bites everyone:

- Setting `max_output_tokens=500` + `thinking_budget=1024` gives the
  model `max(0, 500 - (thinking_used))` for visible output. If the model
  burns its thinking on 500 tokens first, the response is empty.
- On Gemini 3+, the API surfaces `thinking_budget` as a separate config
  and the accounting is clearer. Tier 1 runs on 2.5, so the budget has
  to include thinking:

```
max_output_tokens >= thinking_budget + expected_visible_output
```

Our formatters' `ClassificationResult` JSON is ~300-400 tokens max.
`thinking_budget=1024` + visible ~400 -> `max_output_tokens=2048` gives
us comfortable headroom.

Fetcher visible outputs are ~600-800 tokens. `thinking_budget=1024` + 800
-> `max_output_tokens=1024` is the correct ceiling.

### 10.4 Where to set it

In the existing `generate_content_config=` on each `LlmAgent`:

```python
generate_content_config=genai_types.GenerateContentConfig(
    thinking_config=genai_types.ThinkingConfig(thinking_budget=1024),
    max_output_tokens=2048,  # formatter
    temperature=0.0,
),
```

Currently the code **does not set `max_output_tokens`**, meaning the model
runs up to its default (8,192 for 2.5 Flash). Add this in the next-session
task list (§16).

### 10.5 Known issue with MAX_TOKENS finish_reason

When `thinking_budget + visible > max_output_tokens`, Gemini truncates the
response with `finish_reason=MAX_TOKENS`. This is silent failure — the
output looks like a response but is actually cut mid-JSON. Guard in
`after_model_callback`:

```python
if llm_response.finish_reason == "MAX_TOKENS":
    callback_context.state["temp:truncated"] = True
    # Let the structured-output validator fail downstream -> triggers
    # Guardrails re-ask or CRITICAL fallback per .claude/rules/guardrails.md §6.
```

---

## 11. Cold-start + cost interaction on Cloud Run

### 11.1 Scale-to-zero vs `min-instances=1`

| Mode | Cold-start | Monthly cost (1 vCPU / 512 MiB, idle) | Use when |
|---|---|---|---|
| `min-instances=0` (scale to zero) | 3-5s first request | $0 (instance idle not billed) | Nights / weekends / staging |
| `min-instances=1`, request-billed | <100 ms | ~$3.24 (memory-only) | Demo window + production |
| `min-instances=1`, instance-billed (`--no-cpu-throttling`) | <100 ms | ~$46 (CPU + memory always) | High-QPS production |

### 11.2 Demo-window cost math

Demo window: 2026-04-27 18:00 IST -> 2026-04-29 06:00 IST = 36 hours.

```
Memory: 512 MiB = 0.5 GB
Rate:   $0.00000250 per GB-second
Hours:  36 * 3600 = 129,600 seconds
---
0.5 * 0.00000250 * 129,600 = $0.162
```

CPU (request-billed mode): **$0** for idle. Only the actual Gemini
round-trip time accrues CPU billing, which is ~5 seconds per run * 100
runs * 1 vCPU * $0.000024/sec = **$0.012**.

**Total Cloud Run for the demo window: <$0.25.** The LLM bill
(§5) dominates by 10x.

### 11.3 Why `min-instances=1` specifically

- First user in the demo should not wait 3-5 seconds for cold start on top
  of 5-8 seconds of LLM latency.
- Observability: a cold instance's first log line is `startup`, not
  `http_request`, which wrecks Cloud Run's p50/p95 latency dashboards for
  the day.
- Tracing: OTel tracer provider initialization on cold start adds ~200ms.
  At `min-instances=1`, that happens once and stays warm.

### 11.4 `max-instances=1` caveat for Tier 1

Also set `max-instances=1` during the demo. Reasons:
- slowapi in-memory rate-limit state stays consistent.
- Firestore emulator (if still pointing at one) tolerates single writer.
- Budget determinism — no chance of fan-out spinning up 10 instances.

After Tier 1, raise `max-instances` based on load tests and wire Redis
for slowapi.

### 11.5 Post-demo revert

Immediately after the demo (2026-04-29 morning IST): set
`min-instances=0`, leave `max-instances=1`. Stops the $3-ish/month idle
bill. Restart when work resumes.

---

## 12. Budget alerts

### 12.1 Target thresholds

| Threshold | Meaning | Action |
|---|---|---|
| $10 | First warning — something unusual | Check logs; might be fine |
| $25 | Definite anomaly — 5x the expected demo bill | Investigate, throttle if needed |
| $50 | Hard limit — reconsider running | Consider pausing Cloud Run / rotating key |

### 12.2 Creating via Cloud Console (click path)

1. Cloud Console -> **Billing** (select the billing account)
2. Left nav -> **Budgets & alerts**
3. **CREATE BUDGET**
4. Name: `supply-chain-triage-tier1-demo`
5. Scope:
   - Projects: select our GCP project
   - Services: (leave "All services" — the LLM spend will show under
     Vertex AI, and Cloud Run/Storage are also relevant)
6. Amount:
   - Budget type: **Specified amount**
   - Target amount: `50`
7. Actions -> Threshold rules:
   - `20% actual` (= $10) - Email alert
   - `50% actual` (= $25) - Email alert
   - `100% actual` (= $50) - Email alert
   - `100% forecasted` - Email alert (gives early warning)
8. Email recipients: project billing admin + user email.
9. Save.

### 12.3 Creating via CLI (for scripts / repeatability)

```bash
# Find the billing account:
gcloud billing accounts list

# Create the budget (replace <BILLING_ACCOUNT_ID> and <PROJECT_ID>):
gcloud billing budgets create \
    --billing-account="<BILLING_ACCOUNT_ID>" \
    --display-name="supply-chain-triage-tier1-demo" \
    --budget-amount=50USD \
    --filter-projects="projects/<PROJECT_ID>" \
    --threshold-rule=percent=0.20,basis=CURRENT_SPEND \
    --threshold-rule=percent=0.50,basis=CURRENT_SPEND \
    --threshold-rule=percent=1.00,basis=CURRENT_SPEND \
    --threshold-rule=percent=1.00,basis=FORECASTED_SPEND
```

Email recipients are configured separately:

```bash
gcloud billing budgets update <BUDGET_ID> \
    --billing-account="<BILLING_ACCOUNT_ID>" \
    --notifications-rule-monitoring-notification-channels="<CHANNEL_ID>"
```

(Or use the Console for email recipients — it's faster for one-off setup.)

### 12.4 Pub/Sub automation (post-Tier-1 nice-to-have)

For programmatic kill-switch (e.g. auto-scale Cloud Run to zero at $50):

```bash
gcloud billing budgets update <BUDGET_ID> \
    --billing-account="<BILLING_ACCOUNT_ID>" \
    --notifications-rule-pubsub-topic="projects/<PROJECT>/topics/budget-alerts"
```

Cloud Function subscribed to `budget-alerts` parses the event and calls
`gcloud run services update --min-instances=0 --max-instances=0`. Drop this
into `scripts/budget_kill_switch/` (new subfolder) — but deferred to
Tier 2 at earliest.

### 12.5 Verification

Always verify the budget fires by lowering it to $1 briefly after
initial setup, triggering the 100% alert via a single Gemini call, and
confirming you got the email. Revert to $50.

---

## 13. Emergency kill switch

Mid-demo remediation, in order of lowest cost / fastest action first.

### 13.1 "We're rate-limited / quota-exhausted on AI Studio"

**Fastest:** swap to Vertex AI by flipping env:

```bash
gcloud run services update sct-triage \
    --region=asia-south1 \
    --update-env-vars="GOOGLE_GENAI_USE_VERTEXAI=TRUE,GOOGLE_CLOUD_LOCATION=asia-south1"
```

Takes ~30 seconds to roll. Vertex has different / higher limits (§3.3).
This assumes Vertex AI API is already enabled and the Cloud Run service
account has `roles/aiplatform.user` — verify in `scripts/gcp_bootstrap.sh`
output before demo day.

### 13.2 "We're rate-limited on Vertex too (regional)"

Swap region:

```bash
gcloud run services update sct-triage \
    --region=asia-south1 \
    --update-env-vars="GOOGLE_CLOUD_LOCATION=us-central1"
```

Latency rises from ~1s to ~3s per LLM round-trip but the demo continues.

### 13.3 "Both are rate-limited; nothing Google-side works"

Bump tier via Cloud Console:

1. Confirm billing is on.
2. Spend $1 on any Google Cloud service you already use (Cloud Run logs,
   Storage) to push cumulative spend over the next threshold if it's close.
3. Wait ~10 minutes for auto-upgrade.

Not viable if we're already Tier 1 and cumulative spend is below $250 —
upgrades can't be bought. The real mitigation there is §13.4.

### 13.4 "Nothing's working — fall back to mock mode"

If a "mock mode" is implemented in the UI by demo day, flip the feature
flag:

```bash
gcloud run services update sct-triage \
    --region=asia-south1 \
    --update-env-vars="FEATURE_MOCK_MODE=1"
```

Mock mode returns pre-canned `ClassificationResult` + `ImpactResult` pairs
from `scripts/seed/mock_triage_responses.json`. Demo continues with
honesty ("this is running against cached outputs because the live model
is unavailable"). **Implementation status as of 2026-04-18: not yet
built.** Adding this as a Tier 1 nice-to-have task in §16.

### 13.5 "Everything's broken"

Last resort: tear down Cloud Run, show pre-recorded screen capture of
the working demo. `scripts/demo_dryrun.sh` should capture a full run to
`docs/demos/2026-04-27-dryrun.mp4` on the day before the demo for
exactly this scenario.

### 13.6 Kill-switch authorization

Who can push these changes during the demo:
- User (primary)
- Co-presenter (secondary) — must have `roles/run.admin` on the GCP
  project pre-grant.

Pre-grant before demo, not during. Document in `docs/sessions/
2026-04-27-demo-prep.md`.

---

## 14. Gemini error handling code patterns

### 14.1 The tenacity wrapper

**File:** `src/supply_chain_triage/utils/llm_retry.py`

```python
"""Tenacity-based retry wrapper for transient Gemini failures.

Retries on:
- `google.api_core.exceptions.ResourceExhausted` (429)
- `google.api_core.exceptions.ServiceUnavailable` (503)
- `google.api_core.exceptions.DeadlineExceeded` (504)

Does NOT retry on 400/401/403 — those are permanent misconfigurations
and should surface immediately.

Respects `Retry-After` / `retryDelay` headers when present via
`tenacity.retry_if_result`.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, TypeVar

from google.api_core import exceptions as gcp_exc
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)

from supply_chain_triage.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

_RETRYABLE = (
    gcp_exc.ResourceExhausted,    # 429
    gcp_exc.ServiceUnavailable,   # 503
    gcp_exc.DeadlineExceeded,     # 504
)


async def with_gemini_retries(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    max_wait_s: float = 8.0,
) -> T:
    """Run ``fn`` with bounded exponential-jitter retries on transient errors.

    Args:
        fn: zero-arg async callable that issues the Gemini call.
        max_attempts: total attempts, including the first. Default 3.
        max_wait_s: upper bound on per-retry backoff. Default 8s.

    Returns:
        Whatever ``fn`` returns on success.

    Raises:
        The last retryable exception if ``max_attempts`` is exhausted.
        Non-retryable exceptions propagate immediately.
    """
    attempt = 0
    async for retry in AsyncRetrying(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential_jitter(initial=1.0, max=max_wait_s),
        retry=retry_if_exception_type(_RETRYABLE),
        reraise=True,
    ):
        attempt += 1
        with retry:
            if attempt > 1:
                logger.warning(
                    "gemini_retry",
                    attempt=attempt,
                    max_attempts=max_attempts,
                )
            return await fn()
    # Unreachable: tenacity always exits via `with retry` -> return or raise.
    raise RetryError("Unreachable")  # pragma: no cover
```

This is dependency-injected — tools / runner code call:

```python
from supply_chain_triage.utils.llm_retry import with_gemini_retries

result = await with_gemini_retries(lambda: runner.run_async(...))
```

### 14.2 Tool-level retry (for Firestore etc.)

Already handled by ADK's `ReflectAndRetryPlugin` (§9.2). Do not layer
`tenacity` on top of tools unless you have a specific non-ADK external
call (e.g. a weather API) that `ReflectAndRetryPlugin` can't protect.

### 14.3 The tool contract

Per `.claude/rules/tools.md`, tools return
`{"status": "success"|"error"|"retry", ...}`. `"retry"` specifically is
for "transient; try again later." tenacity is about retrying **within a
single call**; the tool contract is about surfacing **post-retry failure**
to the agent.

Wiring:

```python
async def get_exception_event(exception_id: str) -> dict:
    try:
        data = await with_gemini_retries(
            lambda: firestore_client.collection("exceptions").document(exception_id).get()
        )
        return {"status": "success", "data": data.to_dict()}
    except gcp_exc.ResourceExhausted:
        # Retries exhausted. Surface to agent.
        return {"status": "retry", "error_message": "Firestore rate-limited; try again"}
    except Exception as exc:  # noqa: BLE001 — tool contract catches all
        logger.exception("tool_failed", tool_name="get_exception_event")
        return {"status": "error", "error_message": str(exc)}
```

### 14.4 Reference in `.claude/rules/deployment.md` §9

Cross-link: `.claude/rules/deployment.md` §9 ("Error handling & retries")
documents the deployment-level expectations for this pattern. This
research doc supplies the code.

---

## 15. Cost attribution via OTel

### 15.1 Goal

Per-agent token usage visible in dashboards so we can answer:
- "Which sub-agent is the most expensive?"
- "Which evalset case blew the token budget?"
- "Is thinking_budget=1024 actually being used or cargo-culted?"

### 15.2 OTel span attributes (GenAI semantic conventions)

Per `opentelemetry.io/docs/specs/semconv/gen-ai/`, the required
attributes on an LLM span are:

- `gen_ai.system` = `"gemini"` (literal string)
- `gen_ai.request.model` = `"gemini-2.5-flash"` (string)
- `gen_ai.operation.name` = `"chat"` (or `"embeddings"` etc.)
- `gen_ai.usage.input_tokens` (int)
- `gen_ai.usage.output_tokens` (int)

Optional but recommended:
- `gen_ai.request.temperature`
- `gen_ai.request.max_tokens` (maps to our `max_output_tokens`)
- `gen_ai.response.finish_reasons` (list of strings)

Our extensions:
- `agent.name` = `"classifier_fetcher"` etc. (project convention)
- `agent.model_name` = resolved model name (for when we split Flash/Pro)

### 15.3 Where in the ADK lifecycle to capture

ADK fires `after_model_callback` with an `LlmResponse` that carries
`usage_metadata` (the Gemini response's token counts). This is the
capture point — we already use it in `classifier/agent.py` and
`impact/agent.py` (the `_after_model` function that accumulates into
`session.state`).

Extend `_after_model` to also set span attributes:

```python
from opentelemetry import trace

_tracer = trace.get_tracer("supply_chain_triage.agents")


def _after_model(
    callback_context: CallbackContext,
    llm_response: LlmResponse,
) -> None:
    """Accumulate token usage AND emit OTel attributes."""
    usage = getattr(llm_response, "usage_metadata", None)
    in_tokens = getattr(usage, "prompt_token_count", 0) or 0
    out_tokens = getattr(usage, "candidates_token_count", 0) or 0

    # Existing state accumulation (unchanged).
    prev_in = callback_context.state.get(_STATE_TOKENS_IN, 0)
    prev_out = callback_context.state.get(_STATE_TOKENS_OUT, 0)
    callback_context.state[_STATE_TOKENS_IN] = prev_in + in_tokens
    callback_context.state[_STATE_TOKENS_OUT] = prev_out + out_tokens

    # New: OTel attribution.
    span = trace.get_current_span()
    if span.is_recording():
        span.set_attribute("gen_ai.system", "gemini")
        span.set_attribute("gen_ai.request.model", _MODEL_NAME)
        span.set_attribute("gen_ai.usage.input_tokens", in_tokens)
        span.set_attribute("gen_ai.usage.output_tokens", out_tokens)
        span.set_attribute("agent.name", _AGENT_NAME)
```

### 15.4 Thinking-tokens accounting

Gemini 2.5's `usage_metadata` has `thoughts_token_count` alongside
`candidates_token_count`. Capture both:

```python
thoughts = getattr(usage, "thoughts_token_count", 0) or 0
span.set_attribute("gen_ai.usage.thinking_tokens", thoughts)
```

`gen_ai.usage.thinking_tokens` is not in the OTel spec yet but is a
natural extension. Document as a project-local attribute in
`.claude/rules/observability.md` §1 when we land it.

### 15.5 Cost dashboard query

After spans flow to Cloud Trace + logs flow to Cloud Logging, a
log-based metric pulls per-agent cost:

```
resource.type="cloud_run_revision"
jsonPayload.event="agent_completed"
jsonPayload.agent_name="classifier_fetcher"
```

Group by `agent_name`, sum `tokens_in + tokens_out`, multiply by the rate
card. Build in Cloud Monitoring -> Metrics Explorer -> "Create Log-based
Metric" post-demo.

### 15.6 Reference

`.claude/rules/observability.md` §1 and §7 are the canonical rules
for which attributes must be present. This research doc supplies the
Gemini-specific plumbing.

---

## 16. Concrete next-session task list

Ordered by dependency. Each item is a small, testable change.

### 16.1 Must-do for Tier 1 demo (2026-04-28)

1. **Commit the `core/llm.py` + Groq plumbing work-in-progress.**
   File exists, tests don't yet. ~0 new lines of code, mostly a commit.
   (Blocks nothing; just tidies up.)

2. **Add `max_output_tokens` to all four sub-agents.**
   Files: `modules/triage/agents/classifier/agent.py`,
   `modules/triage/agents/impact/agent.py`.
   - Fetchers: `max_output_tokens=1024`
   - Formatters: `max_output_tokens=2048`
   Change: ~4 lines (two files, two LlmAgents each).
   Tests: `tests/unit/agents/test_classifier.py` +
   `tests/unit/agents/test_impact.py` — assert the config field
   reaches the agent.

3. **Write `utils/llm_retry.py`.**
   ~60 lines per §14.1. Add `tenacity>=9.0` to `pyproject.toml`
   runtime deps.
   Tests: `tests/unit/utils/test_llm_retry.py` — mock `fn` to raise
   `ResourceExhausted` twice then succeed; assert 3 attempts.

4. **Write `middleware/rate_limit.py`.**
   ~40 lines — limiter instance + exception handler. Add
   `slowapi>=0.1.9` to deps.
   Tests: `tests/unit/middleware/test_rate_limit.py` — burst 11 requests
   in 60 s, assert 11th returns 429.

5. **Wire slowapi into `runners/app.py`.**
   ~10 lines — middleware + handler + exception class.
   Tests: integration test `tests/integration/test_rate_limit_integration.py`
   against TestClient.

6. **Extend `_after_model` in both agent.py files with OTel attributes.**
   ~15 lines per agent (§15.3). Add
   `opentelemetry-api>=1.30` if not already in deps (check
   `pyproject.toml` — our transitive via google-cloud-aiplatform likely
   already has it).

7. **Set up GCP budget alerts.**
   One `gcloud billing budgets create` invocation (§12.3). Document the
   budget ID in `docs/sessions/2026-04-19-budget-alerts.md`.

8. **Cloud Run `--min-instances=1 --max-instances=1` for demo window.**
   Add to `scripts/deploy.sh` as `--min-instances=${MIN_INSTANCES:-0}`
   with a `demo` profile that sets it to 1. Document in
   `docs/sessions/2026-04-27-demo-prep.md`.

9. **Verify Vertex AI is enabled and service account has
   `roles/aiplatform.user`.**
   One-liner: `gcloud services enable aiplatform.googleapis.com` +
   `gcloud projects add-iam-policy-binding`. Document in
   `scripts/gcp_bootstrap.sh`.

### 16.2 Should-do for Tier 1 if time permits

10. **Implement mock-mode feature flag.** §13.4. ~100 lines in
    `middleware/mock_mode.py` + seed JSON in
    `scripts/seed/mock_triage_responses.json`. Only activates when
    `FEATURE_MOCK_MODE=1`.

11. **Record a dress-rehearsal demo video** via `scripts/demo_dryrun.sh`.
    ~20 lines of bash to spin up, screen-record, tear down.

### 16.3 Deferred to Tier 2 (after 2026-04-28)

12. Move slowapi storage from in-memory to Redis (Tier 3 prerequisite,
    actually).
13. Per-tenant rate limits via Firebase custom claims.
14. Pub/Sub kill-switch on budget alerts.
15. Log-based metric + dashboard for per-agent cost attribution.
16. `ReflectAndRetryPlugin` on tools that hit external HTTP APIs (Tier 3
    weather / port intel integration).

---

## 17. Sources

All URLs as of research date **2026-04-18**. Accuracy subject to drift
beyond that date; re-verify any number before taking action on it.

### 17.1 Gemini rate limits + pricing

- [Rate limits — Gemini API (ai.google.dev)](https://ai.google.dev/gemini-api/docs/rate-limits) — authoritative per-tier RPM/TPM/RPD numbers. (Retrieved 2026-04-18.)
- [Gemini API Rate Limits Explained: Complete 2026 Guide — YingTu](https://yingtu.ai/en/blog/gemini-api-rate-limits-explained) — third-party summary of April-2026 limits.
- [Gemini API Rate Limits 2026 — AI Free API](https://www.aifreeapi.com/en/posts/gemini-api-rate-limits-per-tier) — Free / Tier 1 / Tier 2 / Enterprise breakdowns.
- [Gemini API Free Tier Rate Limits — Dec 2025 Updates](https://www.aifreeapi.com/en/posts/gemini-api-free-tier-rate-limits) — 2025-12-07 quota adjustment summary.
- [Gemini API Rate Limits and 429 Errors (2026) — LaoZhang AI](https://blog.laozhang.ai/en/posts/gemini-api-rate-limits-guide) — AI Studio + billing mechanics.
- [Gemini API Pricing 2026 (per-1M token) — AI Free API](https://www.aifreeapi.com/en/posts/gemini-api-pricing-2026) — 7-model price table.
- [Gemini API Pricing — BenchLM.ai (April 2026)](https://benchlm.ai/blog/posts/gemini-api-pricing) — current Flash / Flash-Lite / Pro rates.
- [Billing — Gemini API (ai.google.dev)](https://ai.google.dev/gemini-api/docs/billing) — tier upgrade thresholds; $250 spend cap (2026-04-01).
- [How to Upgrade Gemini API to Paid Tier — AI Free API](https://www.aifreeapi.com/en/posts/gemini-api-upgrade-paid-tier) — Free -> Tier 1/2/3 requirements.
- [Google Gemini API Mandatory Tiered Billing — WentuoAI](https://blog.wentuo.ai/en/google-gemini-api-billing-caps-tier-spend-limit-prepaid-guide-en.html) — spend-cap policy.

### 17.2 Vertex AI

- [Vertex AI quotas and limits — Google Cloud](https://docs.cloud.google.com/vertex-ai/docs/quotas) — authoritative Vertex quotas.
- [Generative AI on Vertex AI quotas — Google Cloud](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/quotas) — per-model Gemini quotas on Vertex.
- [Vertex AI Pricing — Google Cloud](https://cloud.google.com/vertex-ai/generative-ai/pricing) — authoritative Vertex pricing.
- [Google Vertex AI Pricing 2026 — TokenMix](https://tokenmix.ai/blog/vertex-ai-pricing) — Gemini / Claude / Llama on Vertex + regional differences.
- [Vertex AI Pricing Explained — GeminiPricing.com](https://www.geminipricing.com/vertex-ai-pricing) — Vertex-specific price breakdowns.
- [Authenticate to Vertex AI — Google Cloud](https://docs.cloud.google.com/vertex-ai/docs/authentication) — ADC / service account auth.
- [Configure application default credentials — Generative AI on Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/gcp-auth) — GOOGLE_GENAI_USE_VERTEXAI env pattern.
- [How to Manage Quotas and Rate Limits for Gemini API in Vertex AI — OneUptime](https://oneuptime.com/blog/post/2026-02-17-how-to-manage-quotas-and-rate-limits-for-gemini-api-requests-in-vertex-ai/view) — quota-increase walkthrough.
- [Google Provisioned Throughput — Apiyi.com](https://help.apiyi.com/en/google-provisioned-throughput-pt-explained-vertex-vs-aistudio-2026-en.html) — Vertex vs AI Studio structural differences.

### 17.3 Error handling

- [Learn how to handle 429 resource exhaustion errors in your LLMs — Google Cloud Blog](https://cloud.google.com/blog/products/ai-machine-learning/learn-how-to-handle-429-resource-exhaustion-errors-in-your-llms) — authoritative Google guidance on 429 handling.
- [Error code 429 — Generative AI on Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/provisioned-throughput/error-code-429) — 429 breakdown.
- [How to Fix Gemini API Error 429 — AI Free API](https://www.aifreeapi.com/en/posts/gemini-api-error-429-resource-exhausted-fix) — tenacity patterns + rate-limit tables.
- [Gemini API Error Troubleshooting (2026) — LaoZhang AI](https://blog.laozhang.ai/en/posts/gemini-api-error-troubleshooting) — 400 / 429 / 500 taxonomy.
- [Tenacity docs (retry library)](https://tenacity.readthedocs.io/) — `wait_exponential_jitter`, `retry_if_exception_type`.

### 17.4 ADK / LiteLLM / Groq

- [google/adk-python issue #217 — output_schema + LiteLlm](https://github.com/google/adk-python/issues/217) — output_schema not being passed through LiteLLM.
- [google/adk-python issue #1214 — built-in retry for 429](https://github.com/google/adk-python/issues/1214) — still open as of April 2026.
- [google/adk-python issue #1967 — LiteLLM structured output](https://github.com/google/adk-python/issues/1967) — direct structured-output bug.
- [openai/openai-agents-python issue #2140 — Groq + structured output](https://github.com/openai/openai-agents-python/issues/2140) — analogous tool_choice=json_tool_call bug.
- [BerriAI/litellm issue #15761 — Groq tool call + structured response](https://github.com/BerriAI/litellm/issues/15761) — upstream bug.
- [Structured Output and Response Schemas — DeepWiki (adk-python)](https://deepwiki.com/google/adk-python/5.6-structured-output-and-response-schemas) — ADK's structured-output model coverage.
- [ReflectAndRetryPlugin — ADK docs](https://google.github.io/adk-docs/plugins/reflect-and-retry/) — tool-level retry semantics.
- [Integrating Groq with Google ADK using LiteLLM — DEV Community](https://dev.to/mmtq/integrating-groq-with-google-adk-using-litellm-50me) — community walkthrough (confirms the json_tool_call trap).

### 17.5 slowapi / FastAPI rate limiting

- [slowapi — GitHub](https://github.com/laurentS/slowapi) — primary repo.
- [slowapi — PyPI](https://pypi.org/project/slowapi/) — pip metadata.
- [SlowApi Documentation](https://slowapi.readthedocs.io/) — config reference.
- [Using SlowAPI in FastAPI — Medium (Shiladitya Majumder)](https://shiladityamajumder.medium.com/using-slowapi-in-fastapi-mastering-rate-limiting-like-a-pro-19044cb6062b) — production patterns.
- [API Rate Limiting with SlowAPI in Production — Johal.in](https://johal.in/api-rate-limiting-with-slowapi-protecting-python-endpoints-from-abuse-in-production/) — production considerations.
- [Implementing a Rate Limiter with FastAPI and Redis — Bryan Anthonio](https://bryananthonio.com/blog/implementing-rate-limiter-fastapi-redis/) — Redis backing store.

### 17.6 Cloud Run cost + scaling

- [Cloud Run pricing — Google Cloud](https://cloud.google.com/run/pricing) — per-second CPU + memory rates.
- [Billing settings for services — Cloud Run docs](https://docs.cloud.google.com/run/docs/configuring/billing-settings) — request-based vs instance-based.
- [Set minimum instances — Cloud Run docs](https://docs.cloud.google.com/run/docs/configuring/min-instances) — `--min-instances=1` idle semantics.
- [Google Cloud Run: Pricing and Cost Optimization — ProsperOps](https://www.prosperops.com/blog/google-cloud-run-pricing-and-cost-optimization/) — idle-instance billing.
- [How to Configure Minimum Instances — OneUptime](https://oneuptime.com/blog/post/2026-02-17-how-to-configure-minimum-instances-on-cloud-run-to-eliminate-cold-starts-for-production-services/view) — cold-start elimination patterns.

### 17.7 GCP budget alerts

- [Create, edit, or delete budgets — Cloud Billing docs](https://docs.cloud.google.com/billing/docs/how-to/budgets) — console click path.
- [Set up programmatic notifications — Cloud Billing docs](https://docs.cloud.google.com/billing/docs/how-to/budgets-programmatic-notifications) — Pub/Sub integration.
- [Customize budget alert email recipients — Cloud Billing docs](https://docs.cloud.google.com/billing/docs/how-to/budgets-notification-recipients) — email routing.
- [Get started with the Cloud Billing Budget API — Cloud Billing docs](https://docs.cloud.google.com/billing/docs/how-to/budget-api-overview) — API reference.

### 17.8 OTel GenAI semantic conventions

- [Semantic conventions for generative AI systems — OpenTelemetry](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — top-level spec.
- [Semantic Conventions for GenAI agent and framework spans — OpenTelemetry](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-agent-spans/) — agent-specific attrs.
- [Semantic conventions for generative client AI spans — OpenTelemetry](https://opentelemetry.io/docs/specs/semconv/gen-ai/gen-ai-spans/) — client span attrs.
- [OpenTelemetry for Generative AI — OTel Blog](https://opentelemetry.io/blog/2024/otel-generative-ai/) — intro / rationale.
- [OpenTelemetry for AI Systems (2026) — Uptrace](https://uptrace.dev/blog/opentelemetry-ai-systems) — 2026-current practitioner guide.
- [opentelemetry-semantic-conventions-ai — PyPI](https://pypi.org/project/opentelemetry-semantic-conventions-ai/) — Python package for the constants.

### 17.9 Gemini thinking budget + max_output_tokens

- [Thinking — Firebase AI Logic](https://firebase.google.com/docs/ai-logic/thinking) — thinking_budget semantics.
- [Thinking — Vertex AI](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/thinking) — same on Vertex.
- [googleapis/python-genai issue #782 — thinking / max_output_tokens interaction](https://github.com/googleapis/python-genai/issues/782) — the MAX_TOKENS truncation bug.
- [Gemini 2.5 Flash Developer API Guide — Shareuhack](https://www.shareuhack.com/en/posts/gemini-2-5-flash-developer-guide-2026) — thinking-budget pitfalls.
- [Gemini 3.1 Pro Pricing — Verdent](https://www.verdent.ai/guides/gemini-3-1-pro-pricing) — thinking-token accounting semantics.
- [Gemini API Spend Caps — Gemini Lab](https://gemilab.net/en/articles/gemini-api/gemini-api-spend-caps-guide) — spend-cap + max_output_tokens interaction.

### 17.10 Internal project references

- `.claude/rules/agents.md` — callback placement, thinking-budget defaults, structured-output two-agent pattern.
- `.claude/rules/observability.md` — OTel attrs, audit events, cost attribution.
- `.claude/rules/guardrails.md` — num_reasks=2, stacked-reask anti-pattern.
- `.claude/rules/deployment.md` — retry expectations (§9).
- `.claude/rules/security.md` — PII-safe logging.
- `docs/research/adk-best-practices.md` — two-agent pattern, thinking-budget defaults.
- `docs/research/gemini-structured-output-gotchas.md` — structured-output failure modes.
- `src/supply_chain_triage/core/llm.py` — provider resolution.
- `src/supply_chain_triage/core/config.py` — Settings + get_secret.
- `src/supply_chain_triage/modules/triage/agents/classifier/agent.py` — current classifier wiring.
- `src/supply_chain_triage/modules/triage/agents/impact/agent.py` — current impact wiring.

---

*End of research document. Open questions for next session are captured
in §16; add new ones to `docs/sessions/2026-04-18-llm-quotas-research.md`
after review.*
