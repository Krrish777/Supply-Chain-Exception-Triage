---
title: Firestore multi-tenant — company_id custom claims + rules + Admin SDK seeding
type: zettel
tags: [firestore, security-rules, multi-tenant, firebase-auth, zettel]
status: first-principles
last_updated: 2026-04-14
confidence: high
sources:
  - https://firebase.google.com/docs/rules/rules-and-auth
  - https://firebase.google.com/docs/auth/admin/custom-claims
  - https://dev.to/alvardev/firebase-firestore-rules-with-custom-claims-an-easy-way-523d
  - https://medium.com/firebase-developers/patterns-for-security-with-firebase-supercharged-custom-claims-with-firestore-and-cloud-functions-bb8f46b24e11
related:
  - "[[Supply-Chain-Firestore-Schema-Tier1]]"
  - "[[zettel-supermemory-python-sdk]]"
---

# Firestore multi-tenant — company_id custom claims + rules + Admin SDK seeding

> **TL;DR.** Canonical pattern: set `company_id` as a custom claim on the Firebase ID token via Admin SDK; security rules compare `request.auth.token.company_id == resource.data.company_id` on every read/write. Custom claims don't auto-refresh — client must force an ID token refresh after claim change. Claims can only be set server-side.

## First principles

**Multi-tenancy in a serverless database means "each row carries its tenant"**. There's no database-per-tenant (too expensive at scale), no schema-per-tenant (Firestore doesn't have schemas). Every document has a `company_id` field; every query filters on it; security rules enforce it at the database boundary.

**Three moving parts must agree:**

1. **Data shape** — every document stores `company_id` as an indexed field.
2. **Auth token** — every authenticated user's ID token carries `company_id` as a custom claim.
3. **Rule** — on every read/write, `request.auth.token.company_id == resource.data.company_id`.

If any one of the three is off, either (a) users see cross-tenant data, or (b) legitimate reads fail.

## Why custom claims, not a `users` collection lookup

Naive pattern: "look up the user's `company_id` from a `users` collection inside the rule." Security rules support `get()` but every rule evaluation costs a read. With N documents in a query × 1 user lookup per doc = N reads just to authorize. Custom claims live in the token — zero reads, O(1) authorization.

Cost: you trust the token. The token is signed by Firebase; claims are trusted until the token expires (default 1 hour).

## Setting a custom claim (server-side only)

```python
from firebase_admin import auth

def set_company_claim(uid: str, company_id: str) -> None:
    """Attach company_id to user's Firebase ID token.

    Claim takes effect on the NEXT token refresh — clients must call
    getIdToken(true) to force refresh, or wait up to 1 hour.
    """
    auth.set_custom_user_claims(uid, {"company_id": company_id})
```

The client cannot set this. Requires Admin SDK (Service Account). Ours lives in `scripts/set_custom_claims.py` for the test-user flow; production uses a Cloud Function triggered on user signup.

## Firestore rules pattern

```javascript
// firestore.rules
rules_version = '2';

service cloud.firestore {
  match /databases/{database}/documents {
    function isCompanyMember(cid) {
      return request.auth != null
        && request.auth.token.company_id == cid;
    }

    match /companies/{companyId} {
      allow read: if isCompanyMember(companyId);
      allow write: if false;  // Admin SDK only
    }

    match /shipments/{shipmentId} {
      allow read: if isCompanyMember(resource.data.company_id);
      allow create: if isCompanyMember(request.resource.data.company_id);
      allow update, delete: if isCompanyMember(resource.data.company_id);
    }

    match /exceptions/{exceptionId} {
      allow read: if isCompanyMember(resource.data.company_id);
      allow create: if isCompanyMember(request.resource.data.company_id);
    }

    match /{static}/{doc} {
      // festival_calendar, monsoon_regions — authenticated read only
      allow read: if request.auth != null && (
        static == 'festival_calendar' || static == 'monsoon_regions'
      );
      allow write: if false;
    }
  }
}
```

