---
title: Firebase Auth + Google OAuth + Multi-Tenant Custom Claims — Tier 1 Research
status: research
sprint: Tier 1 pre-hackathon
owner: backend
stack:
  runtime: python 3.13
  framework: FastAPI
  auth_backend: Firebase Auth (GCP Identity Platform free tier)
  tenancy: custom-claim on shared Firebase project (single-project model)
  sdk_server: firebase-admin (python)
  sdk_client: firebase-js-sdk v10+ (or REST equivalent)
decision_date: 2026-04-18
supersedes: none
related_rules:
  - .claude/rules/security.md
  - .claude/rules/api-routes.md
  - .claude/rules/firestore.md
  - .claude/rules/testing.md
  - .claude/rules/observability.md
related_research:
  - docs/research/zettel-firestore-multi-tenant.md
  - docs/research/Supply-Chain-Firestore-Schema-Tier1.md
tier: 1
---

# Firebase Auth + Google OAuth + Multi-Tenant Custom Claims

> Research document for the Tier 1 auth decision: **Google OAuth + auto-seed into a demo tenant**. When a hackathon judge clicks "Sign in with Google", we auto-provision a user in the `comp_nimblefreight` tenant, stamp `company_id` as a custom claim via the Admin SDK, and redirect them into the dashboard. No password UI, no tenant picker, no waiting list.

---

## 1. Executive summary

For Tier 1 we use **Firebase Auth with Google OAuth as the sole identity provider**, backed by **custom-claim tenanting** on a single shared Firebase project. A hackathon judge authenticates with their Google account; our backend verifies the ID token with `firebase_admin.auth.verify_id_token`, auto-provisions a user document in Firestore on first sight, and stamps `company_id=comp_nimblefreight` as a Firebase custom claim via the Admin SDK. The frontend then force-refreshes the ID token so the claim propagates, and every subsequent API call carries `Authorization: Bearer <id_token>` — the `FirebaseAuthMiddleware` reads `company_id` from the decoded claims and the Firestore security rules compare it to `resource.data.company_id` for defense-in-depth. This gives us zero-friction judge onboarding, a clean tenancy boundary, emulator-friendly testing, and a path to Tier 2+ multi-tenant self-serve without throwing anything away.

---

## 2. End-to-end auth flow for the judge

The full happy path, step by step. Every step names exactly one responsibility owner so we can tell at a glance which side fails if something breaks.

### 2.1 Sequence

```
 Judge              Browser / Frontend                Firebase Auth (Google)        Our FastAPI (/api/v1)        Firestore (Admin SDK)
   │                       │                                    │                            │                          │
   │ click "Sign in"       │                                    │                            │                          │
   ├──────────────────────►│                                    │                            │                          │
   │                       │ signInWithPopup / Redirect(google) │                            │                          │
   │                       ├───────────────────────────────────►│                            │                          │
   │                       │ OAuth consent → id_token + uid     │                            │                          │
   │                       │◄───────────────────────────────────┤                            │                          │
   │                       │ POST /auth/onboard                 │                            │                          │
   │                       │   Authorization: Bearer <id_token> │                            │                          │
   │                       ├───────────────────────────────────────────────────────────────►│                          │
   │                       │                                    │ verify_id_token(id_token)  │                          │
   │                       │                                    │◄───────────────────────────┤                          │
   │                       │                                    │                            │ users/{uid}.get()        │
   │                       │                                    │                            ├─────────────────────────►│
   │                       │                                    │                            │ (not found — first visit)│
   │                       │                                    │                            │◄─────────────────────────┤
   │                       │                                    │                            │ users/{uid}.set({...})   │
   │                       │                                    │                            ├─────────────────────────►│
   │                       │                                    │                            │ set_custom_user_claims() │
   │                       │                                    │                            │   company_id=nimble...   │
   │                       │                                    │◄───────────────────────────┤                          │
   │                       │ { requires_token_refresh: true }   │                            │                          │
   │                       │◄───────────────────────────────────────────────────────────────┤                          │
   │                       │ user.getIdToken(forceRefresh=true) │                            │                          │
   │                       ├───────────────────────────────────►│                            │                          │
   │                       │ new id_token carrying company_id   │                            │                          │
   │                       │◄───────────────────────────────────┤                            │                          │
   │                       │ GET /exceptions (authed)           │                            │                          │
   │                       ├───────────────────────────────────────────────────────────────►│                          │
   │                       │                                    │ middleware reads claim     │                          │
   │                       │                                    │ → request.state.company_id │                          │
   │                       │                                    │                            │ query scoped by tenant  │
   │                       │                                    │                            ├─────────────────────────►│
   │                       │ 200 OK                             │                            │◄─────────────────────────┤
   │                       │◄───────────────────────────────────────────────────────────────┤                          │
   │ sees dashboard        │                                    │                            │                          │
```

### 2.2 Narrative steps

1. Judge visits the dashboard URL (e.g. `https://sct-prod.web.app`).
2. Landing page shows a single "Sign in with Google" button and a one-line explainer.
3. Button invokes Firebase client SDK `signInWithPopup(auth, new GoogleAuthProvider())` or `signInWithRedirect` for narrow browsers / mobile Safari. Popup is the Tier 1 default; redirect is the documented fallback.
4. Firebase redirects the user to Google's consent screen; Google returns a signed OIDC ID token plus refresh material.
5. Firebase client SDK stores both in IndexedDB and exposes `auth.currentUser`. The JS SDK has already minted a Firebase-issued ID token (distinct from the raw Google token — Firebase wraps Google identity).
6. Frontend calls `await user.getIdToken()` and POSTs to `/api/v1/auth/onboard` with header `Authorization: Bearer <id_token>`. Body is empty — the middleware extracts everything from the token.
7. Server middleware verifies the token via `firebase_admin.auth.verify_id_token(token)`. Valid → `request.state.user_id`, `request.state.email`. The `company_id` check in middleware is bypassed for this one route (public allowlist — see §4.4).
8. Route handler checks `users/{uid}`. If missing → this is a first-time judge. We create the doc with `company_id=comp_nimblefreight`, `role=coordinator`, `created_at=now`, `last_seen_at=now`, and call `auth.set_custom_user_claims(uid, {"company_id": "comp_nimblefreight", "tier": 1, "role": "coordinator"})`.
9. Response body: `{"user_id": uid, "company_id": "comp_nimblefreight", "requires_token_refresh": true}`.
10. Frontend immediately calls `await user.getIdToken(/* forceRefresh */ true)`. This is the **critical step** — custom claims are baked into the ID token at mint time, so until the next refresh the claim is not visible to the server.
11. Frontend caches the refreshed token in memory (never localStorage — XSS exposure) and starts hitting authenticated endpoints.
12. Every subsequent request goes through `FirebaseAuthMiddleware`, which rejects on missing `company_id` claim. With the refreshed token, `company_id=comp_nimblefreight` is present and the request proceeds.

