---
title: "The Proper Way to Utilize GCP"
type: research
domains: [deployment, security, infra, gcp, cloud-run, observability]
scope: tier-1
status: active
last_updated: 2026-04-18
author: session-research
review_cadence: before-every-prod-deploy
related_rules:
  - .claude/rules/deployment.md
  - .claude/rules/security.md
  - .claude/rules/observability.md
  - .claude/rules/logging.md
  - .claude/rules/architecture-layers.md
goal: >
  Give the next-session engineer a single file they can open and deploy
  Supply-Chain-Exception-Triage to GCP (asia-south1) correctly, without
  googling. Covers runtime (Cloud Run), data (Firestore), LLM (Vertex AI
  vs AI Studio), secrets (Secret Manager), auth (Workload Identity), obs
  (Cloud Trace + Cloud Logging), cost (budget alerts + $300 credits), and
  CI/CD (GitHub Actions WIF). Tier 1 scope only.
---

# The Proper Way to Utilize GCP — Supply Chain Exception Triage

> User prompt of record (2026-04-18): **"What is the proper way to utilize the GCP? That's what we need to think about."**
>
> This document answers that question at the level of "exhaustive enough to
> execute." Every section is a directly-runnable playbook. If a step is not
> runnable, it is marked `TODO(human)` with the missing input.

---

## 0. How to read this document

1. **Section 1** is a one-paragraph answer. If you're skimming, read it and stop.
2. **Section 2** is the commit-level checklist. Everything else expands one checklist item.
3. **Sections 3-20** are deep dives. Open them only when you are about to do the thing.
4. **Section 21** is the next-session handoff.
5. **Section 22** is sources and dates.

All commands assume:

