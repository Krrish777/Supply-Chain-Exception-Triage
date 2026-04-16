"""In-memory fake :class:`MemoryProvider` for unit tests.

Satisfies the MemoryProvider contract using plain dicts keyed by
``(company_id, ...)``. Hardens Risk 12 (Supermemory container-tag leak) by
asserting ``company_id`` is provided and non-empty on every call — so a test
accidentally omitting it surfaces immediately, not later via a cross-tenant
false positive.

Usage::

    from tests.fixtures.fake_supermemory import FakeSupermemoryClient

    fake = FakeSupermemoryClient()
    fake.seed_user_context("u_1", "comp_1", user_context_instance)
    ctx = await fake.fetch_user_context("u_1", "comp_1")
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from supply_chain_triage.modules.triage.memory.provider import MemoryProvider

if TYPE_CHECKING:
    from supply_chain_triage.modules.triage.models.company_profile import CompanyProfile
    from supply_chain_triage.modules.triage.models.exception_event import ExceptionEvent
    from supply_chain_triage.modules.triage.models.user_context import UserContext


def _assert_company_id(value: str) -> None:
    if not value:
        raise AssertionError(
            "FakeSupermemoryClient requires a non-empty company_id on every "
            "call (Risk 12 — Supermemory container-tag leak prevention)."
        )


class FakeSupermemoryClient(MemoryProvider):
    """In-process Supermemory stand-in for Sprint 0-3 tests."""

    def __init__(self) -> None:
        self._user_contexts: dict[tuple[str, str], UserContext] = {}
        self._company_profiles: dict[str, CompanyProfile] = {}
        self._customer_history: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._similar_past: dict[str, list[dict[str, Any]]] = {}
        self._stored_exceptions: dict[str, list[ExceptionEvent]] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    # --- Seeding helpers (test-only) ---

    def seed_user_context(
        self,
        user_id: str,
        company_id: str,
        ctx: UserContext,
    ) -> None:
        _assert_company_id(company_id)
        self._user_contexts[(user_id, company_id)] = ctx

    def seed_company_profile(self, company_id: str, profile: CompanyProfile) -> None:
        _assert_company_id(company_id)
        self._company_profiles[company_id] = profile

    def seed_customer_history(
        self,
        customer_id: str,
        company_id: str,
        history: list[dict[str, Any]],
    ) -> None:
        _assert_company_id(company_id)
        self._customer_history[(customer_id, company_id)] = history

    def seed_similar_past(
        self,
        company_id: str,
        records: list[dict[str, Any]],
    ) -> None:
        _assert_company_id(company_id)
        self._similar_past[company_id] = records

    # --- MemoryProvider contract ---

    async def fetch_user_context(self, user_id: str, company_id: str) -> UserContext:
        _assert_company_id(company_id)
        self.calls.append(("fetch_user_context", {"user_id": user_id, "company_id": company_id}))
        try:
            return self._user_contexts[(user_id, company_id)]
        except KeyError as exc:
            raise KeyError(
                f"No seeded UserContext for user_id={user_id!r} company_id={company_id!r}",
            ) from exc

    async def fetch_company_profile(self, company_id: str) -> CompanyProfile:
        _assert_company_id(company_id)
        self.calls.append(("fetch_company_profile", {"company_id": company_id}))
        try:
            return self._company_profiles[company_id]
        except KeyError as exc:
            raise KeyError(
                f"No seeded CompanyProfile for company_id={company_id!r}",
            ) from exc

    async def lookup_customer_exception_history(
        self,
        customer_id: str,
        company_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        _assert_company_id(company_id)
        self.calls.append(
            (
                "lookup_customer_exception_history",
                {
                    "customer_id": customer_id,
                    "company_id": company_id,
                    "limit": limit,
                },
            )
        )
        return list(self._customer_history.get((customer_id, company_id), []))[:limit]

    async def lookup_similar_past_exceptions(
        self,
        exception_context: str,
        company_id: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        _assert_company_id(company_id)
        self.calls.append(
            (
                "lookup_similar_past_exceptions",
                {
                    "exception_context": exception_context,
                    "company_id": company_id,
                    "limit": limit,
                },
            )
        )
        return list(self._similar_past.get(company_id, []))[:limit]

    async def store_exception(
        self,
        exception_event: ExceptionEvent,
        company_id: str,
    ) -> str:
        _assert_company_id(company_id)
        self.calls.append(
            (
                "store_exception",
                {
                    "event_id": exception_event.event_id,
                    "company_id": company_id,
                },
            )
        )
        bucket = self._stored_exceptions.setdefault(company_id, [])
        bucket.append(exception_event)
        return f"fake_memory_{company_id}_{exception_event.event_id}"
