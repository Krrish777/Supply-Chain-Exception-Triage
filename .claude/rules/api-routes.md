---
description: FastAPI route design — dependency order, response envelopes, error codes, security messages
paths: ["src/supply_chain_triage/runners/**", "src/supply_chain_triage/middleware/**"]
---

# API route rules

FastAPI is a thin surface over ADK agents plus auxiliary CRUD. These patterns apply to every route regardless of which category.

## 1. Router setup

```python
router = APIRouter(prefix="/exceptions", tags=["exceptions"])
```

- **prefix**: lowercase plural noun matching the resource (`/exceptions`, `/users`, `/triage-results`)
- **tags**: match the prefix — drives OpenAPI grouping and SDK class names

## 2. Function signatures by method

```python
@router.get("/{exception_id}", response_model=ExceptionPublic)
async def read_exception(
    db: FirestoreDep, current_user: CurrentUser, exception_id: str
) -> Any: ...

@router.get("/", response_model=ExceptionsPublic)
async def list_exceptions(
    db: FirestoreDep, current_user: CurrentUser, skip: int = 0, limit: int = 50
) -> Any: ...

@router.post("/", response_model=ExceptionPublic)
async def create_exception(
    *, db: FirestoreDep, current_user: CurrentUser, payload: ExceptionCreate
) -> Any: ...

@router.patch("/{exception_id}", response_model=ExceptionPublic)
async def update_exception(
    *, db: FirestoreDep, current_user: CurrentUser,
    exception_id: str, payload: ExceptionUpdate,
) -> Any: ...

@router.delete("/{exception_id}")
async def delete_exception(
    db: FirestoreDep, current_user: CurrentUser, exception_id: str
) -> Message: ...
```

## 3. Dependency parameter order (ENFORCED)

```
db: FirestoreDep,          # 1. Firestore async client (always first)
current_user: CurrentUser, # 2. Authenticated user (if needed)
exception_id: str,         # 3. Path parameters
payload: ExceptionCreate,  # 4. Request body
skip: int = 0,             # 5. Query params with defaults (last)
limit: int = 50,
```

- Leading `*` makes args keyword-only — use whenever the signature has both deps and a body param.
- Type-hint path params directly (`exception_id: str`), no `Path()` unless validation needed.
- Query params always have defaults.
- Every route has a one-line docstring.

## 4. Dependencies table

| Dependency | Type | Purpose |
|---|---|---|
| `FirestoreDep` | `Annotated[AsyncClient, Depends(get_firestore)]` | Firestore async client (singleton from `app.state.db`) |
| `CurrentUser` | `Annotated[FirebaseUser, Depends(get_current_user)]` | Verified Firebase ID token, required |
| `OptionalUser` | `Annotated[FirebaseUser \| None, Depends(get_optional_user)]` | Routes with public + auth'd modes |
| `TokenDep` | `Annotated[HTTPAuthorizationCredentials, Depends(security)]` | Raw bearer creds when you need the token string |

## 5. Firebase Auth dependency (HTTPBearer + `Depends`, NOT middleware)

```python
from fastapi.security import HTTPBearer
from firebase_admin import auth as firebase_auth
from firebase_admin.auth import (
    InvalidIdTokenError, ExpiredIdTokenError, RevokedIdTokenError,
)

security = HTTPBearer()

async def get_current_user(
    creds: Annotated[HTTPAuthorizationCredentials, Depends(security)],
) -> FirebaseUser:
    try:
        decoded = firebase_auth.verify_id_token(creds.credentials)
    except (InvalidIdTokenError, ExpiredIdTokenError, RevokedIdTokenError):
        raise HTTPException(401, "Invalid token")
    return FirebaseUser(**decoded)
```

- Dependency injection, not ASGI middleware — lets you compose with role checks (`Depends(require_role("ops"))`) and keeps OpenAPI accurate.
- Never hand-decode JWTs.
- Don't set `verify_id_token(check_revoked=True)` per request unless revocation matters (adds a network hop).

## 6. Public routes

Omit `CurrentUser` from the signature. FastAPI routes are public by default — this is intentional.

## 7. Response patterns

**Single resource** — return Pydantic, FastAPI wraps via `response_model`:
```python
return ExceptionPublic.model_validate(doc.to_dict() | {"id": doc.id})
```

**List with count envelope** — always wrap lists with count (enables frontend pagination):
```python
class ExceptionsPublic(BaseModel):
    data: list[ExceptionPublic]
    count: int
```

**Delete** — return `Message`:
```python
return Message(message="Exception deleted")
```

**Auth token** — return `Token(access_token=..., token_type="bearer")`.

**Rules:**
- Never return raw dicts — always Pydantic.
- Never return `DocumentSnapshot` or `DocumentReference` — `.to_dict()` at the boundary.
- Never return the raw user model on public endpoints — use `UserPublic` variants that exclude claims, tokens, internal flags.
- Order list results by `created_at` descending unless a reason says otherwise.

## 8. Status codes

| Code | When | Example detail |
|---|---|---|
| 400 | Invalid input, wrong credentials, inactive user | `"Incorrect email or password"` |
| 401 | Auth token missing / expired / revoked / invalid | `"Invalid token"` |
| 403 | Resource exists but user lacks permission | `"Not enough permissions"` |
| 404 | Resource doesn't exist | `"Exception not found"` |
| 409 | Duplicate resource (conflict) | `"User with this email already exists"` |
| 422 | Pydantic validation failure (automatic) | — |

**Order:** check existence (404) **before** permission (403). This project deliberately returns 403 for "exists but no access" rather than 404 to avoid leaking — consistent with the auth model.

## 9. Security-conscious error messages

Never reveal which half of a compound check failed:

- Login failure: `"Incorrect email or password"` — NEVER `"User not found"` or `"Wrong password"` separately.
- Password recovery: always `"If that email is registered, we sent a recovery link"` — NEVER reveal whether the email exists.
- Password reset with bad token: `"Invalid token"` — NEVER `"User not found"`.

## 10. Error raising

```python
doc = await db.collection("exceptions").document(exception_id).get()
if not doc.exists:
    raise HTTPException(404, "Exception not found")

data = doc.to_dict()
if not current_user.is_superuser and data["owner_id"] != current_user.uid:
    raise HTTPException(403, "Not enough permissions")
```

## 11. Scope of these rules

- Tier 1 FastAPI footprint is small (submit exception, fetch triage result, health, maybe webhook). These rules still apply.
- As Tier 3 adds React dashboard + real CRUD, the checklist in `.claude/rules/new-feature-checklist.md` (when added) picks up from here.