### 2.3 Failure branches

| Failure | Where it surfaces | HTTP | User sees |
|---|---|---|---|
| Google OAuth cancelled | Client SDK throws | — | Stay on landing, no error banner |
| `verify_id_token` fails — expired | Middleware | 401 `token_expired` | Prompt to re-login |
| `verify_id_token` fails — invalid sig | Middleware | 401 `invalid_signature` | Generic "please sign in again" |
| Auto-provision succeeded, token not refreshed | Middleware `missing_company_claim` | 403 | "Please refresh" — the frontend should catch this and re-force-refresh |
| Firestore `users/{uid}.set` fails | Route handler | 500 | Generic error banner; judge retries |
| `set_custom_user_claims` succeeds but Firestore write failed | Route handler | 500 | Partial state; idempotent retry heals (§4.3) |

---

## 3. Server-side verification middleware

The existing `src/supply_chain_triage/middleware/firebase_auth.py` is already correct for Tier 1. We document what it does, extend it with a small amount for emulator support and public-path handling around `/auth/onboard`, and note what to keep vs what to change.

### 3.1 What `verify_id_token` does under the hood

`firebase_admin.auth.verify_id_token(token)` performs, in order:

1. **JWT header decode** — reads `alg` (must be `RS256`) and `kid`.
2. **Public-key fetch** — pulls the matching cert from `https://www.googleapis.com/robot/v1/metadata/x509/securetoken@system.gserviceaccount.com`. Keys are cached in-process by the Admin SDK with respect for the `Cache-Control` response header (typically ~6 hours). This is why "first request is slow, subsequent is fast" is the expected warm-cache behavior — we do not need a caching layer on top.
3. **Signature verify** against the fetched cert.
4. **Standard claims checks:** `iss == https://securetoken.google.com/<project-id>`, `aud == <project-id>`, `exp > now`, `iat < now + skew`, `auth_time <= now`. Default clock skew tolerance is ~5 minutes.
5. **`sub == uid` sanity check** — raises on mismatch.
6. **Revocation check (opt-in)** — only if `check_revoked=True`. Costs one extra Identity Platform RPC per call.
7. **Returns** the decoded claim dict — contains Firebase standard keys plus any custom claims we've set (`company_id`, `tier`, `role`).

### 3.2 Error taxonomy

| Admin SDK exception | Our response | HTTP | Meaning |
|---|---|---|---|
| `ExpiredIdTokenError` | `{"error": "token_expired"}` | 401 | Client must refresh |
| `RevokedIdTokenError` | `{"error": "token_revoked"}` | 401 | Admin revoked the user; re-auth needed |
| `InvalidIdTokenError` | `{"error": "invalid_signature"}` | 401 | Malformed / not from our project |
| `UserDisabledError` | `{"error": "account_disabled"}` | 401 | Admin disabled the account |
| `CertificateFetchError` | `{"error": "service_unavailable"}` | 503 | Google cert endpoint unreachable — retry |
| Other `Exception` | `{"error": "invalid_token"}` | 401 | Unknown; don't leak internals |

### 3.3 Existing middleware — keep vs extend

The existing `FirebaseAuthMiddleware` in `src/supply_chain_triage/middleware/firebase_auth.py` already:

- Accepts a `public_paths` frozenset to skip auth (health checks, docs).
- Parses `Authorization: Bearer <token>`.
- Calls `firebase_auth.verify_id_token`.
- Handles `ExpiredIdTokenError` / `InvalidIdTokenError`.
- Enforces `company_id` custom claim presence (rejects with 403 otherwise).
- Stamps `request.state.user_id`, `request.state.company_id`, `request.state.email`.

**Keep as-is.** The only extensions needed for the onboarding flow:

1. **Add `/api/v1/auth/onboard` to `public_paths`** at app factory wiring — this route *does* need `verify_id_token` but *does not* need `company_id` (chicken-and-egg). We split verification into two tiers below.
2. **Split verification into two dependencies** in `runners/`: one raw (validates token, no claim check — used by `/auth/onboard`), one tenant-scoped (validates token *and* claim — used by everything else). The middleware stays as the default; the onboarding route opts out of middleware and calls the raw dependency.
3. **`RevokedIdTokenError` branch** — catch separately and map to 401 with `token_revoked` so monitoring distinguishes expiry from revocation.

### 3.4 Revocation check policy

Per `.claude/rules/security.md` §1 and §12:

- **Off** for standard request paths — costs an RPC per call, busts free tier.
- **On** for privileged / admin-style endpoints and any flow that changes a user's tenant or role.
- For the onboarding endpoint specifically: **off**. A brand-new signup has nothing revocable yet.

### 3.5 Token-age sanity cap

ID tokens are signed with `exp = iat + 3600`. Firebase guarantees no longer-lived tokens. We add defense-in-depth: reject any token older than 1 hour from `iat` regardless — this catches replay of a stolen token that somehow survived normal expiry handling.

```python
# addition to FirebaseAuthMiddleware, before accepting the decoded claims
MAX_TOKEN_AGE_SECONDS = 3600
age = time.time() - claims.get("iat", 0)
if age > MAX_TOKEN_AGE_SECONDS:
    return JSONResponse({"error": "token_too_old"}, status_code=401)
```

---

## 4. Auto-provisioning endpoint — `/api/v1/auth/onboard`

### 4.1 Route spec

```python
# runners/routes/auth.py
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from firebase_admin import auth as firebase_auth

from supply_chain_triage.core.config import get_firestore_client
from supply_chain_triage.middleware.audit_log import audit_event

router = APIRouter(prefix="/auth", tags=["auth"])


class OnboardResponse(BaseModel):
    """Response shape for /auth/onboard."""
    user_id: str
    company_id: str
    requires_token_refresh: bool


@router.post("/onboard", response_model=OnboardResponse, status_code=200)
async def onboard(request: Request) -> OnboardResponse:
    """Verify the Firebase ID token and auto-provision a demo-tenant user.

    Idempotent — calling twice returns the same user_id without re-writing
    the Firestore doc or re-setting the custom claim.
    """
    ...  # see §4.2
```

Register in `runners/app.py`, add `/api/v1/auth/onboard` to the `FirebaseAuthMiddleware.public_paths` allowlist.

### 4.2 Handler body