Two patterns worth memorizing:
- **`match /shipments/{doc}`** uses `resource.data.company_id` — enforces isolation on any existing document.
- **`allow create`** uses `request.resource.data.company_id` — the *incoming* document must tag itself with the caller's company_id. Prevents users from writing cross-tenant data.

## Project implications

1. **Sprint 0 creates `infra/firestore.rules`.** Copy vault `Supply-Chain-Firestore-Schema-Tier1` §385-441 verbatim, apply above patterns.
2. **Test 2.5 positive counterpart needs `scripts/set_custom_claims.py`.** Web research revealed this gap. Script sets `company_id` on a Firebase Auth test user; test verifies protected endpoint returns 200 (not 403).
3. **Firestore Emulator treats claims differently.** The emulator accepts `FIREBASE_AUTH_EMULATOR_HOST`-signed tokens without signature verification. Useful for test fixtures, dangerous in production — `FIREBASE_AUTH_EMULATOR_HOST` must NEVER be set in Cloud Run env (per `.claude/rules/testing.md` §6).
4. **ID token refresh after claim change.** If we ever change a user's `company_id` (re-org, tenant migration), clients see stale claims for up to 1 hour. Document this in SECURITY.md for Sprint 0.
5. **Custom claims are 1KB max** (Firebase limit). Don't put user profile data in claims — keep claims to identifiers (`uid`, `company_id`, `role`). Profile data lives in Firestore `users` collection.

## Index requirements

Multi-tenant queries need composite indexes. From vault Firestore-Schema-Tier1:
- `company_id + vehicle_id + status`
- `company_id + route_id + status`
- `company_id + region + status`
- `company_id + customer_id + status`
- `company_id + status + deadline`
- `company_id + created_at` (exceptions audit)
- `company_id + classification.exception_type` (exceptions audit)

Sprint 0 creates `infra/firestore.indexes.json` with these; Sprint 5 deploy runs `firebase deploy --only firestore:indexes`.

## Gotchas flagged

- **Claim propagation latency.** Client-side JS SDK caches the ID token for up to 1 hour. After a claim change, call `currentUser.getIdToken(true)` to force refresh. Document in `.claude/rules/api-routes.md`.
- **Rule evaluations cost** — deeply nested `get()` calls in rules are expensive. Our pattern above uses only `resource.data` access (free) + `request.auth.token` (free). Zero reads per authorization.
- **Claim key collisions.** Firebase reserves some claim names (`iss`, `sub`, `aud`, `exp`, etc.). `company_id` is safe — not reserved. Don't use `sub` for our tenant ID.
- **Admin SDK can bypass rules entirely.** Server-side code using `firebase_admin` reads/writes without rule evaluation. Useful for the seed script, dangerous if bugs let user-controllable data reach the Admin SDK. Audit all Admin SDK call sites in SECURITY.md.

## Further research

- **Service account for Cloud Run vs dev SA.** Sprint 5 deployment — how do we provision the production SA with least privilege while the dev SA has `secretmanager.secretAccessor + datastore.user`? See vault `Supply-Chain-Deployment-Options-Research`.
- **Firebase's Identity Platform multi-tenancy** — Firebase offers *tenant-level* separation at the Identity Platform layer (different auth, different config per tenant). Overkill for us (we run one auth project) but worth knowing exists.
- **Rate limiting at the rules layer.** Not natively supported. Rate limits live in App Check + our middleware layer (Sprint 4 scope).
- **Exceptions audit collection and retention.** How long do we keep `exceptions` collection data per tenant? Compliance question for real-data phase.

## Related decisions

- **ADR-005 Testing strategy** — emulator fixtures and the `FIREBASE_AUTH_EMULATOR_HOST` discipline.
- **`.claude/rules/firestore.md`** — project conventions for Firestore access.
- **`[[Supply-Chain-Firestore-Schema-Tier1]]`** — full data model (collections, indexes, rules).