- `gcloud` >= 500.0.0 (2026-Q1) installed and logged in (`gcloud auth login`).
- Active project set: `gcloud config set project <sct-dev|sct-prod|sct-staging>`.
- Current region default: `gcloud config set run/region asia-south1`.
- Shell: bash on WSL or git-bash on Windows. PowerShell works if you adjust
  line-continuations (`` ` `` instead of `\`).

---

## 1. Executive summary

The "proper GCP way" for this project, at Tier 1, is:

> **Deploy a single FastAPI+ADK container image to Cloud Run in `asia-south1`,
> run it as a purpose-built runtime service account with the minimum IAM set
> (`datastore.user` + `secretmanager.secretAccessor` + `logging.logWriter`
> + `monitoring.metricWriter` + `cloudtrace.agent`, optionally
> `aiplatform.user` when we flip from AI Studio to Vertex), read every secret
> from Secret Manager via `--set-secrets=KEY=secret:latest`, authenticate CI
> from GitHub via Workload Identity Federation (no JSON keys, ever), serve
> the Tier 3 frontend through Firebase Hosting with a rewrite to the Cloud
> Run service, observe the system through Cloud Trace + Cloud Logging +
> Cloud Monitoring wired with `opentelemetry-exporter-gcp-trace` + structlog
> JSON that includes `logging.googleapis.com/trace`, guard cost with billing
> budget alerts at $10 / $25 / $50 and `min-instances=1` only during the demo
> window, and keep the whole surface split across three GCP projects —
> `sct-dev` (iteration), `sct-staging` (optional stable), `sct-prod` (fresh,
> burns the $300 new-user credit).**

That one paragraph is the contract. Everything below executes it.

---

## 2. The proper-GCP checklist (Tier 1, 20 items)

Each item lists **what**, **why**, **where it lives**, and **how we verify**.

| # | What | Why | Where | Verify |
|---|---|---|---|---|
| 1 | Three GCP projects: `sct-dev`, `sct-staging`, `sct-prod` | Blast-radius containment; $300 credits burn in `sct-prod` only | GCP console (billing account in each) | `gcloud projects list \| grep sct-` shows 3 |
| 2 | All projects in `asia-south1` (Mumbai) | Demo + users in India; lowest-latency Gemini + Firestore | `gcloud config` default + `firebase projects:list` | `gcloud config get run/region` → `asia-south1` |
| 3 | One runtime service account per service, not the default SA | Least privilege, blast-radius | `sct-run-sa@<pid>.iam.gserviceaccount.com` | `gcloud run services describe ... --format='value(spec.template.spec.serviceAccountName)'` |
| 4 | Workload Identity on Cloud Run (no JSON keys in image or env) | Keyless, rotation-free, auditable | Runtime SA attached via `gcloud run services update --service-account` | `gcloud iam service-accounts keys list --iam-account=...` → zero user-managed keys |
| 5 | Workload Identity Federation for GitHub Actions → GCP | CI deploys without long-lived keys | Workload Identity Pool + Provider in `sct-prod` + `sct-dev` | Any `.github/workflows/deploy*.yml` uses `google-github-actions/auth` with `workload_identity_provider:` |
| 6 | All secrets in Secret Manager; mounted via `--set-secrets=:latest` | Rotation story, no secrets in env inspector | Secret Manager in each project | `gcloud run services describe` → `spec.template.spec.containers[].env[].valueFrom.secretKeyRef` populated |
| 7 | `.env.template` holds **names only**; `.env` is gitignored and for dev | Prevents accidental commit of real values | Repo root | `git check-ignore .env` succeeds |
| 8 | Firestore in Native mode, `asia-south1` | Colocated with Cloud Run → sub-ms RPC | `firestore.googleapis.com` enabled per project | `gcloud firestore databases list --project=sct-prod` |
| 9 | `google-generativeai` (AI Studio) now; `vertexai` only if needed | AI Studio is cheaper + simpler; Vertex earns its way in | `core/llm.py` factory, flag via `LLM_PROVIDER` | Settings validator rejects unknown provider |
| 10 | Cloud Run min-instances=0 dev/staging; =1 only during demo window | $0 idle for dev; zero cold starts for judges | `gcloud run services update --min-instances=1 --no-cpu-throttling` | `gcloud run services describe ... --format='value(spec.template.metadata.annotations)'` |
| 11 | Cloud Run `startup CPU boost` on prod revision | Halves cold-start on N→N+1 scale | `--cpu-boost` on deploy | describe service annotations |
| 12 | Non-root user in Dockerfile; `USER runner` | Least-privilege inside container | `Dockerfile` §9 below | `docker run ... whoami` → `runner` |
| 13 | OTel wired via `opentelemetry-exporter-gcp-trace` + FastAPI instrumentor | Cost attribution per agent; trace↔log correlation on Cloud Run | `utils/observability.py` (new), imported by `runners/app.py` lifespan | Cloud Trace UI shows traces with `agent.name` attribute |
| 14 | Structured JSON logs with `severity` + `logging.googleapis.com/trace` | Cloud Run auto-correlates logs → trace | `utils/logging.py` processor chain (extend §11 below) | Cloud Logging query `traceId:*` returns joined traces |
| 15 | Billing budget alerts: $10 / $25 / $50 on `sct-prod` | Cap credit burn; catch a runaway Gemini loop before billing period | `gcloud billing budgets create ...` (§12) | `gcloud billing budgets list --billing-account=...` shows the budget |
| 16 | CORS allowlist pinned to the Firebase Hosting origin | No wildcard; enforces §11 of security.md | `settings.cors_allowed_origins` | Startup validator rejects `*` in staging/prod |
| 17 | Audit Logs enabled for Firestore, Secret Manager, IAM | Forensic trail; answers "who accessed what" | Admin → Audit Logs, set `DATA_READ`/`DATA_WRITE`/`ADMIN_READ` per service | `gcloud logging read 'logName:cloudaudit.googleapis.com'` returns hits |
| 18 | HTTPS only (Cloud Run enforces); HSTS via security-headers middleware | Already in §5 of security.md | `middleware/security_headers.py` | `curl -I` against prod URL shows `strict-transport-security` |
| 19 | Unused APIs disabled | Reduces attack surface; prevents accidental billable enablement | `gcloud services disable ...` (list in §13) | `gcloud services list --enabled` matches the allowlist in §13 |
| 20 | Multi-revision rollback ready: traffic split by revision, not service | Revert in one command if demo regresses | `gcloud run services update-traffic --to-revisions=<prev>=100` | See §18 |

That table is the "what we commit to for Tier 1." Everything else in this
file is the how.

---

## 3. Multi-project architecture

### 3.1. Projects and their roles

| Project ID | Role | Billing | Region | Notes |
|---|---|---|---|---|
| `sct-dev` | Iteration, ephemeral resources, per-dev branches | Paid billing account (Akash's) | `asia-south1` | Already exists. Keep using it. |
| `sct-staging` | Optional. A stable, always-on dev mirror for tougher integration runs | Same billing account as dev | `asia-south1` | Skip for Tier 1 if friction > benefit. Spin up before demo prep if needed. |
| `sct-prod` | Demo target. Fresh, never paid before. Uses $300 new-user credits. | Separate, freshly-created billing account for the $300 offer | `asia-south1` | Critical: the *billing account* has to be eligible for Free Trial, not just the project. See §16. |

### 3.2. Naming conventions (applies to every project)

| Resource | Naming |
|---|---|
| Service account (runtime) | `sct-run-sa@<pid>.iam.gserviceaccount.com` |
| Service account (CI/CD) | `sct-cicd-sa@<pid>.iam.gserviceaccount.com` |
| Service account (admin/seed) | `sct-admin-sa@<pid>.iam.gserviceaccount.com` |
| Cloud Run service | `sct-api` (the single FastAPI+ADK service) |
| Secret Manager secret | `sct-gemini-api-key`, `sct-groq-api-key`, `sct-firebase-admin-json` (if ever) |
| Artifact Registry repo | `sct-images` (Docker format, `asia-south1`) |
| Workload Identity Pool | `sct-github-pool` |
| Workload Identity Provider | `sct-github-provider` |

Prefixing everything with `sct-` makes `gcloud` tab-completion unambiguous
when multiple projects are combined (e.g. via org-level IAM search).

### 3.3. Per-project environment variables

The *same* container image runs in all three projects. Environment
variables are the switch. See the `Settings` model in
`src/supply_chain_triage/core/config.py` — all of these flow through
pydantic-settings.

```
# Cloud Run env vars set via --set-env-vars
ENV=prod                               # dev | staging | prod
GCP_PROJECT_ID=sct-prod
FIREBASE_PROJECT_ID=sct-prod           # same as GCP project in single-project mode
LLM_PROVIDER=gemini                    # gemini | groq
LLM_MODEL_ID=gemini-2.5-flash
LOG_LEVEL=INFO
LOG_TO_FILES=0                         # Cloud Run has no writable filesystem we want
CORS_ALLOWED_ORIGINS=https://sct-prod.web.app
```

Secrets are mounted via `--set-secrets` (§6), not `--set-env-vars`.

### 3.4. Terraform vs gcloud

Tier 1: **gcloud scripts**, not Terraform. Rationale:
- Demo pressure. Terraform adds state management overhead we don't need.
- The resource count is small (3 projects × ~10 resources each).
- `scripts/gcp_bootstrap.sh` can be re-run idempotently.

Flip to Terraform at Tier 2 when `port_intel/` lands and the resource
count doubles. The `deployment.md` rule §5 already flags "prod + staging:
Terraform only, no `gcloud run deploy` from laptops" — **that flips at
Tier 2.** For the hackathon demo, `gcloud` scripts from laptops are fine,
so long as they're committed.

---

## 4. Service account design

Three service accounts per project. Do not reuse SAs across projects.

### 4.1. Runtime SA — `sct-run-sa`

Attached to the Cloud Run service. It is *the* identity the FastAPI+ADK
process runs as.

**Required roles (Tier 1, AI Studio path):**

| Role | Scope | Why |
|---|---|---|
| `roles/datastore.user` | project | Firestore read/write |
| `roles/secretmanager.secretAccessor` | each secret (not project) | Mount Gemini API key, etc. |
| `roles/logging.logWriter` | project | Cloud Logging stdout ingestion |
| `roles/monitoring.metricWriter` | project | Custom metrics (token burn per agent) |
| `roles/cloudtrace.agent` | project | Cloud Trace span ingestion |

**Add if flipping to Vertex AI (§7):**

| Role | Scope | Why |
|---|---|---|
| `roles/aiplatform.user` | project | Calls `aiplatform.googleapis.com` prediction endpoints in `asia-south1` |

**Create + bind (one-time, per project):**

```bash
PROJECT=sct-prod
SA=sct-run-sa

gcloud iam service-accounts create "$SA" \
  --project="$PROJECT" \
  --display-name="SCT runtime service account"

SA_EMAIL="${SA}@${PROJECT}.iam.gserviceaccount.com"

for ROLE in \
    roles/datastore.user \
    roles/logging.logWriter \
    roles/monitoring.metricWriter \
    roles/cloudtrace.agent
do
  gcloud projects add-iam-policy-binding "$PROJECT" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="$ROLE" \
    --condition=None
done

# Scope secretAccessor to each specific secret, not project-wide.
for SECRET in sct-gemini-api-key sct-groq-api-key; do
  gcloud secrets add-iam-policy-binding "$SECRET" \
    --project="$PROJECT" \
    --member="serviceAccount:${SA_EMAIL}" \
    --role="roles/secretmanager.secretAccessor"
done
```

Scoping `secretAccessor` per-secret is deliberate — it is the single
highest-leverage least-privilege move in this project. A compromised SA
cannot enumerate secrets it doesn't have permission to name.

### 4.2. CI/CD SA — `sct-cicd-sa`

Used by GitHub Actions via Workload Identity Federation (§15). Never has
a JSON key.

**Required roles:**

| Role | Scope | Why |
|---|---|---|
| `roles/run.admin` | project | Deploy / update Cloud Run services |
| `roles/iam.serviceAccountUser` | `sct-run-sa` | Impersonate runtime SA to attach it to new revisions |
| `roles/artifactregistry.writer` | `sct-images` repo | Push container images |
| `roles/cloudbuild.builds.editor` | project (only if using Cloud Build) | Submit builds |
| `roles/storage.objectAdmin` | `gs://<project>_cloudbuild/` bucket (if Cloud Build) | Build context upload |

`iam.serviceAccountUser` *must* be scoped to `sct-run-sa` (the resource),
not the project. Grant it with:

```bash
gcloud iam service-accounts add-iam-policy-binding "sct-run-sa@${PROJECT}.iam.gserviceaccount.com" \
  --project="$PROJECT" \
  --member="serviceAccount:sct-cicd-sa@${PROJECT}.iam.gserviceaccount.com" \
  --role="roles/iam.serviceAccountUser"
```

### 4.3. Admin/seed SA — `sct-admin-sa`

Used by operator scripts in `scripts/*.py` (e.g. `seed_firestore.py`,
`set_custom_claims.py`). Only activated from a developer laptop via
`gcloud auth application-default login --impersonate-service-account`,
never in CI, never in the runtime.

**Required roles:**

| Role | Scope | Why |
|---|---|---|
| `roles/datastore.owner` | project (dev only) | Bulk writes for seed data |
| `roles/firebaseauth.admin` | project | `set_custom_claims` needs it |
| `roles/secretmanager.admin` | project | Rotate secrets (create new versions) |

This SA is *powerful*. Two rules:
1. **Never** make it the runtime SA.
2. Use impersonation (`--impersonate-service-account`), not an exported key.

### 4.4. What we explicitly don't grant

- **No `roles/owner`** on any SA.
- **No `roles/editor`** on runtime or CI/CD — too broad.
- **No project-level `roles/secretmanager.secretAccessor`** on runtime SA.
- **No cross-project IAM bindings.** Each project owns its own SAs.
- **No Service Account Key creation permission** (`iam.serviceAccounts.keys.create`) outside `sct-admin-sa`, and even there we don't actually create keys — Workload Identity replaces them.

---

## 5. Workload Identity end-to-end (Cloud Run)

### 5.1. What "Workload Identity" means on Cloud Run specifically

Cloud Run's term for the feature is **service identity**: the service
runs as a service account, and any Google Cloud SDK call from inside the
container auto-authenticates via the metadata server — no key file, no
`GOOGLE_APPLICATION_CREDENTIALS`, no runtime `gcloud auth activate-service-account`.

The metadata server is at `169.254.169.254` inside the container; Google
libraries (`google-auth`, `firebase-admin`, `google-cloud-firestore`,
`google-cloud-secret-manager`, `vertexai`) detect the Cloud Run
environment and use it automatically.

### 5.2. Step-by-step

1. **Create the runtime SA** (§4.1) and grant roles.
2. **Attach it to the Cloud Run service** at deploy time:
   ```bash
   gcloud run services update sct-api \
     --project=sct-prod \
     --region=asia-south1 \
     --service-account=sct-run-sa@sct-prod.iam.gserviceaccount.com
   ```
   or on first deploy:
   ```bash
   gcloud run deploy sct-api \
     --service-account=sct-run-sa@sct-prod.iam.gserviceaccount.com \
     ...
   ```
3. **Remove any JSON keys** that previously existed for this SA:
   ```bash
   # List keys
   gcloud iam service-accounts keys list \
     --iam-account=sct-run-sa@sct-prod.iam.gserviceaccount.com
   # Delete user-managed keys (keep system-managed; they have no fingerprint you create)
   gcloud iam service-accounts keys delete <KEY_ID> \
     --iam-account=sct-run-sa@sct-prod.iam.gserviceaccount.com
   ```
4. **Remove any `GOOGLE_APPLICATION_CREDENTIALS`** from the Cloud Run env vars. Confirm with:
   ```bash
   gcloud run services describe sct-api \
     --region=asia-south1 --project=sct-prod \
     --format='value(spec.template.spec.containers[0].env)'
   ```

### 5.3. Verification

```bash
gcloud run services describe sct-api \
  --region=asia-south1 --project=sct-prod \
  --format='value(spec.template.spec.serviceAccountName)'
# → sct-run-sa@sct-prod.iam.gserviceaccount.com
```

Inside the container, call:

```python
import google.auth
credentials, project = google.auth.default()
# credentials.service_account_email should equal sct-run-sa@sct-prod.iam.gserviceaccount.com
```

### 5.4. The "keyless" contract

- Zero JSON keys on disk in any image layer.
- Zero JSON keys in any Secret Manager secret.
- Zero `GOOGLE_APPLICATION_CREDENTIALS` env vars in Cloud Run config.
- Zero `serviceAccountKey.json` COPY statements in the Dockerfile.
- Zero keys in `.env.template` (names only) or `.env` (local dev).

`.claude/rules/deployment.md` §3 already says this. This section is its
operational form.

---

## 6. Secret Manager end-to-end

### 6.1. Secret inventory (Tier 1)

| Secret name | Content | Rotation cadence |
|---|---|---|
| `sct-gemini-api-key` | Google AI Studio API key | Every 90 days |
| `sct-groq-api-key` | Groq API key (fallback LLM) | Every 90 days |

That's it for Tier 1. Firebase Admin and Firestore use Workload Identity,
not a secret. Do *not* store a `firebase-admin-json` secret.

### 6.2. Create + version

```bash
PROJECT=sct-prod
SECRET=sct-gemini-api-key

# Create the secret (once per project)
gcloud secrets create "$SECRET" \
  --project="$PROJECT" \
  --replication-policy="automatic"

# Add the first version (stdin to avoid shell history)
printf '%s' "$THE_API_KEY" | gcloud secrets versions add "$SECRET" \
  --project="$PROJECT" --data-file=-
```

### 6.3. Mount into Cloud Run

```bash
gcloud run services update sct-api \
  --project=sct-prod --region=asia-south1 \
  --set-secrets=GEMINI_API_KEY=sct-gemini-api-key:latest
```

This turns `GEMINI_API_KEY` into an env var whose value is read from
Secret Manager at revision start. `:latest` is what we want, paired with
the rotation flow below. Pinning to `:3` is safer for "avoid bad rollout"
but forces a config change on every rotation — not worth it for a two-
secret surface.

### 6.4. Rotation flow

1. Generate new API key in AI Studio console.
2. `printf '%s' "$NEW" | gcloud secrets versions add sct-gemini-api-key --data-file=-`
3. `gcloud run services update sct-api --region=asia-south1 --project=sct-prod` (no args — triggers a new revision that reads `:latest`).
4. Wait for the new revision to serve 100% of traffic (default behavior).
5. `gcloud secrets versions disable <OLD_VERSION> --secret=sct-gemini-api-key`
6. After 24h, `gcloud secrets versions destroy <OLD_VERSION> --secret=sct-gemini-api-key`

Do **not** `destroy` immediately — rollback needs the old version alive.

### 6.5. Access auditing

Secret Manager emits Data Access audit logs when enabled. Enable with:

```bash
# Cloud Console → IAM & Admin → Audit Logs
# Service: Secret Manager API
# Check: Data Read, Data Write, Admin Read
```

Query:

```bash
gcloud logging read \
  'protoPayload.serviceName="secretmanager.googleapis.com" AND protoPayload.methodName="google.cloud.secretmanager.v1.SecretManagerService.AccessSecretVersion"' \
  --project=sct-prod --limit=50
```

### 6.6. Pre-demo rotation checklist

24h before demo:
- [ ] Rotate `sct-gemini-api-key` (fresh version, :latest picks up on redeploy).
- [ ] Rotate `sct-groq-api-key` (same).
- [ ] Redeploy `sct-api` to force revision start → reads latest.
- [ ] Verify via /health that the agent can round-trip Gemini.
- [ ] Leave old version *enabled* until demo ends (rollback cushion).

### 6.7. Anti-patterns

- `gcloud secrets versions access latest --secret=... --quiet >> ~/.bash_history` → leaks the secret into shell history. Always `--data-file=-` + stdin.
- Passing secrets via `--set-env-vars` — that bakes them into the revision spec and shows up in `gcloud run services describe`. Use `--set-secrets`.
- Reading Secret Manager at module import — cold-start latency. `core/config.py::get_secret` already lazy-imports the client, keep it that way.
- Creating a `:latest` alias manually (`versions add --alias=latest`) — Secret Manager manages `latest` for you; a manual alias breaks rotation.

---

## 7. Vertex AI setup (only if we flip)

### 7.1. AI Studio vs Vertex — decision

| Dimension | AI Studio (`google-generativeai`) | Vertex AI (`vertexai` SDK) |
|---|---|---|
| Auth | API key in Secret Manager | Workload Identity via runtime SA |
| Regional residency | API routes globally; no strong `asia-south1` guarantee | `asia-south1` native; data stays in region |
| Pricing | Per-token, single bill line | Per-token, rolls into GCP bill; eligible for $300 credits |
| Quotas | Per-key | Per-project (higher ceilings) |
| Cloud Trace integration | None (we instrument manually) | First-class `aiplatform.googleapis.com` traces |
| SDK surface | `google.generativeai` | `vertexai.generative_models.GenerativeModel` |
| ADK support | Yes, via `LlmAgent(model="gemini-2.5-flash")` | Yes, via `vertexai.init(project, location)` → same model ID |

**Tier 1 default: AI Studio.** Simpler, and the $300 credit covers Vertex
but not AI Studio directly — *but* AI Studio charges against the same
billing account, so it still drains the credit. Practical recommendation:
start with AI Studio; flip only if any of these become true:

- `asia-south1` data residency is a hard requirement (regulatory, not latency).
- Per-key quotas start throttling us during demo.
- We want agent-native Cloud Trace spans (Vertex tags them automatically).

### 7.2. How to flip

1. **Enable Vertex API** in the target project:
   ```bash
   gcloud services enable aiplatform.googleapis.com --project=sct-prod
   ```
2. **Grant `roles/aiplatform.user`** to the runtime SA (§4.1).
3. **Set env vars:**
   ```
   LLM_PROVIDER=vertex
   GCP_PROJECT_ID=sct-prod
   VERTEX_LOCATION=asia-south1
   LLM_MODEL_ID=gemini-2.5-flash-001
   ```
4. **Init in `core/llm.py`** (or equivalent factory):
   ```python
   import vertexai
   vertexai.init(project=settings.gcp_project_id, location="asia-south1")
   ```
5. **Model IDs:** use the pinned form `gemini-2.5-flash-001` on Vertex
   (vs `gemini-2.5-flash` on AI Studio). The pinned suffix on Vertex
   protects against silent model swaps.
6. **Deprecation heads-up:** Gemini 2.5 Pro/Flash/Flash-Lite on Vertex AI
   are scheduled for discontinuation no earlier than **October 16, 2026**
   per Google's announcement. That's post-hackathon, but plan a migration
   to 3.x before Tier 3 lands.

### 7.3. Agent Engine — when not to

Agent Engine is a managed ADK-runtime product. Tier 1: **don't**. Cloud
Run is enough. Flip to Agent Engine only at Tier 2+ when:

- Session state / memory management becomes load-bearing.
- We want managed scaling *within* a long-running agent invocation.
- The Coordinator runs multi-turn conversations that exceed Cloud Run's
  request timeout (default 300s, max 3600s).

For the 2026-04-24 demo, Cloud Run is strictly simpler.

---

## 8. Cloud Run deployment — full playbook

### 8.1. Build + push (local Docker path)

```bash
PROJECT=sct-prod
REGION=asia-south1
REPO=sct-images
TAG=$(git rev-parse --short HEAD)
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/sct-api:${TAG}"

# One-time per project
gcloud artifacts repositories create "$REPO" \
  --project="$PROJECT" \
  --repository-format=docker \
  --location="$REGION" \
  --description="SCT container images"

gcloud auth configure-docker "${REGION}-docker.pkg.dev"

# Build + push
docker build -t "$IMAGE" .
docker push "$IMAGE"
```

### 8.2. Build + push (Cloud Build path, recommended for CI)

```bash
gcloud builds submit \
  --project="$PROJECT" \
  --region="$REGION" \
  --tag="$IMAGE"
```

Cloud Build handles the Docker layer cache and avoids a round-trip
through a laptop on slow uplinks. For WSL/Windows dev, this is faster
than local Docker.

### 8.3. First-deploy command

Full command-line — copy-paste and adjust variables:

```bash
gcloud run deploy sct-api \
  --project="$PROJECT" \
  --region="$REGION" \
  --image="$IMAGE" \
  --service-account="sct-run-sa@${PROJECT}.iam.gserviceaccount.com" \
  --cpu=1 \
  --memory=1Gi \
  --concurrency=40 \
  --timeout=300 \
  --min-instances=0 \
  --max-instances=5 \
  --cpu-boost \
  --port=8080 \
  --ingress=all \
  --allow-unauthenticated \
  --execution-environment=gen2 \
  --set-env-vars="ENV=prod,GCP_PROJECT_ID=${PROJECT},FIREBASE_PROJECT_ID=${PROJECT},LLM_PROVIDER=gemini,LLM_MODEL_ID=gemini-2.5-flash,LOG_LEVEL=INFO,LOG_TO_FILES=0,CORS_ALLOWED_ORIGINS=https://${PROJECT}.web.app" \
  --set-secrets="GEMINI_API_KEY=sct-gemini-api-key:latest,GROQ_API_KEY=sct-groq-api-key:latest"
```

Notes:

- `--cpu=1`, `--memory=1Gi`: Gemini calls are I/O-bound; 1 vCPU is plenty. Upsize only if profiling says so.
- `--concurrency=40`: FastAPI+async handles this trivially. If Gemini per-request latency is high, increase to 80.
- `--min-instances=0`: scale-to-zero for dev/staging. Flip to `1` 24h before the demo.
- `--max-instances=5`: cost guardrail. For 100 judges hitting in parallel, bump to 10 — but a budget alert at $10 will scream first.
- `--cpu-boost`: doubles CPU for the first ~10s of an instance. Eliminates most N→N+1 cold-start pain.
- `--execution-environment=gen2`: gVisor gen2, default for new services, better networking perf.
- `--allow-unauthenticated`: only because Firebase Auth handles identity inside the app. If this is a machine-to-machine service (A2A Tier 3), flip to IAM-authenticated and grant `roles/run.invoker` to the caller SA.

### 8.4. Dry-run before production

Cloud Run doesn't have a true dry-run, but these two equivalents catch most issues:

```bash
# Validate the flags parse (no API call)
gcloud run deploy sct-api --project="$PROJECT" --region="$REGION" --image="$IMAGE" \
  --dry-run 2>/dev/null || echo "gcloud does not support --dry-run for Run; use --no-traffic instead"

# Deploy a revision but send 0% traffic to it
gcloud run deploy sct-api ... --no-traffic --tag=canary
# Test against the revision-specific URL:
# https://canary---sct-api-<hash>-<region>.run.app
# Then shift traffic:
gcloud run services update-traffic sct-api --to-tags=canary=100 --region="$REGION"
```

### 8.5. Post-deploy verification

```bash
URL=$(gcloud run services describe sct-api \
  --region="$REGION" --project="$PROJECT" \
  --format='value(status.url)')

# 1. Health check
curl -sf "$URL/health" && echo "healthy"

# 2. SA attached
gcloud run services describe sct-api --region="$REGION" --project="$PROJECT" \
  --format='value(spec.template.spec.serviceAccountName)'

# 3. Secrets mounted
gcloud run services describe sct-api --region="$REGION" --project="$PROJECT" \
  --format='value(spec.template.spec.containers[0].env)' | grep -E 'GEMINI|GROQ'

# 4. Trace is flowing (wait 60s first)
gcloud logging read 'resource.type="cloud_run_revision"' --project="$PROJECT" --limit=5 --freshness=2m
```

### 8.6. What NOT to do

- Do **not** `COPY serviceAccountKey.json` anywhere.
- Do **not** set `GOOGLE_APPLICATION_CREDENTIALS` as a Cloud Run env var.
- Do **not** `--allow-unauthenticated` if the service is expected to be machine-to-machine only (e.g. A2A inter-agent).
- Do **not** pass secrets via `--set-env-vars` — they show up in revision JSON.
- Do **not** bake `.env` files into the image (`.dockerignore` blocks, but be explicit).
- Do **not** deploy from a feature branch to `sct-prod` — only `master` → prod.
- Do **not** deploy without committing the image tag. The git SHA in the tag is the audit trail.

---

## 9. Dockerfile + .dockerignore

The Dockerfile stub in `.claude/rules/deployment.md` §1 is canonical. This
section is the full, copy-pasteable version extended with Cloud Run
specifics.

### 9.1. `Dockerfile`

```dockerfile
# syntax=docker/dockerfile:1.7

# ---------- builder ----------
FROM python:3.13-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    PYTHONDONTWRITEBYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Layer 1: dependency install (fast rebuild when code changes)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev

# Layer 2: project install
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------- runtime ----------
FROM python:3.13-slim

RUN useradd -m -u 1000 runner && \
    apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates \
      tini \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder --chown=runner:runner /app/.venv /app/.venv
COPY --from=builder --chown=runner:runner /app/src /app/src

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8080 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1

USER runner
EXPOSE 8080

# tini is PID 1 → forwards SIGTERM to uvicorn → OTel span shutdown runs
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "supply_chain_triage.runners.app:app", \
     "--host", "0.0.0.0", "--port", "8080", \
     "--workers", "1", "--loop", "uvloop", "--http", "httptools"]
```

Why the additions vs the rules-file stub:

- **`tini`** — guarantees `SIGTERM` propagates to uvicorn, which flushes
  the OTel span processor (`.claude/rules/observability.md` §3). Without
  `tini`, Cloud Run's scale-down kills PID 1 without signal forwarding
  and we lose the last few traces.
- **`ca-certificates`** — some minimal base images drop these; Firestore
  TLS handshake fails without them. Cheap insurance.
- **`--workers 1`** — Cloud Run handles scaling via instance count; in-process worker multiplication doubles memory use. One worker per instance.
- **`uvloop`+`httptools`** — ~20% latency win on async FastAPI.

### 9.2. `.dockerignore`

```
# --- venv + caches ---
.venv/
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.ruff_cache/
.mypy_cache/

# --- dev artifacts ---
tests/
evals/
docs/
.claude/
.github/
.git/
.vscode/
.idea/

# --- secrets + config ---
.env
.env.*
!.env.template
*.pem
*.key
serviceAccountKey*.json

# --- docs + misc ---
*.md
!README.md
LICENSE
Makefile
.pre-commit-config.yaml
.gitignore
.gitleaksignore
.secrets.baseline

# --- build output ---
dist/
build/
*.egg-info/
htmlcov/
coverage.xml
logs/
```

Two things to verify once:

- `!.env.template` — we *do* want the template in the image for
  operator diagnostic ("what env vars does this service expect?"). If
  this feels wrong, drop it — we don't actually read it at runtime.
- `!README.md` — not needed at runtime; omitting it saves a layer.

### 9.3. Lifespan startup

`runners/app.py` lifespan must:
1. Init OTel tracer provider + FastAPI instrumentor.
2. Resolve Secret Manager values (or read from env — `get_secret` handles both).
3. Construct the Firestore async client (`get_firestore_client()` singleton).
4. Register SIGTERM handler → `tracer_provider.shutdown()`.
5. Yield.
6. On shutdown: flush traces, close Firestore client.

Skeleton (put in `runners/app.py`):

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lazy imports — keeps cold start tight
    from supply_chain_triage.utils.observability import init_tracing, shutdown_tracing
    from supply_chain_triage.core.config import get_firestore_client, get_settings

    settings = get_settings()
    tracer_provider = init_tracing(project_id=settings.gcp_project_id)
    app.state.db = get_firestore_client()

    try:
        yield
    finally:
        shutdown_tracing(tracer_provider)
        # AsyncClient doesn't need explicit close in current SDK; noop is safe.
```

---

## 10. Firebase Hosting for the frontend

Tier 1 doesn't have a frontend beyond `/health`. This section prepares the
Tier 3 React dashboard path so we don't re-litigate it.

### 10.1. Why Firebase Hosting (not Cloud Run serving static)

- Global CDN with cached static assets (React bundle). Cloud Run would
  bill a request for every asset.
- Free tier covers 10 GB/month egress, 360 MB/day transfer — fine for a demo.
- Integrates with Cloud Run via `rewrites` — one origin, no CORS
  complications for the browser.
- Integrates with Firebase Auth client SDK for token issuance.

### 10.2. Setup

```bash
cd <repo-root>
firebase login
firebase init hosting
# Choose: Use existing project → sct-prod
# Public directory: frontend/dist (wherever React builds to)
# SPA rewrites: yes → index.html
# GitHub Actions: no (we do this manually or in our own workflow)
```

### 10.3. `firebase.json`

```json
{
  "hosting": {
    "public": "frontend/dist",
    "ignore": ["firebase.json", "**/.*", "**/node_modules/**"],
    "rewrites": [
      {
        "source": "/api/**",
        "run": {
          "serviceId": "sct-api",
          "region": "asia-south1"
        }
      },
      {
        "source": "**",
        "destination": "/index.html"
      }
    ],
    "headers": [
      {
        "source": "**/*.@(js|css|woff2)",
        "headers": [
          { "key": "Cache-Control", "value": "public, max-age=31536000, immutable" }
        ]
      }
    ]
  }
}
```

### 10.4. Deploy

```bash
# Build React first
pushd frontend && npm run build && popd

# Deploy hosting (pushes static assets + updates rewrites)
firebase deploy --only hosting --project=sct-prod
```

Production URL: `https://sct-prod.web.app` (and `sct-prod.firebaseapp.com`).
Pin `CORS_ALLOWED_ORIGINS` to *both* in the Cloud Run env config, though
if the rewrite is set up the browser talks to the Firebase origin only.

### 10.5. CORS implication

With the rewrite, the browser requests `/api/...` on the Firebase Hosting
origin. Firebase Hosting proxies to Cloud Run internally. Browser *never*
sees Cloud Run's `*.run.app` origin → CORS is a non-issue. Still, keep the
allowlist strict:

```python
CORS_ALLOWED_ORIGINS=["https://sct-prod.web.app", "https://sct-prod.firebaseapp.com"]
```

---

## 11. Observability — Cloud Trace + Cloud Logging + Cloud Monitoring

### 11.1. Trace exporter wiring

Put this in `src/supply_chain_triage/utils/observability.py` (new file).
`.claude/rules/architecture-layers.md` §2 "Narrow exception" lets utils
depend on OTel when it's a logging/obs canonical entry point.

```python
"""OpenTelemetry → Cloud Trace exporter + FastAPI instrumentation.

Cold-start hot path — keep imports local to the init function.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from opentelemetry.sdk.trace import TracerProvider


def init_tracing(project_id: str) -> "TracerProvider":
    """Initialize Cloud Trace exporter + FastAPI instrumentor. Idempotent."""
    from opentelemetry import trace
    from opentelemetry.exporter.cloud_trace import CloudTraceSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({
        "service.name": "sct-api",
        "service.version": _git_sha_or_unknown(),
    })
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(CloudTraceSpanExporter(project_id=project_id))
    )
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor().instrument()  # wires middleware automatically
    return provider


def shutdown_tracing(provider: "TracerProvider") -> None:
    """Flush + shutdown. Call from lifespan teardown + SIGTERM handler."""
    provider.shutdown()


def _git_sha_or_unknown() -> str:
    import os
    return os.environ.get("GIT_SHA", "unknown")
```

Add dependencies to `pyproject.toml`:

```toml
"opentelemetry-api>=1.29.0",
"opentelemetry-sdk>=1.29.0",
"opentelemetry-exporter-gcp-trace>=1.9.0",
"opentelemetry-instrumentation-fastapi>=0.50b0",
```

### 11.2. Log-to-trace correlation

Cloud Run auto-correlates logs with traces when log records contain
`logging.googleapis.com/trace` and `logging.googleapis.com/spanId` keys.

Extend the structlog processor chain in `utils/logging.py`:

```python
def _add_trace_context(logger, method_name, event_dict):
    """Inject Cloud Run-recognized trace fields from the active span."""
    from opentelemetry import trace
    span = trace.get_current_span()
    ctx = span.get_span_context()
    if ctx and ctx.is_valid:
        project = os.environ.get("GCP_PROJECT_ID", "")
        event_dict["logging.googleapis.com/trace"] = \
            f"projects/{project}/traces/{format(ctx.trace_id, '032x')}"
        event_dict["logging.googleapis.com/spanId"] = format(ctx.span_id, '016x')
        event_dict["logging.googleapis.com/trace_sampled"] = ctx.trace_flags.sampled
    return event_dict
```

Insert into the processor chain *before* `JSONRenderer`. Cloud Run reads
the JSON, extracts the trace ID, and in the Cloud Logging UI every log
entry links to its Cloud Trace span.

### 11.3. Severity mapping

structlog emits log records with `level` keys; Cloud Run wants `severity`
(uppercase). Add this processor:

```python
_LEVEL_TO_SEVERITY = {
    "debug": "DEBUG", "info": "INFO", "warning": "WARNING",
    "error": "ERROR", "exception": "ERROR", "critical": "CRITICAL",
}

def _map_severity(logger, method_name, event_dict):
    level = event_dict.pop("level", method_name).lower()
    event_dict["severity"] = _LEVEL_TO_SEVERITY.get(level, "DEFAULT")
    return event_dict
```

### 11.4. SIGTERM handler

Already in `.claude/rules/observability.md` §3. In `runners/app.py`:

```python
import signal
from supply_chain_triage.utils.observability import shutdown_tracing

_provider = None  # set during lifespan init

def _on_sigterm(*_):
    if _provider:
        shutdown_tracing(_provider)

signal.signal(signal.SIGTERM, _on_sigterm)
```

The `tini` entrypoint (Dockerfile §9.1) is what makes this work on Cloud
Run. Without `tini`, Cloud Run's SIGTERM goes to PID 1 which is uvicorn,
and handler registration there is racy.

### 11.5. Cloud Monitoring — custom metrics

Token burn per agent is the one custom metric worth wiring for Tier 1.
Use log-based metrics (derived from structured logs), not the custom
metrics API — log-based metrics are free and don't need extra code:

1. In Cloud Console → Logging → Log-based metrics → Create metric.
2. Filter: `resource.type="cloud_run_revision" AND jsonPayload.event="agent_completed"`.
3. Metric type: Counter.
4. Labels: extract `jsonPayload.agent_name`, `jsonPayload.tokens_in`,
   `jsonPayload.tokens_out` as labels / distributions.

Then a Monitoring dashboard with one panel per agent showing tokens over time.

### 11.6. Pre-demo dashboards

Build these in Cloud Console → Monitoring → Dashboards:

1. **SLO dash** — request count, p50/p95/p99 latency, error rate. One row per endpoint.
2. **Agent cost dash** — tokens per agent per minute, total spend estimate.
3. **Firestore dash** — reads/writes per collection, 429 rate.
4. **Cold-start dash** — container startup time, min-instance utilization.

Export each as JSON via `gcloud monitoring dashboards describe ... --format=json > infra/monitoring/<name>.json` and commit to `infra/monitoring/`.

---

## 12. Budget alerts + billing guardrails

### 12.1. The three-threshold pattern

$10 / $25 / $50 on `sct-prod`. Rationale:

- **$10** — "something is happening, take a look." The alert fires before
  anything meaningful is spent. Use this as the early-warning for runaway
  Gemini loops.
- **$25** — "we're burning credits fast; pause or reconfigure."
- **$50** — "hit the brakes." $50 is ~1/6 of the $300 credit — if a hackathon project consumes that, something is wrong (agent retry loop, stuck on `max-instances=50`, etc).

### 12.2. `gcloud billing budgets create` invocation

```bash
BILLING_ACCOUNT=<ACCOUNT_ID>  # e.g. 0X0X0X-0X0X0X-0X0X0X
PROJECT=sct-prod

gcloud billing budgets create \
  --billing-account="$BILLING_ACCOUNT" \
  --display-name="sct-prod tiered budget (demo guardrail)" \
  --budget-amount=50USD \
  --filter-projects="projects/$PROJECT" \
  --threshold-rule=percent=20 \
  --threshold-rule=percent=50 \
  --threshold-rule=percent=100 \
  --threshold-rule=percent=100,basis=forecasted
```

Interpretation:
- Budget cap: $50.
- 20% → $10 (first-tier warning).
- 50% → $25 (mid-tier).
- 100% actual → $50 (hit the cap).
- 100% forecasted → fires earlier, based on projected monthly spend.

### 12.3. Email routing

By default, alerts go to billing administrators + project owners. To add
the dev team:

1. Create a monitoring email channel:
   ```bash
   gcloud alpha monitoring channels create \
     --project="$PROJECT" \
     --display-name="Akash dev email" \
     --type=email \
     --channel-labels=email_address=akashbhargava1992@gmail.com
   ```
2. Pass the channel to the budget via `--notifications-rule-monitoring-notification-channels=...` on create/update, *or* through the Cloud Console (Billing → Budgets → Edit → Manage notifications).

### 12.4. Quota vs budget (relation)

Budget alerts *notify*; they do not *cap*. A runaway loop can exceed the
budget between the alert and manual intervention. For hard caps:

- **Gemini API**: AI Studio and Vertex both expose per-minute quotas. Set
  a low RPM in Vertex AI Console → Quotas for the Gemini model. Cap at
  60 RPM during demo; ADK + classifier/impact run rate is ~5 RPM.
- **Firestore**: no app-level cap is needed — reads/writes are cheap, and
  the `memory/` helper already counts ops for attribution (`observability.md` §8).

### 12.5. Auto-shutoff (nuclear option)

Pub/Sub-wired budget → Cloud Function → `gcloud run services update --max-instances=0`.
Tier 2 work. For Tier 1, the $50 cap + manual intervention is acceptable.

---

## 13. Security hardening — checklist

### 13.1. Disable unused APIs

Enabled APIs = attack surface + billing risk. For Tier 1 Cloud Run +
Firebase + Firestore, the enabled API allowlist is:

```
run.googleapis.com
firestore.googleapis.com
secretmanager.googleapis.com
artifactregistry.googleapis.com
cloudbuild.googleapis.com            # only if using Cloud Build
iam.googleapis.com
iamcredentials.googleapis.com        # required for WIF
cloudresourcemanager.googleapis.com
logging.googleapis.com
monitoring.googleapis.com
cloudtrace.googleapis.com
aiplatform.googleapis.com            # only if flipped to Vertex
firebase.googleapis.com
firebaseauth.googleapis.com
identitytoolkit.googleapis.com
```

Disable everything else. Script:

```bash
ALLOW="run firestore secretmanager artifactregistry cloudbuild iam iamcredentials cloudresourcemanager logging monitoring cloudtrace firebase firebaseauth identitytoolkit"
gcloud services list --enabled --project="$PROJECT" --format='value(config.name)' | while read api; do
  name="${api%%.*}"
  if ! echo " $ALLOW " | grep -q " $name "; then
    echo "Disabling $api"
    gcloud services disable "$api" --project="$PROJECT" --force
  fi
done
```

### 13.2. Audit Logs

Cloud Audit Logs split into Admin Activity (always-on, free) and Data
Access (opt-in, charged). Enable Data Access for:

- **IAM** — `roles/iam.*` changes.
- **Secret Manager** — every `AccessSecretVersion`.
- **Firestore** — optional; we already log `agent_invoked` with tenant IDs. Enable only during demo for audit completeness.

Via Cloud Console: IAM & Admin → Audit Logs → select service → check
Data Read / Data Write / Admin Read.

### 13.3. Org policies (apply at project level if no org)

Tier 1 doesn't have a GCP Organization (hackathon = personal account),
so org policies are inapplicable. When this moves into a company GCP org
post-hackathon, enforce:

- `constraints/iam.disableServiceAccountKeyCreation` — no more keys.
- `constraints/compute.requireShieldedVm` — not relevant for Cloud Run, but good hygiene for any VM we spin up.
- `constraints/run.allowedIngress` — restrict ingress to internal + load balancer.
- `constraints/run.allowedVPCEgress` — force VPC connector egress (Tier 3 if we add Memorystore).

### 13.4. Cloud Armor (optional, Tier 3)

For Tier 1, not worth the $5/policy monthly. Enable at Tier 3 when:
- The React frontend is live and subject to bot traffic.
- `slowapi` per-user rate limits are wired (security.md §4).
- We want preset WAF rules (OWASP Top 10).

Pattern: Global HTTPS Load Balancer → Cloud Armor policy → Serverless
NEG → Cloud Run. LB adds ~1 min cold-start on first request but then caches.

### 13.5. HTTPS-only + CORS

- Cloud Run **only** serves HTTPS. No action needed.
- HSTS header: already in `middleware/security_headers.py` (security.md §5).
- CORS allowlist: pinned to Firebase Hosting origins (§10.5 above).

### 13.6. PII logging

`utils/logging.py::_drop_pii` is the backstop. Also enable a Cloud
Logging **exclusion filter** that drops any log record containing the
string `api_key` or `Bearer ` — defense-in-depth at the log ingestion
boundary:

```bash
gcloud logging sinks create no-pii-filter \
  logging.googleapis.com/projects/"$PROJECT"/locations/global/buckets/_Default \
  --log-filter='NOT (textPayload:("api_key" OR "Bearer "))' \
  --project="$PROJECT"
```

(Exact syntax: use an exclusion on the `_Default` bucket. Tweak in Cloud
Console if the CLI form confuses — the UI is clearer.)

---

## 14. Regional + data-residency

### 14.1. Why `asia-south1`

- **Users:** India-first app. Mumbai region → ~20-40ms RTT from Delhi,
  Bangalore, Chennai, Mumbai. vs ~180-250ms for `us-central1`.
- **Data residency:** Firestore + Secret Manager + Cloud Run + Vertex AI
  all colocated. No cross-region egress.
- **Gemini availability:** Gemini 2.5 Flash is confirmed available in
  `asia-south1` via Vertex AI as of March 2026 (see §7, Sources §22).

### 14.2. Services to colocate

| Service | Region | Why |
|---|---|---|
| Cloud Run | `asia-south1` | User proximity |
| Firestore | `asia-south1` | Sub-ms RPC from Cloud Run |
| Secret Manager | automatic (global) | Auto-replication; no choice needed |
| Artifact Registry | `asia-south1` | Image pull latency during cold start |
| Vertex AI (if flipped) | `asia-south1` | Data residency + low latency |
| Cloud Logging / Monitoring / Trace | automatic (global) | Can't colocate; negligible impact |

### 14.3. Cross-region egress cost

Internal to `asia-south1` → $0.
`asia-south1` → internet → $0.12/GB (standard tier). The demo traffic is
JSON-small (<10 KB/response); egress cost is effectively zero ($0.01/day
at 1000 requests).

### 14.4. Firebase Hosting — multi-region by default

Firebase Hosting is globally distributed via Google's edge CDN. Static
assets serve from the nearest edge. The `rewrites → run: region` entry
in `firebase.json` pins *dynamic* traffic to `asia-south1`.

---

## 15. CI/CD in GitHub Actions → GCP

### 15.1. One-time: set up Workload Identity Federation for GitHub

```bash
PROJECT=sct-prod
POOL=sct-github-pool
PROVIDER=sct-github-provider
REPO_OWNER=Krrish777           # GitHub user/org
REPO_NAME=Supply-Chain-Exception-Triage

# Get project number (not ID)
PROJECT_NUMBER=$(gcloud projects describe "$PROJECT" --format='value(projectNumber)')

# Create pool
gcloud iam workload-identity-pools create "$POOL" \
  --project="$PROJECT" \
  --location=global \
  --display-name="GitHub Actions pool"

# Create provider
gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
  --project="$PROJECT" \
  --location=global \
  --workload-identity-pool="$POOL" \
  --display-name="GitHub provider" \
  --attribute-mapping="google.subject=assertion.sub,attribute.actor=assertion.actor,attribute.repository=assertion.repository,attribute.ref=assertion.ref" \
  --attribute-condition="attribute.repository == '${REPO_OWNER}/${REPO_NAME}'" \
  --issuer-uri="https://token.actions.githubusercontent.com"

# Bind the CI/CD SA to tokens from this pool+repo
gcloud iam service-accounts add-iam-policy-binding \
  "sct-cicd-sa@${PROJECT}.iam.gserviceaccount.com" \
  --project="$PROJECT" \
  --role="roles/iam.workloadIdentityUser" \
  --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${REPO_OWNER}/${REPO_NAME}"

# Record the provider name for the workflow file
echo "workload_identity_provider: projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}"
```

The `attribute-condition` narrows the token-trust to **only** this one
GitHub repo. Without it, any GitHub Actions workflow in any repo can
authenticate as the SA. Do not omit it.

### 15.2. `.github/workflows/deploy-prod.yml`

```yaml
name: Deploy to sct-prod

on:
  push:
    branches: [master]
    paths:
      - 'src/**'
      - 'pyproject.toml'
      - 'uv.lock'
      - 'Dockerfile'
      - '.github/workflows/deploy-prod.yml'
  workflow_dispatch:

permissions:
  contents: read
  id-token: write   # REQUIRED for WIF

env:
  PROJECT: sct-prod
  REGION: asia-south1
  SERVICE: sct-api
  REPO: sct-images

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Authenticate to GCP (WIF, keyless)
        uses: google-github-actions/auth@v2
        with:
          workload_identity_provider: projects/<PROJECT_NUMBER>/locations/global/workloadIdentityPools/sct-github-pool/providers/sct-github-provider
          service_account: sct-cicd-sa@sct-prod.iam.gserviceaccount.com

      - name: Set up gcloud
        uses: google-github-actions/setup-gcloud@v2

      - name: Set up uv
        uses: astral-sh/setup-uv@v4

      - name: Install deps
        run: uv sync --locked --all-extras

      - name: Ruff + mypy
        run: |
          uv run ruff check .
          uv run mypy src

      - name: Tests (unit only — integration runs against emulators locally)
        run: uv run pytest tests/unit/ -q

      - name: Configure docker auth
        run: gcloud auth configure-docker ${{ env.REGION }}-docker.pkg.dev --quiet

      - name: Build + push image
        env:
          TAG: ${{ github.sha }}
        run: |
          IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/${REPO}/${SERVICE}:${TAG}"
          docker build -t "$IMAGE" .
          docker push "$IMAGE"
          echo "IMAGE=$IMAGE" >> $GITHUB_ENV

      - name: Deploy to Cloud Run
        uses: google-github-actions/deploy-cloudrun@v2
        with:
          service: ${{ env.SERVICE }}
          region: ${{ env.REGION }}
          image: ${{ env.IMAGE }}
          flags: >-
            --service-account=sct-run-sa@sct-prod.iam.gserviceaccount.com
            --cpu=1 --memory=1Gi --concurrency=40 --timeout=300
            --min-instances=0 --max-instances=5
            --cpu-boost --execution-environment=gen2 --port=8080
            --allow-unauthenticated
            --set-env-vars=ENV=prod,GCP_PROJECT_ID=sct-prod,FIREBASE_PROJECT_ID=sct-prod,LLM_PROVIDER=gemini,LLM_MODEL_ID=gemini-2.5-flash,LOG_LEVEL=INFO,LOG_TO_FILES=0,CORS_ALLOWED_ORIGINS=https://sct-prod.web.app,GIT_SHA=${{ github.sha }}
            --set-secrets=GEMINI_API_KEY=sct-gemini-api-key:latest,GROQ_API_KEY=sct-groq-api-key:latest

      - name: Smoke test
        run: |
          URL=$(gcloud run services describe ${SERVICE} --region=${REGION} --project=${PROJECT} --format='value(status.url)')
          curl -sf "$URL/health"
```

### 15.3. Why WIF beats JSON keys

| Dimension | JSON key | WIF |
|---|---|---|
| Rotation | Manual, 30-90 days | Auto, 1h token lifetime |
| Storage | GitHub secret (encrypted at rest, but exists) | Nothing to store |
| Revocation | Delete + rotate all workflows | Remove IAM binding, takes effect instantly |
| Audit | "Used by CI" — which CI? | GitHub org + repo + ref in the token claims |
| Leak impact | Full SA access until revoked | Zero — token can't be exfiltrated |

### 15.4. Branching rules

- `master` → `sct-prod`.
- `develop` (if we adopt) → `sct-staging`.
- Feature branches → `sct-dev` via manual `workflow_dispatch` only.

Enforce at the `on:` trigger, not in job logic.

---

## 16. $300 credits activation

### 16.1. Eligibility (strict)

From Google's Free Trial FAQs:

> You're eligible when **both** are true: (a) you've never been a paying
> user of Google Cloud, Google Maps Platform, or Firebase; and (b) you
> haven't previously signed up for the Free Trial.

**Implications for us:**
- `sct-dev` is already on a *paid* billing account → that account is **not eligible**.
- To claim $300, we need a **new Google account** or a new billing account tied to a Google account that has never touched GCP. Easiest path: a new personal Google account.
- Don't attempt to reuse `akashbhargava1992@gmail.com` if that has ever touched paid GCP — it won't fly Google's eligibility check.

### 16.2. Activation path

1. Open an incognito browser.
2. Create / sign in to a fresh Google account.
3. Go to https://cloud.google.com/free → Start free.
4. Enter a credit card (required, not charged during trial).
5. Accept terms → billing account auto-created with $300 / 90 days.
6. Create project `sct-prod` under this new billing account.

### 16.3. Credit coverage

The $300 credit covers **any Google Cloud service** usage, including:
- Cloud Run (vCPU, memory, requests)
- Firestore (reads, writes, storage)
- Vertex AI (Gemini API calls via Vertex)
- Secret Manager
- Artifact Registry
- Cloud Logging / Monitoring / Trace (above free tier)
- Cloud Build minutes

It does **not** cover:
- AI Studio (Google AI) API calls — that bills separately to the AI key's account, **unless** you link AI Studio to the Google Cloud project, in which case it flows through the same billing. (Verify on activation.)
- Any third-party Marketplace SaaS charges.

### 16.4. Credit balance verification

```bash
# Doesn't have a clean CLI; use the UI:
# Cloud Console → Billing → (select billing account) → Credits
```

### 16.5. 90-day burn plan

Assume demo window is Tier 1 release 2026-04-24, 48h demo window after.

| Week | Expected spend | Dominant service |
|---|---|---|
| Week 1 (through demo) | ~$30 | Cloud Run (min-instances=1 for 48h = ~$8), Gemini calls (~$15), misc $7 |
| Week 2-4 | ~$5/week | Scale-to-zero idle, occasional dev |
| Week 5-12 (Tier 2 work) | ~$10/week | Port intel agent dev, occasional Vertex experimentation |
| **Total** | ~$110 | Out of $300 → healthy buffer |

If any week goes >$50 unexpectedly, the $10 / $25 / $50 budget alerts
(§12) will fire.

### 16.6. "Upgrade to paid" trap

After 90 days, the billing account auto-closes unless upgraded. The
"Upgrade" button converts to a normal paid billing account and *keeps*
any unused credit. Do **not** upgrade mid-hackathon — wait until the
credit is near-depleted.

---

## 17. Pre-demo checklist (24h before)

Execute these 20 items the day before the demo. Each is <5 min. Check
boxes in the session note for the day.

- [ ] Rotate `sct-gemini-api-key` (add new version, keep old enabled).
- [ ] Rotate `sct-groq-api-key`.
- [ ] Redeploy `sct-api` to `sct-prod` (picks up :latest secrets).
- [ ] `gcloud run services update sct-api --min-instances=1 --region=asia-south1 --project=sct-prod`.
- [ ] Confirm `--cpu-boost` is on: `gcloud run services describe ... --format='value(spec.template.metadata.annotations)'` → look for `run.googleapis.com/startup-cpu-boost: "true"`.
- [ ] Budget alerts exist and have the correct email channel (Cloud Console → Billing → Budgets).
- [ ] Trace pipeline working: send 1 synthetic request, verify a trace appears in Cloud Console → Trace within 60s.
- [ ] Log pipeline working: Cloud Logging shows `severity`, `logging.googleapis.com/trace`, `jsonPayload.event` on the synthetic request.
- [ ] Health endpoint: `curl -sf https://sct-prod.web.app/api/health` returns 200.
- [ ] Firebase Hosting rewrite working: `curl -I https://sct-prod.web.app/api/health` shows `server: Google Frontend` (the rewrite is transparent).
- [ ] CORS allowlist has the demo origin (`https://sct-prod.web.app`), no wildcards.
- [ ] Firestore indexes deployed: `firebase deploy --only firestore:indexes --project=sct-prod`.
- [ ] Seed data present: `gcloud firestore export` or a simple read-count sanity check.
- [ ] Quota ceiling checked: Vertex AI → Quotas → Gemini 2.5 Flash RPM/TPM within limits.
- [ ] `gcloud run revisions list --service=sct-api` — previous revision still present for rollback.
- [ ] Rollback command saved in a note: `gcloud run services update-traffic sct-api --to-revisions=<PREV_REV>=100 --region=asia-south1 --project=sct-prod`.
- [ ] Monitoring dashboard URLs saved and tested (Agent cost, SLO, Firestore).
- [ ] `.env` on local machine matches what's deployed — no drift that would confuse demo-time debugging.
- [ ] Gitleaks + detect-secrets: `uv run pre-commit run --all-files` clean.
- [ ] Demo script walkthrough dry-run against prod once, end-to-end.

---

## 18. Rollback playbook

### 18.1. Revision listing

Every deploy creates a new revision. List them:

```bash
gcloud run revisions list \
  --service=sct-api --region=asia-south1 --project=sct-prod \
  --format='table(metadata.name,status.conditions.status.list():label=ACTIVE,metadata.creationTimestamp.date())'
```

### 18.2. Traffic shift

```bash
# Shift 100% of traffic back to a known-good revision
gcloud run services update-traffic sct-api \
  --to-revisions=sct-api-00042-abc=100 \
  --region=asia-south1 --project=sct-prod
```

No rebuild, no redeploy — the revision container image is already in
Artifact Registry and its env + secret bindings are preserved.

### 18.3. Gradual rollout (canary)

```bash
gcloud run services update-traffic sct-api \
  --to-revisions=sct-api-00043-def=10,sct-api-00042-abc=90 \
  --region=asia-south1 --project=sct-prod
```

10% to the new revision, 90% to the old. Watch logs for 5 min. If clean,
shift to 100.

### 18.4. Revision tagging

For predictable rollback, tag each release:

```bash
gcloud run services update-traffic sct-api \
  --set-tags=stable=sct-api-00042-abc,canary=sct-api-00043-def \
  --region=asia-south1 --project=sct-prod
```

Then traffic shifts reference tags instead of revision names:

```bash
gcloud run services update-traffic sct-api \
  --to-tags=stable=100 --region=...
```

### 18.5. What *not* to roll back

- **Firestore data writes** during the bad revision — not reversible by a
  Cloud Run rollback. If the new revision corrupted data, restore from a
  Firestore export. Plan a nightly export *before* the demo:
  ```bash
  gcloud firestore export gs://sct-prod-firestore-backup/$(date +%F) \
    --project=sct-prod
  ```
- **Secret Manager versions** — disabling a version does not undo any
  access that already happened. Rotate instead.

---

## 19. Cost model for the demo window

**Window:** 2026-04-24 release + 48h demo + 100 concurrent judge runs = ~200 total invocations.

### 19.1. Cloud Run

| Component | Formula | Cost |
|---|---|---|
| vCPU-seconds | 1 vCPU × 200 req × 2s avg = 400 vCPU-sec. Tier 1 price $0.000024/vCPU-sec → **$0.0096** | <$0.01 |
| GiB-seconds | 1 GiB × 400 = 400 GiB-sec. $0.0000025/GiB-sec → **$0.001** | <$0.01 |
| Requests | 200 × $0.0000004 → **$0.00008** | <$0.01 |
| **Min-instance carry (48h)** | 1 vCPU × 172,800s × $0.000024 = **$4.15** | **$4.15** |
| **Min-instance memory carry (48h)** | 1 GiB × 172,800s × $0.0000025 = **$0.43** | **$0.43** |
| **Cloud Run total** | — | **~$4.60** |

Note: `asia-south1` may be Tier 2 pricing (~30% higher). Round up to **$6**.

### 19.2. Firestore

- 200 invocations × ~10 reads each = 2000 reads. Free tier: 50K/day. **$0**.
- ~2 writes per invocation = 400 writes. Free tier 20K/day. **$0**.

### 19.3. Gemini (via AI Studio or Vertex)

- Per invocation: ~2000 input tokens, ~500 output tokens, 3 agents → 6000 in, 1500 out per invocation.
- 200 invocations → 1.2M in, 300K out.
- Gemini 2.5 Flash: ~$0.075/1M in, $0.30/1M out → **$0.09 + $0.09 = $0.18**.

Bumping to include Coordinator + iterative agent reasoning, round to **$2**.

### 19.4. Secret Manager

- Access operations: 200 revision starts × 2 secrets = 400 operations.
- Free tier: 10K operations/month. **$0**.

### 19.5. Cloud Trace + Logging

- Trace: 200 × ~20 spans = 4000 spans. Free tier: 2.5M spans/month. **$0**.
- Logging: 200 × ~5KB = 1 MB. Free tier: 50 GB/month. **$0**.

### 19.6. Artifact Registry

- Image size ~250 MB. 5 deploys during demo prep = 1.25 GB stored.
- Price: $0.10/GB/month. ~$0.12/month → **$0.01** prorated to demo window.

### 19.7. Total

**~$8 for the whole demo window.** That's 2.7% of the $300 credit. The
budget alerts ($10 / $25 / $50) are intentionally generous safety nets,
not expected consumption points.

---

## 20. What we explicitly are NOT doing (Tier 1)

| Deferred | Reason | Revisit |
|---|---|---|
| GKE | Cloud Run is serverless; we don't need cluster management. | Never, unless GPU. |
| Cloud Spanner | Firestore scales more than enough for a 3PL app. | Tier 4+ if multi-region writes needed. |
| BigQuery | No analytics workload in Tier 1. | Tier 3 if dashboarding beyond Monitoring. |
| Pub/Sub | No async fan-out yet. Agents run inline. | Tier 2 if multi-module coordination gets queue-backed. |
| Vertex AI Pipelines | No training or batch inference. | Never for this app. |
| Dataflow | No streaming ETL. | Never. |
| Cloud Functions | Cloud Run supersedes; no reason to split. | Never. |
| Cloud SQL | Firestore is the chosen store; no relational needs. | Tier 4+ if reporting demands joins. |
| Agent Engine | Cloud Run + ADK is enough; Agent Engine adds complexity. | Tier 2+ if session state becomes heavy. |
| VPC + Memorystore Redis | `slowapi` is in-memory (stub Tier 1); distributed rate-limit not needed yet. | Tier 2 when real rate limits land. |
| Cloud Armor | Firebase Hosting + Cloud Run already HTTPS; DDoS threat is low pre-launch. | Tier 3 with React frontend. |
| Load Balancer (HTTPS LB) | Cloud Run direct URL is sufficient; no LB until Cloud Armor or multi-backend. | Tier 3. |
| IAP (Identity-Aware Proxy) | Firebase Auth handles identity in-app. IAP duplicates. | Never for user traffic; maybe for admin-only routes Tier 3. |

The meta-rule: **no service gets enabled in a GCP project unless we can
name the failure mode it prevents.** Audit Logs, Trace, Logging clear
that bar. Everything in this "not doing" table doesn't, yet.

---

## 21. Concrete next-session task list (file-by-file)

When the next session opens, execute in this order:

### 21.1. Settings + config

1. `src/supply_chain_triage/core/config.py`
   - No changes required for Workload Identity — `get_secret` already
     lazy-imports Secret Manager. Verify with a unit test.
   - Add fields if needed: `environment: Literal["dev", "staging", "prod"]`, `git_sha: str | None = None` (for trace resource attributes).
2. `.env.template`
   - Add: `ENV=`, `LOG_TO_FILES=`, `VERTEX_LOCATION=` (optional if flipping).

### 21.2. Observability module (new)

3. `src/supply_chain_triage/utils/observability.py`
   - Implement `init_tracing(project_id)` + `shutdown_tracing(provider)` per §11.1.
4. `src/supply_chain_triage/utils/logging.py`
   - Add `_add_trace_context` + `_map_severity` processors per §11.2-11.3.
5. `pyproject.toml`
   - Add OpenTelemetry deps from §11.1.
   - Re-run `uv lock`.

### 21.3. FastAPI app factory

6. `src/supply_chain_triage/runners/app.py` (or wherever `create_app` lives)
   - Wire the `lifespan` per §9.3 skeleton.
   - Register SIGTERM handler.

### 21.4. Deployment artifacts

7. `Dockerfile`
   - Replace with §9.1 full version (adds `tini`, `ca-certificates`, uvloop).
8. `.dockerignore`
   - Replace with §9.2 full version.
9. `firebase.json`
   - Create with §10.3 content.

### 21.5. Scripts

10. `scripts/gcp_bootstrap.sh` (new)
    - Automate §4 SA creation + IAM bindings + §13.1 API allowlist + §15.1 WIF setup, idempotently.
11. `scripts/deploy.sh` (new)
    - The `gcloud run deploy ...` invocation from §8.3 with variable defaults.

### 21.6. CI/CD

12. `.github/workflows/deploy-prod.yml` (new)
    - §15.2 content. Replace `<PROJECT_NUMBER>` after running §15.1.
13. `.github/workflows/ci.yml` (existing)
    - Confirm `uv sync --locked` + ruff + mypy + pytest runs. No changes expected.

### 21.7. Docs / sessions

14. `docs/sessions/YYYY-MM-DD-gcp-bootstrap.md` — capture decisions +
    the output of bootstrap scripts + any open questions.

### 21.8. Verification

15. Manual smoke:
    ```bash
    ./scripts/gcp_bootstrap.sh sct-dev
    ./scripts/deploy.sh sct-dev
    curl -sf "$(gcloud run services describe sct-api --region=asia-south1 --project=sct-dev --format='value(status.url)')/health"
    ```
16. Pre-demo checklist (§17) dry-run against `sct-dev`.

---

## 22. Sources + date-stamped links

All accessed 2026-04-18.

### Cloud Run identity + deploy

- [Configure service identity for services — Cloud Run docs](https://docs.cloud.google.com/run/docs/configuring/services/service-identity) — April 2026 canonical doc for `--service-account`.
- [Introduction to service identity — Cloud Run docs](https://docs.cloud.google.com/run/docs/securing/service-identity) — why dedicated SA over default.
- [Integrate Cloud Run and Workload Identity Federation — IAM docs](https://cloud.google.com/iam/docs/tutorial-cloud-run-workload-id-federation) — end-to-end WIF tutorial.
- [Deploying container images to Cloud Run](https://docs.cloud.google.com/run/docs/deploying) — `gcloud run deploy` flags reference.
- [Deploying to Cloud Run — Artifact Registry docs](https://docs.cloud.google.com/artifact-registry/docs/integrate-cloud-run) — image push + deploy pattern.

### Secret Manager

- [Configure secrets for services — Cloud Run docs](https://docs.cloud.google.com/run/docs/configuring/services/secrets) — `--set-secrets` format, `:latest` behavior.
- [About rotation schedules — Secret Manager docs](https://docs.cloud.google.com/secret-manager/docs/rotation-recommendations) — rotation best practices.
- [Secret rotation via revision rollout — Cloud Run Medium](https://medium.com/google-cloud/cloud-run-hot-reload-your-secret-manager-secrets-ff2c502df666) — Guillaume Blaquière on hot-reload patterns.
- [Access control with IAM — Secret Manager docs](https://docs.cloud.google.com/secret-manager/docs/access-control) — `secretAccessor` per-secret vs per-project.
- [Implement Least Privilege Access for Secret Manager — Trend Micro](https://www.trendmicro.com/cloudoneconformity/knowledge-base/gcp/SecretManager/check-for-administrative-permissions.html) — enumeration of least-privilege roles.

### Vertex AI + regional availability

- [Gemini 2.5 Flash — Vertex AI docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/models/gemini/2-5-flash) — model + region table.
- [Deployments and endpoints — Vertex AI docs](https://cloud.google.com/vertex-ai/generative-ai/docs/learn/locations) — `asia-south1` support matrix.
- [Is there any model available in asia-south1? — Google AI Developers Forum](https://discuss.ai.google.dev/t/is-there-any-model-available-or-planned-in-the-asia-south1-region-on-vertex-ai-that-is-more-capable-than-gemini-2-5-flash/128791) — confirms 2.5 Flash in Mumbai as of March 2026.
- [Gemini 2.5 Vertex AI retirement — GCP Study Hub](https://gcpstudyhub.com/blog/google-is-retiring-gemini-2-5-on-vertex-ai-what-you-need-to-know-and-do-before-october-2026) — Oct 2026 EoL notice.

### Observability

- [opentelemetry-exporter-gcp-trace — PyPI](https://pypi.org/project/opentelemetry-exporter-gcp-trace/) — package page with install instructions.
- [Cloud Trace Exporter Example — google-cloud-opentelemetry docs](https://google-cloud-opentelemetry.readthedocs.io/en/latest/examples/cloud_trace_exporter/README.html) — Python exporter reference.
- [Deploy Google-Built OpenTelemetry Collector on Cloud Run](https://docs.cloud.google.com/stackdriver/docs/instrumentation/opentelemetry-collector-cloud-run) — collector pattern for heavier setups.
- [OTel GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/) — `gen_ai.usage.*` attribute names.

### Billing + budgets

- [Create, edit, or delete budgets and budget alerts — Cloud Billing docs](https://docs.cloud.google.com/billing/docs/how-to/budgets) — `gcloud billing budgets create` syntax.
- [Customize budget alert email recipients](https://docs.cloud.google.com/billing/docs/how-to/budgets-notification-recipients) — Monitoring channel setup.
- [Get started with the Cloud Billing Budget API](https://docs.cloud.google.com/billing/docs/how-to/budget-api-overview) — programmatic budgets.

### GitHub Actions WIF

- [google-github-actions/auth](https://github.com/google-github-actions/auth) — action repo + WIF inputs.
- [google-github-actions/deploy-cloudrun](https://github.com/google-github-actions/deploy-cloudrun) — deploy action inputs.
- [Enabling keyless authentication from GitHub Actions — Cloud Blog](https://cloud.google.com/blog/products/identity-security/enabling-keyless-authentication-from-github-actions) — WIF rationale + setup.
- [Configure Workload Identity Federation with deployment pipelines — IAM docs](https://docs.cloud.google.com/iam/docs/workload-identity-federation-with-deployment-pipelines) — canonical reference.

### $300 credits

- [Google Cloud Free Trial FAQs](https://cloud.google.com/signup-faqs) — eligibility rules.
- [Free Google Cloud features and trial offer](https://docs.cloud.google.com/free/docs/free-cloud-features) — what's covered.
- [Billing during the free trial — Cloud Console Help](https://support.google.com/cloud/answer/7006543?hl=en) — upgrade path details.

### Firebase Hosting

- [Firebase Hosting for Cloud Run — Firebase Blog](https://firebase.blog/posts/2019/04/firebase-hosting-and-cloud-run/) — original integration post (still accurate).
- [Firebase Hosting Rewrites to Cloud Run — OneUptime 2026 guide](https://oneuptime.com/blog/post/2026-02-17-how-to-use-firebase-hosting-rewrites-to-route-traffic-to-cloud-run-services/view) — Feb 2026 walkthrough.

### Cold start + performance

- [Faster cold starts with startup CPU Boost — Cloud Blog](https://cloud.google.com/blog/products/serverless/announcing-startup-cpu-boost-for-cloud-run--cloud-functions) — `--cpu-boost` rationale.
- [Configure CPU limits for services — Cloud Run docs](https://docs.cloud.google.com/run/docs/configuring/services/cpu) — CPU allocation + always-on modes.
- [Cloud Run Scaling Explained — CloudWebSchool](https://cloudwebschool.com/docs/gcp/compute/cloud-run-scaling-behaviour/) — min/max instances + concurrency interaction.
- [Advanced Performance Tuning for FastAPI on Cloud Run](https://davidmuraya.com/blog/fastapi-performance-tuning-on-google-cloud-run/) — practical uvicorn+asgi tuning.

### Pricing

- [Cloud Run pricing](https://cloud.google.com/run/pricing) — current vCPU/GiB/req rates.

### Repo rules and prior decisions (internal)

- `.claude/rules/deployment.md` — Cloud Run Dockerfile + `--set-secrets` pattern.
- `.claude/rules/security.md` §5, §6, §11 — security headers, secret discipline, CORS.
- `.claude/rules/observability.md` §2-§7 — OTel spans, SIGTERM, cost attribution.
- `.claude/rules/logging.md` §4, §6 — structlog chain, request-id propagation.
- `.claude/rules/architecture-layers.md` §2 narrow exception — `utils/logging.py` + observability external deps.
- `docs/security/threat-model.md` — STRIDE, Sprint 5 deploy-time secret-leakage mitigation.
- `docs/research/adk-best-practices.md` — ADK lazy-init + runner shim.

---

**End of document.** If a section here gets out of date, update *this*
file and link the update from `docs/sessions/YYYY-MM-DD-*.md`. Rules
files change via ADR; research files change via session notes.