```python
@router.post("/onboard", response_model=OnboardResponse, status_code=200)
async def onboard(request: Request) -> OnboardResponse:
    # 1. Raw token verification (no company_id check)
    auth_header = request.headers.get("authorization", "")
    if not auth_header.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing_credentials")
    token = auth_header.split(" ", 1)[1].strip()

    try:
        claims = firebase_auth.verify_id_token(token)
    except firebase_auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="token_expired")
    except firebase_auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="invalid_token")

    uid = claims["uid"]
    email = claims.get("email", "")
    display_name = claims.get("name", email.split("@")[0] if email else uid)

    db = get_firestore_client()
    user_ref = db.collection("users").document(uid)
    user_doc = await user_ref.get()

    if user_doc.exists:
        # 2. Idempotent path — already provisioned. Touch last_seen_at.
        data = user_doc.to_dict() or {}
        await user_ref.update({"last_seen_at": firestore.SERVER_TIMESTAMP})
        audit_event(
            "auth_login",
            correlation_id=request.state.request_id,
            user_id=uid,
            company_id=data.get("company_id", "system"),
        )
        return OnboardResponse(
            user_id=uid,
            company_id=data["company_id"],
            requires_token_refresh=False,  # claim already on their tokens
        )

    # 3. First-sight provisioning path
    company_id = pick_demo_tenant(email)  # §6
    now = firestore.SERVER_TIMESTAMP

    await user_ref.set({
        "uid": uid,
        "company_id": company_id,
        "email": email,
        "display_name": display_name,
        "role": "coordinator",
        "language_preference": "en",
        "communication_style": "concise",
        "created_at": now,
        "last_seen_at": now,
    })

    # 4. Stamp the claim. Setting twice is idempotent.
    firebase_auth.set_custom_user_claims(uid, {
        "company_id": company_id,
        "tier": 1,
        "role": "coordinator",
    })

    audit_event(
        "auth_login",
        correlation_id=request.state.request_id,
        user_id=uid,
        company_id=company_id,
    )

    return OnboardResponse(
        user_id=uid,
        company_id=company_id,
        requires_token_refresh=True,  # client MUST force-refresh
    )
```

### 4.3 Idempotency

Three layers of safety in the handler above:

1. **Read-before-write on the Firestore doc.** If `users/{uid}` already exists we skip provisioning.
2. **`set_custom_user_claims` is itself idempotent** — passing the same dict overwrites with the same values.
3. **Two-call dedup:** the claim-refresh cost is avoided on the second call because the doc-exists branch returns `requires_token_refresh=False`.

If the handler dies *between* the Firestore write and the `set_custom_user_claims` call, the user is in a torn state: doc exists, claim missing. The idempotent second call heals it — the doc-exists branch does not re-stamp. To make *that* self-healing, upgrade the doc-exists branch to re-check the claim:

```python
if user_doc.exists:
    data = user_doc.to_dict() or {}
    user_record = firebase_auth.get_user(uid)
    current_claims = user_record.custom_claims or {}
    needs_refresh = current_claims.get("company_id") != data["company_id"]
    if needs_refresh:
        firebase_auth.set_custom_user_claims(uid, {
            "company_id": data["company_id"],
            "tier": 1,
            "role": data.get("role", "coordinator"),
        })
    return OnboardResponse(
        user_id=uid,
        company_id=data["company_id"],
        requires_token_refresh=needs_refresh,
    )
```

The extra `get_user` RPC is cheap compared to the user-visible weirdness of a half-provisioned account.

### 4.4 Rate limiting

Per `.claude/rules/security.md` §4:

- `/auth/onboard`: **5 requests / minute / IP.** Provisioning is a sensitive write; we cap it to prevent account-flooding during demo day.
- Keyed by `get_remote_address(request)` because `request.state.user_uid` is not yet populated (this is where it gets populated).
- Returns 429 with a `Retry-After` header.

Backed by the same Redis (Memorystore) that limits other routes.

### 4.5 Audit event

Every successful `/auth/onboard` emits `auth_login` via `audit_event` with `correlation_id`, `user_id`, `company_id`. Every failure emits `auth_failure` with the normalized error class. These flow through the structured log chain and are picked up by Cloud Run's log-to-trace correlation.

### 4.6 Why POST not GET

POST is correct for a mutation. A GET for "onboard-if-not-exists" would be caught by proxies / prefetch / link-previewers and silently provision accounts. FastAPI returns 200 rather than 201 because the resource (`users/{uid}`) is often already present on the second call and the Location header adds no value in an SPA flow.

---

## 5. Custom-claim setting via the Admin SDK

### 5.1 The canonical call

```python
firebase_auth.set_custom_user_claims(uid, {
    "company_id": "comp_nimblefreight",
    "tier": 1,
    "role": "coordinator",
})
```

### 5.2 Constraints

- **Server-only.** The JS client SDK cannot set custom claims — this is by Firebase design. Our `scripts/set_custom_claims.py` is the canonical CLI path; `/auth/onboard` is the canonical programmatic path.
- **Size cap: 1000 bytes** when JSON-serialized. The three-key payload above is ~80 bytes; the cap is effectively unbounded for our schema.
- **Replace, not merge.** Each call fully overwrites the user's custom claims. To add a key, read the current claims via `firebase_auth.get_user(uid).custom_claims`, merge, and write.
- **Reserved names not allowed.** Standard OIDC claim names (`aud`, `auth_time`, `exp`, `iat`, `iss`, `sub`, `email`, `email_verified`, `firebase`, etc.) are rejected.
- **Max 1500 uid-claim pairs total per project** per documented quota — irrelevant at Tier 1 scale.

### 5.3 Size budget check

Keep a runtime guardrail alongside the constant-time compare:

```python
import json
CLAIMS_BYTE_CAP = 900  # leave headroom under Firebase's 1000-byte limit

def safe_set_claims(uid: str, claims: dict) -> None:
    """Set claims after verifying they fit under the Firebase byte cap."""
    payload = json.dumps(claims, separators=(",", ":"))
    if len(payload.encode("utf-8")) > CLAIMS_BYTE_CAP:
        raise ValueError(f"claims payload too large: {len(payload)} bytes")
    firebase_auth.set_custom_user_claims(uid, claims)
```

Place in `scripts/set_custom_claims.py` and in `modules/triage/memory/user_claims.py` (the Tier 2 home for programmatic claim mutation).

### 5.4 Propagation latency

Custom claims are stamped onto the user record server-side **immediately**. But the user's currently-held ID token does *not* update — claims are baked at mint time.

Three options for client propagation:

1. **Force refresh** — `await user.getIdToken(true)` in the JS SDK. Forces a synchronous round-trip to Firebase Auth to mint a new token carrying the current claims. **This is what we do** in `/auth/onboard`'s response.
2. **Wait up to 1 hour** — default refresh cycle eventually picks up new claims. Unacceptable for onboarding.
3. **Server fetches latest claims on every request via `firebase_auth.get_user(uid)`** — costs one RPC per privileged call. Acceptable only on role-changes / tenant-moves where immediacy matters more than cost. See `.claude/rules/security.md` §3 propagation delay.

### 5.5 Never trust client-decoded claims

