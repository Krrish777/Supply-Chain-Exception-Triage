---
description: Firestore client lifecycle, data model, query patterns, emulator setup
paths: ["src/supply_chain_triage/modules/*/memory/**", "src/supply_chain_triage/modules/*/tools/**", "src/supply_chain_triage/middleware/**"]
---

# Firestore rules

Firestore is accessed only from `memory/`, `tools/`, and `middleware/`. Agents do not import firestore — see `.claude/rules/imports.md`.

## 1. Client choice

Use `google.cloud.firestore.AsyncClient`. Do **not** use `firebase_admin.firestore.client()` — it returns a sync client that blocks the ASGI event loop.

```python
from google.cloud.firestore import AsyncClient
```

`firebase_admin` is still used for **auth** (`firebase_admin.auth.verify_id_token`) — just not for Firestore.

## 2. Client lifecycle

One `AsyncClient` per process, created in FastAPI's `lifespan` context, attached to `app.state.db`:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.db = AsyncClient()
    try:
        yield
    finally:
        app.state.db.close()

app = FastAPI(lifespan=lifespan)
```

Dependency:
```python
async def get_firestore(request: Request) -> AsyncClient:
    return request.app.state.db

FirestoreDep = Annotated[AsyncClient, Depends(get_firestore)]
```

**Never** create a client per request. gRPC channel leaks compound fast.

## 3. Data model

```
exceptions/{exceptionId}                    # top-level
    triage_results/{resultId}               # subcollection — classification + impact + resolution
    events/{eventId}                        # subcollection — audit log
users/{uid}                                 # top-level
adk_sessions/{sessionId}                    # ADK FirestoreSessionService
```

- Main entities at root (easier security rules, cheaper queries).
- Child / audit data as subcollections (avoids 1MB doc cap, scoped queries).
- Use `db.collection_group("triage_results")` for cross-exception analytics.

## 4. Document IDs

Use ULIDs (time-sortable) for exceptions, not auto-IDs. Helps range queries, pagination cursors, and debugging.

```python
from ulid import ULID
exception_id = str(ULID())
```

## 5. Query patterns

**Cursor-based pagination only** — never `offset=N` (still billed for skipped docs):

```python
query = db.collection("exceptions").order_by("created_at", direction="DESCENDING").limit(50)
if cursor:
    snapshot = await db.collection("exceptions").document(cursor).get()
    query = query.start_after(snapshot)
docs = [doc async for doc in query.stream()]
```

**Field masks / `select()`** when you don't need the full doc:
```python
doc_ref.get(field_paths=["status", "severity", "created_at"])
```

**Batched writes** up to 500 ops via `db.batch()`.

**Transactions** (`@firestore.async_transactional`) only when read-modify-write atomicity is needed — they retry on contention and cost more.

## 6. Storage discipline

- **No blobs in Firestore.** Images, PDFs, CSVs → GCS. Store `gs://` URI in the doc.
- **No real-time `on_snapshot` listeners server-side** — continuous reads, no bound.
- **Composite indexes** declared in `firestore.indexes.json`, deployed via `firebase deploy --only firestore:indexes`. Don't create them by hand in the console.

## 7. ADK session / memory persistence

Use ADK's `FirestoreSessionService` (and `FirestoreMemoryService` when Tier 2 adds durable memory). Do not roll your own. Wire in a `modules/*/memory/` adapter:

```python
# modules/triage/memory/session.py
from google.adk.sessions import FirestoreSessionService

def build_session_service(db: AsyncClient) -> FirestoreSessionService:
    return FirestoreSessionService(db=db, collection="adk_sessions")
```

## 8. Security rules

Admin/server SDKs **bypass security rules**. Since Tier 1-2 servers are the only Firestore client, rules serve as defense-in-depth only:

- Default rule: deny-all.
- Open narrowly if/when Tier 3 frontend reads Firestore directly.
- File: `firestore.rules` (not yet created; add when frontend needs it).

## 9. Emulator for tests

Integration tests set environment before the client is constructed:

```python
os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
os.environ["GCLOUD_PROJECT"] = "sct-test"
```

Session-scoped pytest fixture spawns `firebase emulators:start --only firestore`, clears state between tests via emulator REST:
```
DELETE http://localhost:8080/emulator/v1/projects/{project}/databases/(default)/documents
```

**`mockfirestore`** only for unit tests of pure tool logic. It doesn't emulate indexes, transactions, or security rules accurately — queries behave differently from production.

## 10. Free-tier cost awareness

Daily free limits per project: 50k reads / 20k writes / 20k deletes. Optimizations:
- Cursor pagination (see §5).
- Field masks when possible.
- Per-turn cache in `tool_context.state` (see `.claude/rules/tools.md` §6).
- Avoid unbounded `list_documents` / fan-out queries inside agent loops.

## 11. Anti-patterns

- Per-request client construction.
- Returning `DocumentSnapshot` / `DocumentReference` from tools (not JSON-serializable, leaks SDK into LLM context).
- Storing binary content in docs.
- Offset pagination.
- Real-time listeners in server code.
- Calling `firebase_admin.initialize_app()` per request (once per process in `lifespan`).
