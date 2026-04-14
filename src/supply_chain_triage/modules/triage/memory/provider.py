"""MemoryProvider ABC — portability boundary for agent memory.

Per ADR-002 ("Memory Layer — Supermemory"), this interface exists so the
concrete memory backend (Supermemory today; Firestore-DIY fallback in Sprint 4
Should-Have; possibly Mem0 or Zep later) can be swapped without touching
agent or tool code.

Risk 12 mitigation (Sprint 0 risks.md): every public method takes
``company_id`` as a REQUIRED POSITIONAL argument. Forgetting it must be a
type error at the call site, not a silent cross-tenant data leak.
``docs/research/zettel-supermemory-python-sdk.md`` expands on why.

Architecture-layers compliance: this file lives in ``modules/triage/memory/``
(terminal layer — data in, data out). Imports are allowed to include
``firebase_admin`` / ``google.cloud.firestore`` per the per-file-ignore in
``pyproject.toml``, and the concrete Supermemory SDK will be imported in the
adapter module (not here).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from supply_chain_triage.modules.triage.models.company_profile import CompanyProfile
    from supply_chain_triage.modules.triage.models.exception_event import ExceptionEvent
    from supply_chain_triage.modules.triage.models.user_context import UserContext


class MemoryProvider(ABC):
    """Abstract interface for agent memory.

    All implementations must accept ``company_id`` as a required positional
    argument on every method. This is Risk 12's defense against cross-tenant
    data leaks through forgotten scoping.

    Signatures return our own Pydantic models (never SDK types) to preserve
    the ADR-002 portability goal — a Firestore-DIY fallback must be able to
    fulfill this contract without leaking Supermemory-specific types into
    consuming code.
    """

    @abstractmethod
    async def fetch_user_context(self, user_id: str, company_id: str) -> UserContext:
        """Fetch a user's operator profile.

        Consumed by the Coordinator's ``before_model_callback`` (Sprint 3) to
        render the ``<user_context>`` XML block into the agent prompt.

        Args:
            user_id: Firebase Auth UID.
            company_id: Tenant identifier. REQUIRED — Risk 12.

        Returns:
            Hydrated :class:`UserContext`.

        Raises:
            KeyError: If no profile exists for the ``(user_id, company_id)`` pair.
        """

    @abstractmethod
    async def fetch_company_profile(self, company_id: str) -> CompanyProfile:
        """Fetch the company profile used by Classifier Rule 3 + prompt context.

        Args:
            company_id: Tenant identifier. REQUIRED.

        Returns:
            Hydrated :class:`CompanyProfile`.

        Raises:
            KeyError: If the company is not registered.
        """

    @abstractmethod
    async def lookup_customer_exception_history(
        self,
        customer_id: str,
        company_id: str,
        limit: int = 5,
    ) -> list[dict[str, Any]]:
        """Fetch the most recent exceptions for a customer within a company.

        Consumed by the Impact Agent (Sprint 2) for churn-weight reasoning.

        Args:
            customer_id: Customer identifier within the company.
            company_id: Tenant identifier. REQUIRED.
            limit: Max records to return.

        Returns:
            Recent exception records (most-recent-first). Empty list if none.
        """

    @abstractmethod
    async def lookup_similar_past_exceptions(
        self,
        exception_context: str,
        company_id: str,
        limit: int = 3,
    ) -> list[dict[str, Any]]:
        """Semantic-search for exceptions similar to the current one.

        Consumed by the Impact Agent (Sprint 2) to calibrate severity and
        priority using precedents.

        Args:
            exception_context: Natural-language summary of the current exception.
            company_id: Tenant identifier. REQUIRED.
            limit: Max records to return.

        Returns:
            Similar exception records with similarity score attached. Empty
            list if none pass the minimum-similarity threshold.
        """

    @abstractmethod
    async def store_exception(
        self,
        exception_event: ExceptionEvent,
        company_id: str,
    ) -> str:
        """Persist an exception event + triage outcome for future recall.

        Args:
            exception_event: The raw exception + downstream triage attached.
            company_id: Tenant identifier. REQUIRED.

        Returns:
            Memory ID (backend-specific) for later retrieval.
        """