The browser can decode an ID token (it's a JWT — three base64 chunks). Never trust client-side role checks as the authorization gate. `FirebaseAuthMiddleware.verify_id_token` on the server is the only authoritative reader.

---

## 6. Demo-tenant assignment logic

### 6.1 Options

| Strategy | Pros | Cons |
|---|---|---|
| **A. Always `comp_nimblefreight`** | Simplest. Judge always sees the same data. Deterministic demo. | Can't show multi-tenancy working under real login — need a second judge or a manual step. |
| **B. Round-robin between `comp_nimblefreight` / `comp_swiftlogix`** | Live proof tenancy works at the auth layer. | Non-deterministic across judges — confuses "which tenant did I land in" demos. Needs a counter in Firestore or a hash of uid. |
| **C. Email-domain-based** | Legible demo: `@nimblefreight.com` → NimbleFreight, else SwiftLogix. | Judges don't use corporate email; nearly all go to the `else` branch. |
| **D. UID-hash-based** | Deterministic per judge, deterministic across restarts. Distribution even. | Hidden rule — explaining "you're in tenant X because your uid hashes to it" is worse than either of A or C. |

### 6.2 Decision

**Option A — always `comp_nimblefreight`** for Tier 1.

Rationale:
- The goal at Tier 1 is onboarding friction = zero and the demo narrative = "here is how one coordinator handles exceptions for NimbleFreight".
- Multi-tenancy is demonstrated separately by the `scripts/set_custom_claims.py` path: operator reassigns a test user to `comp_swiftlogix` and re-runs the same queries to show isolation.
- Option B moves to front-and-center in Tier 2 when self-serve onboarding with a tenant picker arrives.

### 6.3 Implementation

```python
def pick_demo_tenant(email: str) -> str:
    """Return the company_id to provision a new judge into.

    Tier 1: always the NimbleFreight demo tenant. Email is accepted for
    future email-domain-based assignment (Tier 2).
    """
    return "comp_nimblefreight"
```

Keeping the parameter makes the eventual Tier 2 upgrade a one-line change.

---

## 7. User document shape in Firestore

### 7.1 Shape

```
users/{uid}
  uid                  : str            # Firebase Auth UID, matches document ID
  company_id           : str            # tenant boundary; matches custom claim
  email                : str
  display_name         : str
  role                 : str            # coordinator | admin | viewer (Tier 2+)
  language_preference  : str            # en | hi | hi-en (Hinglish)
  communication_style  : str            # concise | detailed
  created_at           : Timestamp      # server time
  last_seen_at         : Timestamp      # updated on each /auth/onboard hit
```

### 7.2 Tie-back to Firebase Auth record

| Field | Source of truth |
|---|---|
| `uid` | Firebase Auth (also the Firestore doc ID) |
| `email`, `display_name` | Firebase Auth — replicated for query ergonomics |
| `company_id`, `role`, `tier` | Firebase Auth custom claims (authoritative); replicated to Firestore for rules |
| `language_preference`, `communication_style` | Firestore only — per-user UI prefs |
| `created_at`, `last_seen_at` | Firestore only |

Custom claims and the Firestore doc's `company_id` **must always agree**. If they drift, the self-healing path in §4.3 re-stamps. If drift is detected server-side during a request, emit an `audit_event("permission_denied", ...)` with `failure_reason="tenant_claim_drift"` and return 403.

### 7.3 Why duplicate `company_id` into Firestore

- Firestore rules only see custom claims via `request.auth.token`. For *server-side* queries under the Admin SDK (which bypasses rules) we still need the doc to carry `company_id` so other collections' rules can read it through join queries. See `.claude/rules/firestore.md` §8.
- Queries like "find me all users in `comp_nimblefreight`" are expressible on the Firestore side without needing the Auth SDK at all.

### 7.4 Model classes (Tier 2 shape)

```python
# modules/triage/models/user.py
class UserBase(BaseModel):
    email: EmailStr
    display_name: str

class UserCreate(UserBase):
    company_id: str
    role: Literal["coordinator", "admin", "viewer"] = "coordinator"

class UserPublic(UserBase):
    uid: str
    company_id: str
    role: str
    language_preference: str = "en"
    communication_style: str = "concise"

class UsersPublic(BaseModel):
    data: list[UserPublic]
    count: int
```

Naming pyramid per `.claude/rules/api-routes.md`.

---

## 8. Firestore rules and auto-onboarding

### 8.1 The `/users/{uid}` rule

Current state in `infra/firestore.rules`:

```
match /users/{userId} {
  allow read: if isAuthed() && request.auth.uid == userId;
  allow write: if false;
}
```

**This is correct and does not need to change for the onboarding flow.** The Admin SDK bypasses security rules entirely — `user_ref.set({...})` on the server side succeeds regardless of the `allow write: if false` rule. Client SDK writes to `/users/{uid}` stay blocked, which is exactly what we want.

### 8.2 Admin SDK is the only writer — confirmed

We enumerate every production write path:

| Write | Caller | Bypass rules? |
|---|---|---|
| `/users/{uid}.set(...)` on first onboard | `runners/routes/auth.py` — Admin SDK | Yes |
| `/users/{uid}.update({"last_seen_at": ...})` on subsequent onboards | same | Yes |
| `/users/{uid}.update({...})` on profile edits (Tier 2) | route handler — Admin SDK | Yes |
| Any client-side write | JS SDK | No — denied by rules |

Verified: no code path writes `/users/{uid}` from the client SDK. The `allow write: if false` rule is a defense-in-depth backstop.

### 8.3 Other collections' rules unchanged

All other `isCompanyMember(resource.data.company_id)` rules keep working because `request.auth.token.company_id` now arrives from our custom claim on every client request (and Admin-SDK writes bypass rules anyway).

---

## 9. Token-refresh UX

### 9.1 The mandatory refresh

After `/auth/onboard` responds with `requires_token_refresh: true`:

```ts
// Frontend (firebase-js-sdk v10+)
import { getAuth } from "firebase/auth";

async function onboardAndRefresh(): Promise<string> {
  const auth = getAuth();
  const user = auth.currentUser!;
  const initialToken = await user.getIdToken();

  const resp = await fetch("/api/v1/auth/onboard", {
    method: "POST",
    headers: { Authorization: `Bearer ${initialToken}` },
  });
  const body = await resp.json();

  if (body.requires_token_refresh) {
    // force a round-trip to Firebase Auth to mint a new token
    // that carries the freshly-stamped company_id / tier / role claims
    return await user.getIdToken(/* forceRefresh= */ true);
  }
  return initialToken;
}
```

### 9.2 Plain HTML / vanilla JS

For teams not using a bundler (hackathon landing page):

```html
<script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js"></script>
<script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-auth-compat.js"></script>
<script>
  firebase.initializeApp({ apiKey: "...", authDomain: "...", projectId: "..." });
  const auth = firebase.auth();

  async function signInAndOnboard() {
    const provider = new firebase.auth.GoogleAuthProvider();
    const result = await auth.signInWithPopup(provider);
    const user = result.user;
    const token = await user.getIdToken();

    const resp = await fetch("/api/v1/auth/onboard", {
      method: "POST",
      headers: { Authorization: "Bearer " + token }
    });
    const body = await resp.json();

    if (body.requires_token_refresh) {
      const newToken = await user.getIdToken(true);
      window.__apiToken = newToken;
    } else {
      window.__apiToken = token;
    }

    window.location.hash = "#/dashboard";
  }

  document.getElementById("signInBtn").onclick = signInAndOnboard;
</script>
```

### 9.3 React hook

```tsx
// hooks/useFirebaseAuth.tsx
import { useEffect, useState, useCallback } from "react";
import {
  getAuth,
  GoogleAuthProvider,
  onAuthStateChanged,
  signInWithPopup,
  signOut,
  User,
} from "firebase/auth";

export function useFirebaseAuth() {
  const [user, setUser] = useState<User | null>(null);
  const [apiToken, setApiToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const onboard = useCallback(async (u: User) => {
    const token = await u.getIdToken();
    const resp = await fetch("/api/v1/auth/onboard", {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
    });
    if (!resp.ok) throw new Error(`onboard ${resp.status}`);
    const body = await resp.json();
    const final = body.requires_token_refresh ? await u.getIdToken(true) : token;
    setApiToken(final);
  }, []);

  useEffect(() => {
    const auth = getAuth();
    const unsub = onAuthStateChanged(auth, async (u) => {
      setUser(u);
      if (u) await onboard(u);
      else setApiToken(null);
      setLoading(false);
    });
    return unsub;
  }, [onboard]);

  const login = useCallback(async () => {
    const auth = getAuth();
    await signInWithPopup(auth, new GoogleAuthProvider());
  }, []);

  const logout = useCallback(() => signOut(getAuth()), []);

  return { user, apiToken, loading, login, logout };
}
```

### 9.4 Why in-memory storage, not localStorage

Firebase client SDK persists the refresh-token material to IndexedDB via its own encryption; that's the well-reviewed primitive. **Our copy of the ID token should live in memory only** (React state / `window.__apiToken` at worst). Stuffing ID tokens into localStorage creates an XSS exfiltration target with none of the protections the SDK provides — a single reflected XSS on the dashboard would let an attacker read every authenticated token.

---

## 10. Cross-origin auth — Firebase Hosting → Cloud Run

### 10.1 The topology

- **Frontend:** Firebase Hosting at `https://sct-prod.web.app` (or similar).
- **API:** Cloud Run at `https://sct-api-<hash>-uc.a.run.app`.

Different origins. CORS applies.

### 10.2 Choice: bearer tokens, not cookies

Three options considered:

| Pattern | Pros | Cons |
|---|---|---|
| **`Authorization: Bearer <id_token>`** | Works cross-origin trivially. No CSRF surface. SSE + XHR + fetch all carry it identically. Stateless on server. | Token visible to JS (mitigated by in-memory storage). |
| **Firebase session cookies** (`__session` cookie) | Long-lived (up to 2 weeks), revocable, HttpOnly. | Cross-origin cookie needs `SameSite=None; Secure` + `credentials: include` on every fetch. CSRF defenses required (double-submit / origin check). Adds infra. |
| **Reverse proxy same-origin** | Sidesteps cross-origin. | Adds Cloud Load Balancer + routing complexity; not worth it at Tier 1. |

**Decision: bearer tokens.** Matches how the existing `FirebaseAuthMiddleware` already works. Session-cookie support can be layered on at Tier 3 when we have a long-running dashboard to worry about.

### 10.3 CORS configuration

```python
# runners/app.py — already per .claude/rules/security.md §11
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,  # exact match, no wildcards in prod
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    allow_credentials=False,  # bearer tokens — no cookies — no credentials needed
    max_age=3600,
)
```

- `allow_credentials=False` because we don't use cookies. Setting it to True forces strict wildcard-free origins but buys us nothing else.
- `allow_headers` must include `Authorization` or the preflight fails.
- `CORS` middleware runs **before** `FirebaseAuthMiddleware` per `.claude/rules/security.md` §9 middleware stack order — preflight OPTIONS must not require credentials.

### 10.4 CSRF considerations

With bearer tokens we don't need CSRF tokens:

- Requests are authorized by the `Authorization` header, not by ambient cookies.
- A malicious cross-origin site cannot read our token (it's not in its origin) and cannot forge headers on a cross-origin request under the same-origin policy.
- We still set `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'` per `.claude/rules/security.md` §5 to prevent UI redress attacks.

If we switched to session cookies at Tier 3, we'd add either:

- Origin-header checks on every mutating route.
- A CSRF token round-tripped via a same-origin initial request.

Deferred — bearer tokens remain the recommendation.

---

## 11. SSE + auth

The triage pipeline streams results via Server-Sent Events. Auth on SSE is the single rough edge in the bearer-token story.

### 11.1 The problem

The W3C `EventSource` API **cannot set custom request headers**. `new EventSource(url)` sends cookies and that's it. Our `Authorization: Bearer <id_token>` scheme is incompatible out of the box.

### 11.2 Three solutions, ranked

| Solution | How it works | Pros | Cons |
|---|---|---|---|
| **A. `fetch`-based SSE polyfill** (e.g. `@microsoft/fetch-event-source`) | Opens a streaming `fetch` with custom headers; dispatches SSE events manually. | Headers work like any other request. Supports `AbortController` for clean disconnect. Retry semantics configurable. | Adds a JS dep (~15 KB). |
| **B. Query-param token** (`?token=...`) | Token sent as URL param. | Works with native `EventSource`. | Token appears in Cloud Run access logs, in browser history, in referrer headers. Terrible security hygiene. |
| **C. Short-lived signed URL** | Backend mints a one-shot signed token specifically for the SSE connection; client passes it as query param. | Blast radius limited to one stream. | Custom minting infra; extra round-trip. |

### 11.3 Decision: Solution A — `fetch-event-source`

```ts
import { fetchEventSource } from "@microsoft/fetch-event-source";

await fetchEventSource("/api/v1/triage/stream", {
  method: "POST",
  headers: {
    "Authorization": `Bearer ${apiToken}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ exception_id }),
  onmessage(ev) { /* ... */ },
  onerror(err) {
    // polyfill will retry unless we throw here
    if (err?.status === 401) throw err;
  },
});
```

### 11.4 Server side

No change to the middleware. The FastAPI route consumes the `Authorization` header identically to any other request; the fact that it responds with `text/event-stream` is irrelevant to auth.

One subtlety: if an ID token expires mid-stream (1-hour cap), the server cannot "re-auth" the open connection — it just observes the expiry on the next middleware pass, which won't happen mid-stream. The client polyfill's `onerror` / reconnect hook is where we re-mint a fresh token via `user.getIdToken(true)` and reconnect. For Tier 1 demos the 1-hour window is generous — judges spend 10 minutes in the app.

### 11.5 CSP adjustments

SSE rides over HTTPS, so `connect-src 'self'` in the existing CSP is sufficient. No `frame-src` or `media-src` changes needed.

---

## 12. Emulator-based auth testing

Follow `.claude/rules/testing.md` §7 — two patterns, picked per test kind.

### 12.1 Unit + most integration: dependency override

```python
# tests/conftest.py
import pytest
from fastapi import FastAPI
from supply_chain_triage.middleware.firebase_auth import FirebaseUser
from supply_chain_triage.runners.dependencies import get_current_user

