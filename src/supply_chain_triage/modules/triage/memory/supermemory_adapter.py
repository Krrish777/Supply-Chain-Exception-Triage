"""Supermemory-backed :class:`MemoryProvider` implementation — Sprint 0 stub.

Real implementation lands Sprint 4 Should-Have per the vault sprint plan
(``docs/research/Supply-Chain-Sprint-Plan-Spiral-SDLC.md``). The Sprint 0
scaffold exists so Sprint 1-3 tests can mock against the concrete type
instead of only the ABC, and so the module path is stable.

Design intent (see ``docs/research/zettel-supermemory-python-sdk.md``):

- Constructor takes no args. API key is read from ``core.config.get_secret``
  at call time, not at construction time, to keep the container startup fast
  and avoid reading Secret Manager on every test.
- Every call passes ``container_tags=[company_id]`` to the Supermemory SDK.
  The caller never builds container tags themselves — the adapter owns that
  contract. Per-method ``company_id`` required-positional arguments (from
  :class:`MemoryProvider`) enforce this at the type-check boundary.
- Sprint 0 methods raise ``NotImplementedError`` with a clear
  ``TODO(sprint-4)`` message so anyone running against the real adapter
  before Sprint 4 integration gets a loud, actionable failure.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from supply_chain_triage.modules.triage.memory.provider import MemoryProvider

if TYPE_CHECKING:
    from supply_chain_triage.modules.triage.models.company_profile import CompanyProfile
    from supply_chain_triage.modules.triage.models.exception_event import ExceptionEvent
    from supply_chain_triage.modules.triage.models.user_context import UserContext


_SPRINT4 = "sprint-4: real Supermemory integration pending"


class SupermemoryAdapter(MemoryProvider):
    """Skeleton that will wrap the Supermemory Python SDK in Sprint 4.

    Until then, every call raises :class:`NotImplementedError` pointing to
    Sprint 4. Tests that need memory behavior in Sprints 1-3 use
    :class:`tests.fixtures.fake_supermemory.FakeSupermemoryClient` instead —
    same ABC, test-configurable behavior.
    """

    async def fetch_user_context(self, user_id: str, company_id: str) -> UserContext:
        """See :meth:`MemoryProvider.fetch_user_context`."""
        raise NotImplementedError(_SPRINT4)

    async def fetch_company_profile(self, company_id: str) -> CompanyProfile:
        """See :meth:`MemoryProvider.fetch_company_profile`."""
        raise NotImplementedError(_SPRINT4)

    async def lookup_customer_exception_history(
        self,
        customer_id: str,
        company_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """See :meth:`MemoryProvider.lookup_customer_exception_history`."""
        raise NotImplementedError(_SPRINT4)

    async def lookup_similar_past_exceptions(
        self,
        exception_context: str,
        company_id: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """See :meth:`MemoryProvider.lookup_similar_past_exceptions`."""
        raise NotImplementedError(_SPRINT4)

    async def store_exception(
        self,
        exception_event: ExceptionEvent,
        company_id: str,
    ) -> str:
        """See :meth:`MemoryProvider.store_exception`."""
        raise NotImplementedError(_SPRINT4)
