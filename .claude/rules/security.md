---
description: Firebase Auth + Cloud Run security — what still applies from generic JWT/password rules, and the Firebase-specific additions
paths: ["src/supply_chain_triage/middleware/**", "src/supply_chain_triage/core/settings.py", "src/supply_chain_triage/runners/**"]
---

# Security rules

Firebase Auth handles password hashing, JWT signing/verification, expiry checks, and revocation server-side. This rule file is a short list of what still applies to us plus the Firebase-specific + Cloud Run-specific additions.

## 1. What Firebase owns (never re-implement)

| Concern | Handled by |
|---|---|
| Password hashing | Firebase (modified Scrypt) — never hash in our code |
| JWT signing + verification | `auth.verify_id_token(token)` — never craft tokens |
| `exp` claim validation + clock skew | Firebase Admin SDK (raises `ExpiredIdTokenError`) |
| Token revocation | `auth.revoke_refresh_tokens(uid)` + `check_revoked=True` on **privileged routes only** (adds an RPC per call) |
| Email / password sign-in UI flow | Firebase client SDK |

Enforced: `bcrypt` and `passlib` are banned project-wide via ruff `TID251.banned-api`. Writing custom password hashing is forbidden.

## 2. What still applies from generic rules

### Timing-safe comparisons for server-owned secrets

```python
import hmac
if not hmac.compare_digest(provided_key, settings.GEMINI_ADMIN_KEY):
    raise HTTPException(401, "Unauthorized")
```

Use `hmac.compare_digest` for:
- Admin-only API keys
- Webhook signature verification (carrier callbacks, etc.)
- Any server-owned secret compared against a client-provided value

**Never** `==` for secret comparison.

### Email-enumeration protection

Wrap Firebase's `generate_password_reset_link` server-side; ignore `UserNotFoundError`:

```python
@router.post("/auth/reset", status_code=202)
async def reset(req: ResetReq):
    try:
        firebase_auth.generate_password_reset_link(req.email)
        # send link via SendGrid / SES
    except firebase_auth.UserNotFoundError:
        pass
    return {"status": "if_account_exists_email_sent"}
```

Also enable "Email enumeration protection" in the Firebase Console (GA 2023). Defence-in-depth.

### Non-default secret enforcement

Pydantic-settings validator rejects empty / placeholder values for required secrets outside dev:

```python
from pydantic_settings import BaseSettings
from pydantic import field_validator

class Settings(BaseSettings):
    ENV: Literal["dev", "staging", "prod"]
    GEMINI_API_KEY: str
    FIREBASE_PROJECT_ID: str

    @field_validator("GEMINI_API_KEY")
    @classmethod
    def _no_placeholder(cls, v: str, info) -> str:
        if info.data.get("ENV") != "dev" and v in {"", "changeme", "test", "changethis"}:
            raise ValueError("GEMINI_API_KEY must be set in non-dev environments")
        return v
```

Same pattern for any secret that must not be placeholder in staging/prod.

## 3. Custom claims + role hierarchy

Keep claims **flat + small** (<1000 bytes). Ordered integer tiers compared numerically — not string-set hierarchies.

```python
# Set once via admin script — see scripts/set_custom_claims.py
firebase_auth.set_custom_user_claims(uid, {"tier": 2, "tenant_id": "acme"})
```

Dependency factory:

```python
def require_tier(min_tier: int):
    async def _dep(user: FirebaseUser = Depends(get_current_user)) -> FirebaseUser:
        if user.tier < min_tier:
            raise HTTPException(403, "insufficient_role")
        return user
    return _dep
```

### Propagation delay (~1 hour)

Client-side token refresh can lag up to 1 hour after claim changes. For privilege-critical endpoints, **re-fetch via Admin SDK** instead of trusting the decoded token claim:

```python
async def current_claims(uid: str) -> dict:
    # cache 60s in-memory to avoid per-request RPC
    if cached := _claims_cache.get(uid):
        return cached
    user_record = firebase_auth.get_user(uid)
    _claims_cache[uid] = user_record.custom_claims or {}
    return _claims_cache[uid]
```

## 4. Rate limiting

`slowapi` with a **distributed backend** — in-memory breaks on Cloud Run scale-to-zero and multi-instance.

```python
from slowapi import Limiter

limiter = Limiter(
    key_func=lambda r: getattr(r.state, "user_uid", None) or get_remote_address(r),
    storage_uri="redis://10.x.x.x:6379",       # Memorystore
)
```

**Recommended limits:**
- Auth-like endpoints (password reset, token issue): **5/min/IP**
- Agent invocation (Gemini cost): **20/min/uid + 200/day/uid**
- Public health / version: **60/min/IP**

**Cloud Armor** sits before Cloud Run behind a Load Balancer — L7 DDoS protection, IP/geo blocking, OWASP preset. Use Armor for coarse volumetric + geo / WAF; `slowapi` for per-user business-logic limits.

## 5. Security headers middleware

