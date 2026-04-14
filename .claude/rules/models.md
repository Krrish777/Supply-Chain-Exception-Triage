---
description: Pydantic v2 model conventions — inheritance pyramid, field conventions, Firestore-aware patterns, structured-output reliability
paths: ["src/supply_chain_triage/modules/*/models/**", "src/supply_chain_triage/modules/*/agents/*/schemas.py"]
---

# Model rules

Pydantic v2 + Firestore, no ORM. Field discipline for agent I/O, Firestore documents, and FastAPI boundaries. Most of the spirit from the SQLModel pyramid applies; the ORM-specific half (`table=True`, relationships, foreign keys) does not.

## 1. Inheritance pyramid

Every domain entity follows:

```
XxxBase       — shared fields (API input + DB shape share these)
  → XxxCreate — POST body (may add required-on-create fields)
  → XxxUpdate — PATCH body (all fields T | None = None, extra="forbid")
  → XxxPublic — API response (adds id, created_at, updated_at)
```

No `table=True` sibling — Firestore docs are structural, not typed rows. No `XxxInDB` with hashed passwords — Firebase handles auth.

```python
class ExceptionBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    shipment_id: str = Field(min_length=8, max_length=64)
    severity: Severity
    description: str = Field(max_length=2000)

class ExceptionCreate(ExceptionBase):
    pass

class ExceptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severity: Severity | None = None
    description: str | None = Field(default=None, max_length=2000)

class ExceptionPublic(ExceptionBase):
    id: str
    created_at: datetime
    updated_at: datetime
```

## 2. Field conventions

### Document IDs (string, time-sortable)

```python
id: str = Field(default_factory=lambda: str(uuid7()))
```

- **Prefer UUIDv7** (RFC 9562) — time-sortable, `str`. Use a v7-capable lib (`uuid-utils`, `uuid_extensions`) or a shim.
- **ULID acceptable** for legacy reasons.
- **Never** Firestore auto-IDs (not time-ordered), **never** integer auto-increment.

### Timestamps (always tz-aware)

```python
from datetime import UTC, datetime

created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
```

- **Never `datetime.utcnow()`** — deprecated in Python 3.12. Enforced by ruff `DTZ` rules.
- **Never naive `datetime`** — Firestore returns tz-aware on read; mismatch breaks serialization.

### Optional fields (Pydantic v2 syntax)

```python
full_name: str | None = None
full_name: str | None = Field(default=None, max_length=255)  # when constraints needed
```

- **`X | None = None`** — never `Optional[X]`.
- Explicit `None` default — Pydantic v2 requires it for optional fields.
- Only use `Field(default=None, ...)` when you also need `description`, constraints, or `alias`.

### String constraints

```python
shipment_id: str = Field(min_length=8, max_length=64)
notes: str | None = Field(default=None, max_length=2000)
email: EmailStr                              # only when we actually handle email
```

- Enforce **domain caps**, not Firestore caps (1 MiB fields, 1500-byte doc IDs — our domain limits are tighter).
- `EmailStr` requires the `pydantic[email]` extra — only pull in if we have email fields.

### Enums

```python
class Severity(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
```

- Short values — Gemini structured-output reliability drops with long enums.
- Use `StrEnum` (Python 3.11+) for natural JSON serialization.

### Mutable defaults

```python
tags: list[str] = Field(default_factory=list)
meta: dict[str, str] = Field(default_factory=dict)
```

- **Always `default_factory`** for lists/dicts — never `= []` / `= {}`.
- Same rule applies to `datetime` factories above.

## 3. Partial-update pattern

Hand-roll `XxxUpdate` with every field `T | None = None` + `extra="forbid"`. Apply via:

```python
payload = exception_update.model_dump(exclude_unset=True)
await doc_ref.update(payload)
```

- `exclude_unset=True` sends only fields the client actually provided — `None` is preserved only when explicitly set.
- Dynamic `create_model(...)` helpers are tempting but hide the schema from OpenAPI — keep hand-rolled for Tier 1-2.

## 4. Validators (v2 forms)