@pytest.fixture
def authed_app(app: FastAPI):
    """App with auth overridden to a fixed test user."""
    def _fake_user():
        return FirebaseUser(
            uid="test-user-uid",
            email="test@example.com",
            company_id="comp_nimblefreight",
            role="coordinator",
            tier=1,
        )
    app.dependency_overrides[get_current_user] = _fake_user
    yield app
    app.dependency_overrides.clear()  # mandatory — cross-test leakage otherwise
```

### 12.2 Middleware integration: real Auth emulator

```python
# tests/integration/conftest.py
import os
import httpx
import pytest
from firebase_admin import auth as firebase_auth

@pytest.fixture(scope="session", autouse=True)
def _auth_emulator_env():
    # MUST be set before firebase_admin initializes. Never leaks to prod.
    os.environ["FIREBASE_AUTH_EMULATOR_HOST"] = "localhost:9099"
    yield

@pytest.fixture
async def authed_token(_auth_emulator_env) -> str:
    """Mint a real Firebase ID token via the Auth emulator."""
    uid = "test-u-1"
    firebase_auth.create_user(uid=uid, email="judge@example.com")
    firebase_auth.set_custom_user_claims(uid, {"company_id": "comp_nimblefreight", "tier": 1, "role": "coordinator"})
    custom_token = firebase_auth.create_custom_token(uid).decode()

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            "http://localhost:9099/identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken",
            params={"key": "fake-api-key"},
            json={"token": custom_token, "returnSecureToken": True},
        )
    return resp.json()["idToken"]
