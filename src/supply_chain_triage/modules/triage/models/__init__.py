"""Public re-exports for the triage module's Pydantic schemas.

Enables the smoke-import acceptance criterion (§17 item #9 in Sprint 0 PRD v2):

    python -c "from supply_chain_triage.modules.triage.models import (
        ExceptionEvent, ClassificationResult, ImpactResult, ShipmentImpact,
        TriageResult, UserContext, CompanyProfile,
    )"
"""

from supply_chain_triage.modules.triage.models.classification import (
    ClassificationResult,
    ExceptionType,
    Severity,
)
from supply_chain_triage.modules.triage.models.company_profile import (
    CompanyProfile,
    CustomerPortfolio,
)
from supply_chain_triage.modules.triage.models.exception_event import (
    ExceptionEvent,
    SourceChannel,
)
from supply_chain_triage.modules.triage.models.financial import FinancialBreakdown
from supply_chain_triage.modules.triage.models.impact import ImpactResult, ShipmentImpact
from supply_chain_triage.modules.triage.models.learned_preferences import (
    render_learned_preferences,
)
from supply_chain_triage.modules.triage.models.route import (
    HubCapacityWindow,
    HubStatus,
    RouteDefinition,
    RouteLeg,
)
from supply_chain_triage.modules.triage.models.triage_result import (
    EscalationPriority,
    TriageResult,
    TriageStatus,
)
from supply_chain_triage.modules.triage.models.user_context import UserContext, WorkingHours

__all__ = [
    "ClassificationResult",
    "CompanyProfile",
    "CustomerPortfolio",
    "EscalationPriority",
    "ExceptionEvent",
    "ExceptionType",
    "FinancialBreakdown",
    "HubCapacityWindow",
    "HubStatus",
    "ImpactResult",
    "RouteDefinition",
    "RouteLeg",
    "Severity",
    "ShipmentImpact",
    "SourceChannel",
    "TriageResult",
    "TriageStatus",
    "UserContext",
    "WorkingHours",
    "render_learned_preferences",
]
