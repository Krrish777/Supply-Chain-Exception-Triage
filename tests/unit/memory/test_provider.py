"""Tests for MemoryProvider ABC + SupermemoryAdapter stub.

Sprint 0 scope per ADR-002: the interface exists so Sprint 1-3 can mock against
the contract. Real Supermemory integration lands Sprint 4. Risk 12 mitigation:
every public method takes ``company_id`` as a REQUIRED POSITIONAL argument.
Forgetting it is a type error, not a silent cross-tenant leak.
"""

from __future__ import annotations

import inspect

import pytest

from supply_chain_triage.modules.triage.memory.provider import MemoryProvider
from supply_chain_triage.modules.triage.memory.supermemory_adapter import SupermemoryAdapter


class TestMemoryProviderIsAbstract:
    def test_cannot_instantiate_abc_directly(self) -> None:
        # Given: MemoryProvider is the abstract interface
        # When / Then: instantiating raises TypeError (ABC contract)
        with pytest.raises(TypeError, match="MemoryProvider"):
            MemoryProvider()  # type: ignore[abstract]


class TestCompanyIdIsRequiredPositional:
    """Risk 12 mitigation — no method may accept company_id via kwarg-with-default."""

    def test_all_public_methods_require_company_id_positionally(self) -> None:
        # Given: every public (non-dunder) method on MemoryProvider
        methods = {
            name: getattr(MemoryProvider, name)
            for name in dir(MemoryProvider)
            if not name.startswith("_") and callable(getattr(MemoryProvider, name))
        }
        assert methods, "MemoryProvider exposes no public methods — interface too narrow?"
        # When: inspecting each method's signature
        for name, method in methods.items():
            sig = inspect.signature(method)
            params = dict(sig.parameters)
            assert "company_id" in params, (
                f"MemoryProvider.{name} is missing company_id — Risk 12 requires "
                f"company_id on every memory-facing method."
            )
            param = params["company_id"]
            # Then: company_id has NO default (forces caller to pass it)
            assert param.default is inspect.Parameter.empty, (
                f"MemoryProvider.{name}.company_id must be a REQUIRED parameter "
                f"(no default). Found default: {param.default!r}."
            )


class TestSupermemoryAdapterStub:
    """Sprint 0 adapter is a skeleton. Real methods land Sprint 4."""

    def test_adapter_is_a_memory_provider(self) -> None:
        # Given: SupermemoryAdapter class
        # When / Then: it subclasses MemoryProvider
        assert issubclass(SupermemoryAdapter, MemoryProvider)

    def test_adapter_can_be_instantiated(self) -> None:
        # Given: constructor with no required args (API key read from Settings at call time)
        adapter = SupermemoryAdapter()
        # Then: instance is a MemoryProvider
        assert isinstance(adapter, MemoryProvider)

    async def test_stubbed_methods_raise_not_implemented(self) -> None:
        # Given: an adapter instance
        adapter = SupermemoryAdapter()
        # When: awaiting a method
        # Then: NotImplementedError with a message that points at Sprint 4
        with pytest.raises(NotImplementedError, match="sprint-4"):
            await adapter.fetch_user_context(user_id="u_1", company_id="comp_1")
        with pytest.raises(NotImplementedError, match="sprint-4"):
            await adapter.fetch_company_profile(company_id="comp_1")