```

### 12.3 Per-endpoint checklist contributions

Per `.claude/rules/testing.md` §10, every route gets:

- 401 no token.
- 403 wrong tenant / tier.
- Auth-emulator round-trip (at least one per route-group).

For `/auth/onboard` specifically, the test matrix is:

| # | Scenario | Asserts |
|---|---|---|
| 1 | 401 no token | `detail == "missing_credentials"` |
| 2 | 401 expired token | `detail == "token_expired"` |
| 3 | 401 invalid signature | `detail == "invalid_token"` |
| 4 | 200 first sight — creates doc + sets claim | Firestore has `users/{uid}` with correct shape; `get_user(uid).custom_claims["company_id"] == "comp_nimblefreight"`; response `requires_token_refresh == True` |
| 5 | 200 idempotent — second call | Firestore doc unchanged; response `requires_token_refresh == False` |
| 6 | 200 self-heal — doc exists, claim missing | claim re-stamped; response `requires_token_refresh == True` |
| 7 | 429 rate-limit after 6 calls in 60s | `Retry-After` header present |
| 8 | audit event `auth_login` emitted on success | log capture fixture picks up entry |

### 12.4 Cleanup

```python
@pytest.fixture(autouse=True)
async def _clear_emulators(_auth_emulator_env):
    """Wipe emulator state between tests."""
    yield
    async with httpx.AsyncClient() as client:
        await client.delete(
            "http://localhost:9099/emulator/v1/projects/sct-test/accounts"
        )
        await client.delete(
            "http://localhost:8080/emulator/v1/projects/sct-test/databases/(default)/documents"
        )
