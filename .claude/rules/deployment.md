---
description: Cloud Run deployment — Dockerfile, secrets, environment separation, A2A scaffolding
paths: [".github/workflows/**", "Dockerfile", "infra/**", ".env.template"]
---

# Deployment rules

Cloud Run for Tier 1. Agent Engine only if Tier 2+ session state / long-running reasoning becomes load-bearing. Not GKE.

> **Verification note:** The agent-starter-pack CLI flags, Cloud Run secret-mount syntax, and Agent Engine availability should be re-verified against live Google Cloud docs before the first production deploy. Snippets below reflect the uv Docker guide (verified) and stable Cloud Run patterns.

## 1. Multi-stage uv Dockerfile

```dockerfile
# syntax=docker/dockerfile:1.7
FROM python:3.13-slim AS builder
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-install-project --no-dev
COPY src/ ./src/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

FROM python:3.13-slim
RUN useradd -m -u 1000 runner
COPY --from=builder --chown=runner:runner /app/.venv /app/.venv
COPY --from=builder --chown=runner:runner /app/src /app/src
WORKDIR /app
ENV PATH="/app/.venv/bin:$PATH" \
    PORT=8080 \
    PYTHONUNBUFFERED=1
USER runner
EXPOSE 8080
CMD ["uvicorn", "supply_chain_triage.runners.app:app", "--host", "0.0.0.0", "--port", "8080"]
```

**Dockerignore:** `.venv/`, `tests/`, `evals/`, `docs/`, `.git/`, `.github/`, `.claude/`, `*.md`, `.env*`, `__pycache__/`.

## 2. Runtime choice

| Target | When |
|---|---|
| Cloud Run | Tier 1 default — scale-to-zero, pay-per-request, simple FastAPI + ADK |
| Agent Engine | Tier 2+ if managed session / memory becomes load-bearing |
| GKE | Only if sidecars, GPUs, custom networking — not for this project |

## 3. Secrets

- **Workload Identity** on the Cloud Run service account (grant Firebase Admin role) — not a baked JSON key.
- Secret Manager values mounted as env vars: `--set-secrets GEMINI_API_KEY=gemini-key:latest`.
- `.env.template` holds **names only**. `.env` is gitignored.
- Read Secret Manager values in the FastAPI `lifespan` startup, not at module import (cold-start latency).

Never:
- `COPY serviceAccountKey.json` in a Dockerfile layer.
- `GOOGLE_APPLICATION_CREDENTIALS` pointing at a baked file.
- Commit `*.json` service-account keys.

## 4. Environment separation

Three GCP projects: `sct-dev`, `sct-staging`, `sct-prod`. Same container image, different `--set-env-vars ENV=X` and different Firestore databases and Firebase projects.

Pydantic settings in `core/settings.py` loads via env:
```python
class Settings(BaseSettings):
    env: Literal["dev", "staging", "prod"]
    gcp_project: str
    gemini_api_key: SecretStr
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
```

## 5. Deploy gate

- Prod + staging: Terraform only, no `gcloud run deploy` from laptops.
- Dev: `gcloud run deploy` is fine for iteration.

## 6. A2A scaffolding (Tier 3)

When an A2A surface is needed:
```
uvx agent-starter-pack create sct-a2a --agent adk_a2a
```
**Keep:** Terraform, Dockerfile skeleton, A2A wiring (`A2aAgentExecutor`, `AgentCardBuilder`, `agent.json`, `A2AFastAPIApplication` mount), CI/CD glue, load-test skeleton.

**Customize:** FastAPI app factory to match `src/supply_chain_triage/runners/`, module layout, auth middleware.

**Never hand-write** A2A artifacts — see `.claude/rules/agents.md` §11.

## 7. `.env.template`

Names-only. Example:
```
ENV=dev
GCP_PROJECT=sct-dev
GEMINI_API_KEY=
FIREBASE_PROJECT_ID=
FIRESTORE_EMULATOR_HOST=
FIREBASE_AUTH_EMULATOR_HOST=
LOG_LEVEL=INFO
```

Values never committed.

## 8. Cold start

- Scale-to-zero for dev/staging.
- Min-instances=1 for the demo-day prod deploy (avoids user-visible cold starts).
- Keep the image small (see §1 dockerignore).
- Lazy-import heavy modules (`google.cloud.firestore`, Gemini client) inside `lifespan`, not at module top level.

## 9. Retries + circuit breakers

- Gemini 429: exponential backoff with jitter, max 3 retries, then classify as `status: retry` and stop. Use `tenacity`.
- Firestore quota exceeded: same, plus circuit breaker (open 30s after N failures). Lives in `modules/*/memory/`, not in agents.
- **Never** unbounded retry loops — they multiply cost during incidents.
