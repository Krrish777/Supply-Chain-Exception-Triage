"""Classifier-private tools — re-exports from the shared lookup module.

The actual implementations live in
``supply_chain_triage.modules.triage.tools.lookup`` so the same tools can be
called from the classifier agent, the impact agent, and the deterministic
hydration callback without code duplication.
"""

from __future__ import annotations

from supply_chain_triage.modules.triage.tools.lookup import (
    get_company_profile,
    get_exception_event,
)

__all__ = ["get_company_profile", "get_exception_event"]