```

---

## 13. Security hardening

A grab-bag of must-haves layered on top of the baseline flow.

### 13.1 Revocation check policy

Per `.claude/rules/security.md` §1 and §12:

- **Off** on `/auth/onboard` and standard request paths.
- **On** for: future `/admin/*` endpoints, any role-elevation endpoint, any endpoint that changes `company_id`. Pattern:

```python
claims = firebase_auth.verify_id_token(token, check_revoked=True)
```

### 13.2 Token age cap

See §3.5 — reject tokens with `iat` more than 3600s old even if the SDK didn't.

### 13.3 Audit every login

Canonical event per `.claude/rules/observability.md` §6:

```python
audit_event(
    "auth_login",
    correlation_id=request_id,
    user_id=uid,
    company_id=company_id,
)
```

Failure path:

```python
audit_event(
    "auth_failure",
    correlation_id=request_id,
    user_id="unknown",
    company_id="system",
    failure_reason="token_expired",
)
```

### 13.4 Cross-tenant drift detection

If the decoded token's `company_id` disagrees with the Firestore `users/{uid}.company_id`, short-circuit the request:

```python
claims = firebase_auth.verify_id_token(token)
token_company = claims.get("company_id")
user_doc = await db.collection("users").document(claims["uid"]).get()
firestore_company = (user_doc.to_dict() or {}).get("company_id")
if token_company != firestore_company:
    audit_event("permission_denied", ..., failure_reason="tenant_claim_drift")
    raise HTTPException(403, "tenant_mismatch")
```

Do this only on privileged mutations — not on every request (the self-heal path in §4.3 is cheaper for the common case).

### 13.5 Email-enumeration protection

Not directly relevant for Google OAuth — Google's own flow handles account existence. If we later add password flows, `.claude/rules/security.md` §2 covers this.

### 13.6 OAuth scopes — least privilege

Our Google provider requests **only** the `openid email profile` scopes. Never request `https://www.googleapis.com/auth/gmail.readonly` or similar unless a feature genuinely needs it.

```ts
const provider = new GoogleAuthProvider();
// default scopes are sufficient: openid email profile
// DO NOT call provider.addScope("https://www.googleapis.com/auth/...") unless required
```

### 13.7 Authorized domains allowlist

In Firebase Console → Authentication → Settings → Authorized domains, list **only**:
- `localhost` (dev)
- `<project>.web.app` / `<project>.firebaseapp.com` (Hosting)
- Custom prod domain if any

Default allowlists commonly include legacy domains — review and trim.

### 13.8 Unicode + HTML sanitization

Per `.claude/rules/security.md` §10, the `display_name` we pull from Google is passed through `sanitize_input` before being persisted to Firestore. Devanagari + Hinglish are preserved; control chars and HTML are stripped.

---

## 14. Judge-facing credentials panel

### 14.1 Copy

```
Sign in to see the triage demo

[ Sign in with Google ]

You'll be placed in the NimbleFreight demo tenant. Two seconds.
We don't store your password — sign-in is handled by Google.
```

### 14.2 Layout sketch (HTML)

```html
<main style="display:flex;align-items:center;justify-content:center;min-height:100vh">
  <section style="max-width:420px;text-align:center;padding:32px">
    <img src="/logo.svg" alt="Supply Chain Triage" style="height:64px;margin-bottom:24px"/>
    <h1 style="font-size:28px;margin:0 0 8px">Supply Chain Exception Triage</h1>
    <p style="color:#6b7280;margin:0 0 32px">One-click onboarding for judges.</p>

    <button id="signInBtn"
            style="width:100%;padding:12px 24px;background:#4285F4;color:#fff;border:0;border-radius:8px;font-weight:600;cursor:pointer">
      Sign in with Google
    </button>

    <p style="color:#6b7280;font-size:13px;margin-top:16px;line-height:1.5">
      You'll be placed in the <strong>NimbleFreight</strong> demo tenant.<br/>
      Takes 2 seconds. We don't store your password.
    </p>
  </section>
</main>
```

### 14.3 React variant

```tsx
export function LandingPage() {
  const { login, loading } = useFirebaseAuth();
  return (
    <main className="flex min-h-screen items-center justify-center">
      <section className="max-w-sm text-center px-8">
        <img src="/logo.svg" alt="" className="h-16 mb-6 mx-auto"/>
        <h1 className="text-2xl font-semibold mb-2">Supply Chain Exception Triage</h1>
        <p className="text-slate-500 mb-8">One-click onboarding for judges.</p>
        <button
          onClick={login}
          disabled={loading}
          className="w-full bg-blue-600 text-white rounded-lg py-3 font-medium"
        >
          {loading ? "Loading..." : "Sign in with Google"}
        </button>
        <p className="text-sm text-slate-500 mt-4 leading-relaxed">
          You'll be placed in the <strong>NimbleFreight</strong> demo tenant.<br/>
          Takes 2 seconds. We don't store your password.
        </p>
      </section>
    </main>
  );
}
```

### 14.4 Explicitly NOT offered

- **Password login.** Adds two flows (signup + reset), doubles the attack surface, adds zero credibility for a judge. OAuth-only is simpler and looks more serious.
- **Anonymous auth.** Would let a judge skip the "Sign in with Google" step; we lose email for audit trails and lose the instinct that this is a real product.
- **Magic links.** Require a working SMTP path we don't need for a hackathon.

---

## 15. Future Tier 2+ considerations

Not in scope for Tier 1. Notes for the session that picks up after the deadline.

### 15.1 Self-serve multi-tenant onboarding

- Add `/auth/tenant/create` — authenticated user creates a new company, becomes its admin. Generates a company-scoped invite link.
- Add `/auth/tenant/join?invite=<token>` — user accepts invite, gets added to that tenant's member list, claims updated to that tenant.
- Tenant picker UI for users in ≥2 tenants — claims carry the *current* tenant; switch triggers a force refresh.

### 15.2 Invite links

- Opaque token (ULID or UUIDv7) stored in Firestore with `{company_id, invited_email, expires_at, consumed_by}`.
- Rate-limited aggressively (1 creation per minute per admin; 10 redemptions per minute per IP).
- Single-use by default; optionally time-boxed multi-use with a cap.

### 15.3 Role-based permissions

- Roles: `admin`, `coordinator`, `viewer`. Ordered integer in the claim:
  ```python
  ROLE_TIER = {"viewer": 0, "coordinator": 1, "admin": 2}
  ```
- `require_role(min_tier)` dep matching `require_tier` from `.claude/rules/security.md` §3.
- `admin` can reassign users' tenants; `coordinator` can write exceptions; `viewer` can only read.

### 15.4 Multiple identity providers

- Microsoft OAuth for enterprise demos (same flow, different provider wiring).
- Email/password as a fallback, with email-verification enforced (`email_verified: true` as a precondition to any mutation). Gated behind an ADR because of the added attack surface.

### 15.5 Audit-log UX

Dashboard view for tenant admins showing recent `auth_login`, `auth_failure`, `permission_denied`, `tenant_claim_drift` events scoped to their tenant. Reads from BigQuery log export.

### 15.6 Firebase Auth session cookies

For long-running dashboards, switch to the session-cookie pattern described in §10.2. Requires same-origin or `SameSite=None; Secure` with CSRF defenses. Defer until a real need emerges.

---

## 16. Concrete next-session task list

File-by-file, ordered by dependency.

### 16.1 Backend

| # | File | Change |
|---|---|---|
| 1 | `src/supply_chain_triage/middleware/firebase_auth.py` | Add `RevokedIdTokenError` branch; add `MAX_TOKEN_AGE_SECONDS` cap check; narrow docstring to note new behavior. |
| 2 | `src/supply_chain_triage/runners/dependencies.py` (NEW) | Define `get_current_user` raw + tenant-scoped dep factories. Source of truth that routes use instead of reading `request.state` directly. |
| 3 | `src/supply_chain_triage/runners/routes/auth.py` (NEW) | Implement `POST /api/v1/auth/onboard`. See §4.2. |
| 4 | `src/supply_chain_triage/runners/app.py` | Register the new router; add `/api/v1/auth/onboard` to `FirebaseAuthMiddleware.public_paths`. |
| 5 | `src/supply_chain_triage/modules/triage/memory/user_claims.py` (NEW) | Wrap `set_custom_user_claims` with the size-cap guard from §5.3. |
| 6 | `src/supply_chain_triage/modules/triage/models/user.py` (NEW) | `UserBase`, `UserCreate`, `UserPublic`, `UsersPublic` — pyramid from §7.4. |
| 7 | `scripts/set_custom_claims.py` | Use the new `user_claims.safe_set_claims` wrapper rather than calling the SDK directly. |

### 16.2 Frontend (framework-agnostic first)

| # | File | Change |
|---|---|---|
| 8 | `public/index.html` | Landing page with "Sign in with Google" button + explainer (§14.2). |
| 9 | `public/auth.js` | Vanilla flow — `signInAndOnboard` from §9.2. Mint token, POST onboard, force-refresh. |
| 10 | `public/api.js` | Thin wrapper that injects `Authorization: Bearer` from an in-memory token. |
| 11 | `public/sse.js` | SSE via `@microsoft/fetch-event-source` (or equivalent) — §11.3. |

If React: replace #9-11 with `hooks/useFirebaseAuth.tsx` (§9.3) plus `lib/api.ts` and `lib/sse.ts`.

### 16.3 Infra

| # | File | Change |
|---|---|---|
| 12 | `infra/firestore.rules` | No change — confirmed adequate in §8. |
| 13 | Firebase Console — Authorized domains | Trim to `localhost`, `<project>.web.app`, and prod domain (§13.7). |
| 14 | Firebase Console — Enable Google provider | Enable, set support email, restrict scopes to `openid email profile` default. |

### 16.4 Tests

| # | File | Change |
|---|---|---|
| 15 | `tests/integration/auth/test_onboard.py` (NEW) | Full matrix from §12.3 — 8 scenarios. |
| 16 | `tests/unit/middleware/test_firebase_auth.py` | Add cases for `RevokedIdTokenError` and `token_too_old`. |
| 17 | `tests/integration/conftest.py` | Session-scoped Auth emulator env setup per §12.2 + cleanup fixture per §12.4. |

### 16.5 Observability

| # | File | Change |
|---|---|---|
| 18 | `src/supply_chain_triage/middleware/audit_log.py` | Confirm `auth_login` and `auth_failure` events in the canonical names table (already listed per `.claude/rules/observability.md` §6). |
| 19 | Dashboard log view | Add a sample Cloud Logging query for `jsonPayload.event = "auth_login"` scoped to the last hour. |

### 16.6 Documentation

| # | File | Change |
|---|---|---|
| 20 | `docs/sessions/2026-04-18-firebase-auth-onboard.md` (NEW) | Session note recording this research document and the decisions taken. |
| 21 | `README.md` | One-paragraph section "How the demo judge logs in" linking to this research doc. |

---

## 17. Sources + dates

All consulted 2026-04-18. Firebase Auth product docs have been stable since 2023; the auto-provisioning pattern is long-documented.

### Official Firebase / Google docs

- **Firebase Auth ID-token verification** — https://firebase.google.com/docs/auth/admin/verify-id-tokens (Python Admin SDK section).
- **Firebase Auth custom claims** — https://firebase.google.com/docs/auth/admin/custom-claims — size limit, propagation semantics, reserved claim names.
- **Firebase Admin Python SDK reference** — https://firebase.google.com/docs/reference/admin/python/firebase_admin.auth.
- **Firebase Auth emulator** — https://firebase.google.com/docs/emulator-suite/connect_auth — REST endpoints, sign-in-with-custom-token flow, env var honoring.
- **Firebase JS SDK `signInWithPopup` / `signInWithRedirect`** — https://firebase.google.com/docs/auth/web/google-signin — choice between popup and redirect, authorized domains.
- **`getIdToken(forceRefresh)`** — https://firebase.google.com/docs/reference/js/auth.user#usergetidtoken — explicit note that custom claims require refresh to propagate.
- **Firestore security rules with custom claims** — https://firebase.google.com/docs/firestore/security/rules-conditions — `request.auth.token.<claim>` semantics.
- **Firebase Auth session cookies** — https://firebase.google.com/docs/auth/admin/manage-cookies — considered, deferred.
- **Google Identity Platform multi-tenancy** — https://cloud.google.com/identity-platform/docs/multi-tenancy — alternative we rejected for Tier 1.

### Standards

- **OIDC Core 1.0** — https://openid.net/specs/openid-connect-core-1_0.html.
- **RFC 6750 — OAuth 2.0 Bearer Token Usage** — https://datatracker.ietf.org/doc/html/rfc6750.
- **RFC 7519 — JWT** — https://datatracker.ietf.org/doc/html/rfc7519.
- **W3C EventSource (SSE)** — https://html.spec.whatwg.org/multipage/server-sent-events.html — confirms no custom-header support on native `EventSource`.

### Ecosystem references

- **`@microsoft/fetch-event-source`** — https://github.com/Azure/fetch-event-source — chosen SSE polyfill.
- **FastAPI security deps** — https://fastapi.tiangolo.com/tutorial/security/ — `HTTPBearer` pattern used by `.claude/rules/api-routes.md` §5.
- **Starlette middleware ordering** — https://www.starlette.io/middleware/#using-middleware — reverse-add-order wrapping confirmed, backs `.claude/rules/security.md` §9.

### Internal references

- `.claude/rules/security.md` — Firebase-specific security rules, custom-claim size + propagation, middleware stack ordering.
- `.claude/rules/api-routes.md` — Dependency order, response envelopes, status codes.
- `.claude/rules/firestore.md` — Admin SDK bypasses rules; AsyncClient; cursor pagination.
- `.claude/rules/testing.md` — A/B rule for auth in tests; emulator patterns; per-endpoint checklist.
- `.claude/rules/observability.md` — `audit_event` contract; canonical event names; PII redaction.
- `docs/research/zettel-firestore-multi-tenant.md` — companion zettel that informed the custom-claim-tenancy choice.
- `docs/research/Supply-Chain-Firestore-Schema-Tier1.md` §385-441 — authoritative multi-tenant rules reference.
- `src/supply_chain_triage/middleware/firebase_auth.py` — existing middleware that this document extends.
- `scripts/set_custom_claims.py` — existing Admin-SDK claim-setter; reference pattern for the onboarding endpoint.
- `infra/firestore.rules` — existing rules confirmed adequate under the Admin-SDK-only-writer model.

---

## Appendix A — Decision log

| Decision | Options | Choice | Rationale |
|---|---|---|---|
| IdP | Google, Microsoft, email/password, anonymous | Google only | Lowest friction for hackathon judges; enterprise-credible; zero password UI. |
| Tenancy model | GCP Identity Platform tenants, per-project isolation, custom-claim on shared project | Custom-claim on shared project | Lowest infra cost; matches existing middleware; Firestore rules already compatible. |
| Token transport | Bearer, session cookie, reverse proxy | Bearer | Cross-origin trivial; no CSRF surface; matches existing middleware. |
| Claim propagation | Force refresh, wait 1 hour, server re-fetch | Force refresh after `/auth/onboard` | Only sub-second option; required for immediate dashboard access. |
| Demo tenant assignment | Always NimbleFreight, round-robin, email-domain, uid-hash | Always NimbleFreight | Deterministic demo; multi-tenant shown separately via CLI. |
| SSE auth | `EventSource`+query param, fetch polyfill, signed URL | fetch polyfill | Keeps bearer-token pattern; no token in URLs. |
| Session cookies | Adopt now, adopt later, never | Later (Tier 3 if needed) | No current need; bearer tokens do the job. |
| Revocation check | Always on, always off, privileged routes only | Privileged routes only | Free-tier RPC budget; most routes don't need it. |
| Auto-provision write path | Client-side, Cloud Function, FastAPI endpoint | FastAPI endpoint | Keeps all auth logic in one service; no extra deploy target. |

## Appendix B — Glossary

- **ID token.** Short-lived (1h) JWT minted by Firebase Auth; proves identity + custom claims.
- **Refresh token.** Long-lived token held by the Firebase JS SDK; used to mint new ID tokens.
- **Custom claim.** Key-value stamped on a Firebase Auth user record via Admin SDK; shows up in every subsequently-minted ID token.
- **`company_id`.** Our tenant-boundary custom claim. Value shape: `comp_<slug>`.
- **Tier.** Our role ordinal, integer. 0 = viewer, 1 = coordinator, 2 = admin.
- **Custom token.** Short-lived token *we* sign with the Admin SDK (e.g. in tests) — the client then exchanges it via `signInWithCustomToken` for a real ID token.
- **Session cookie.** Firebase-minted long-lived cookie set by the server; alternative to bearer tokens for long-running dashboards.
- **Force refresh.** `user.getIdToken(true)` — bypasses the SDK's default cache and round-trips to Firebase to mint a fresh ID token.

---