```python
from pydantic import field_validator, model_validator

class ExceptionCreate(ExceptionBase):
    @field_validator("shipment_id")
    @classmethod
    def _shipment_id_format(cls, v: str) -> str:
        if not v.isalnum():
            raise ValueError("shipment_id must be alphanumeric")
        return v

    @model_validator(mode="after")
    def _consistency(self) -> "ExceptionCreate":
        # cross-field checks after all fields are parsed
        return self
```

- **Never** v1 `@validator` or `root_validator` — both deprecated.
- `mode="after"` when the check needs all fields; `mode="before"` for type coercion.

## 5. Cross-model references

No foreign keys. Agents pass IDs in state; models embed IDs, not objects:

```python
from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..classifier.schemas import Classification

class ImpactInput(BaseModel):
    exception_id: str                       # reference, not embed
    classification: Classification          # embed when small + same turn (re-validate)
```

Pydantic v2 resolves forward refs automatically when `from __future__ import annotations` is present.

## 6. List envelope — generic `Page[T]`

Replace the SQLModel-style per-resource `XxxsPublic`:

```python
class Page[T](BaseModel):
    model_config = ConfigDict(extra="forbid")
    data: list[T]
    count: int
    next_cursor: str | None = None         # Firestore uses cursor pagination (see firestore.md)
```

- PEP 695 generic syntax (Python 3.13 supported).
- `next_cursor` opaque to the client — encode Firestore cursor tokens server-side.
- Place in `modules/<mod>/models/` (shared across resources).

## 7. Placement — agent-private vs module-shared

| Model | Lives in |
|---|---|
| Agent I/O envelopes (`ClassifierInput`, `ClassifierOutput`) | `modules/<mod>/agents/<name>/schemas.py` |
| Domain records used by multiple agents (`ExceptionRecord`, `Shipment`) | `modules/<mod>/models/` |
| `Page[T]`, `Message`, `Token`, other API utility models | `modules/<mod>/models/` (or `core/api_models.py` if cross-module) |

**Promotion rule:** if a second agent imports a model, promote it from `schemas.py` to `modules/<mod>/models/`. Otherwise keep it agent-private.

## 8. Structured-output reliability (Gemini 2.5 Flash)

When a model is passed as `output_schema=` on an `LlmAgent`:

- **Nesting depth ≤ 2 levels.** Reliability drops sharply past that.
- Flat primitives, short enums. Deep `list[BaseModel]` and untagged unions degrade.
- Prefer discriminated unions (`Field(discriminator="kind")`) over untagged unions.

Longer / nested schemas: use the two-agent fetcher+formatter pattern from `.claude/rules/agents.md` §5 instead.

## 9. Boundary `extra` discipline

| Layer | `extra` |
|---|---|
| API input models (`XxxCreate`, `XxxUpdate`) | `"forbid"` — reject unknown fields, clean 422 |
| API response models (`XxxPublic`, `Page[T]`) | `"forbid"` — don't leak internal fields |
| Agent I/O (`ClassifierInput`, `ClassifierOutput`) | `"forbid"` |
| Firestore read adapters in `memory/` | `"ignore"` — tolerate schema drift on the way in; validate explicitly |
| Firestore write adapters in `memory/` | `"forbid"` |

## 10. Utility models

Small non-domain models live in `modules/<mod>/models/` or `core/api_models.py`:

```python
class Message(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str

class Token(BaseModel):                       # rarely used since Firebase mints ID tokens client-side
    model_config = ConfigDict(extra="forbid")
    access_token: str
    token_type: str = "bearer"
```

## 11. Anti-patterns

- `datetime.utcnow()` — banned (use `datetime.now(UTC)`). Enforced by ruff `DTZ`.
- Mutable defaults (`= []`, `= {}`) — always `default_factory`.
- `Optional[X]` — always `X | None`.
- `extra="allow"` at API boundary — forbidden; `"ignore"` only in `memory/` read.
- Methods on models beyond `@field_validator` / `@model_validator` / `@computed_field` — behavior belongs in `tools/` and `utils/`.
- SQLModel `table=True`, `sa_type=...`, `foreign_key=...`, `cascade_delete=...`, `Relationship(...)` — forbidden (wrong framework).
- Pydantic v1 `@validator` / `root_validator` — forbidden (deprecated).
- Deeply nested or wide `list[BaseModel]` as `output_schema` — breaks Gemini Flash.
- Reusing a model for both API input and Firestore write without `extra="forbid"` on both.