```python
from starlette.middleware.base import BaseHTTPMiddleware

class SecurityHeaders(BaseHTTPMiddleware):
    async def dispatch(self, req, call_next):
        r = await call_next(req)
        r.headers["X-Content-Type-Options"] = "nosniff"
        r.headers["X-Frame-Options"] = "DENY"
        r.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        r.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains; preload"
        r.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "connect-src 'self' https://*.googleapis.com https://firestore.googleapis.com "
            "https://identitytoolkit.googleapis.com https://securetoken.googleapis.com; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline'; "    # Tier 3 React: switch to nonces
            "frame-ancestors 'none'"
        )
        return r
```

**STS** only in prod — breaks local HTTP testing otherwise.

**SSE + CSP gotcha:** ADK streams responses via `text/event-stream`. CSP doesn't block SSE itself, but `connect-src` must list the API origin. When Tier 3 React lands, swap `style-src 'unsafe-inline'` to nonce-based CSP.

Prefer hand-rolled middleware over the `secure.py` lib (last release 2023; thin wrapper).

## 6. Secret reading discipline

Read Secret Manager values at **FastAPI `lifespan` startup**. Never at module import, never per-request.

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    sm = secretmanager.SecretManagerServiceClient()
    app.state.gemini_key = sm.access_secret_version(
        name="projects/<PID>/secrets/gemini-key/versions/latest"
    ).payload.data.decode()
    try:
        yield
    finally:
        pass
```

**Discipline:**
- No `SECRET = os.environ[...]` at module scope. Always via `Settings` (pydantic-settings) or `app.state`.
- Use `:latest` version in Cloud Run. Rotate via revision rollout (new container reads latest), then disable the old version after drain.
- Never pin `:1` — atomic cutover via revision rollout only works with `:latest`.

Firebase service account keys: **Workload Identity only**. If a JSON key is unavoidable, mount as a secret file — never `COPY` into the image. Rotate every 30 days via `iam.serviceAccountKeys.create/delete`.

## 7. PII-safe structured logging

```python
import structlog

def _drop_pii(_, __, event_dict):
    for k in ("prompt", "response", "document", "email", "phone"):
        event_dict.pop(k, None)
    return event_dict

structlog.configure(processors=[
    structlog.contextvars.merge_contextvars,
    _drop_pii,
    structlog.processors.JSONRenderer(),
])

log = structlog.get_logger()
log.info("agent_invoked", request_id=rid, uid=uid, agent="classifier",
         exception_id=eid, latency_ms=ms)    # OK
# log.info("agent_response", response=...)   # DROPPED by processor
```

**Loggable:** `request_id`, `uid`, `agent_name`, `exception_id` (ULID), `latency_ms`, `status`.
**Not loggable:** raw Gemini prompts, Gemini output, Firestore doc contents, emails, phone numbers, free-text user input.

The drop processor is the **defence-in-depth** backstop — developers should also not pass banned keys in the first place.

## 8. Authorization patterns

### Any authenticated user

```python
@router.get("/exceptions/me", response_model=Page[ExceptionPublic])
async def list_mine(db: FirestoreDep, current_user: CurrentUser) -> Any: ...
```

### Tier-gated

```python
@router.delete("/exceptions/{id}", dependencies=[Depends(require_tier(2))])
async def delete_exception(...) -> Message: ...
```

### Owner-scoped (tenant or user)

```python
doc = await db.collection("exceptions").document(exception_id).get()
if not doc.exists:
    raise HTTPException(404, "Exception not found")
data = doc.to_dict()
if data["tenant_id"] != current_user.tenant_id:
    raise HTTPException(403, "Not enough permissions")
```

Always **existence (404) before permission (403)** — consistent with `.claude/rules/api-routes.md` §8.

## 9. Anti-patterns

### Firebase + Cloud Run

- `check_revoked=True` on every request — expensive. Reserve for privileged routes.
- `FIREBASE_AUTH_EMULATOR_HOST` in Cloud Run env — Firebase Admin SDK honors it unconditionally and will accept forged tokens. Pydantic-settings validator rejects when `ENV != "dev"`.
- Service account JSON baked into the image — Workload Identity only.
- Trusting `uid` from request body / header — always `verify_id_token`. Never read `uid` from untrusted input.
- Custom password hashing alongside Firebase — `bcrypt` / `passlib` banned via ruff `TID251`.
- `check_revoked=True` skipped on admin / privilege-elevation routes — use it there.

### Secrets

- Hard-coding API keys, passwords, tokens in source — always through `Settings`.
- Logging secrets, JWTs, full Gemini prompts/responses, even at DEBUG.
- Returning secrets in error responses.
- Committing `.env` with real values (gitleaks/detect-secrets catches).

### Authentication

- Skipping `verify_id_token` — never trust client-provided claims.
- Storing user profile data in the ID token as source of truth — fetch from Firestore or `auth.get_user` when needed.
- Returning different error messages for "user not found" vs "wrong password" — Firebase sign-in flow is client-side, but any server-side signup or password-reset flow must not differentiate.

### Authorization

- Client-side role checks as the only gate.
- Exposing internal IDs / database shapes in error messages.
- Allowing self-deletion of admin/superuser accounts.

### Data handling

- String-concatenating into Firestore queries (even though there's no injection surface like SQL, the `where()` / `order_by()` chain still benefits from typed inputs).
- Returning the raw user record on public endpoints — use `UserPublic` variants that exclude claims, tier, tokens.
- Accepting file uploads without size + type validation — relevant when any media endpoint is added.
