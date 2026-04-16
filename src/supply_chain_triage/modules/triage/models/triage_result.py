"""TriageResult — combined output of the full triage pipeline.

``impact`` is ``None`` when the Coordinator applied Rule F (LOW severity skip),
per ``docs/research/Supply-Chain-Agent-Spec-Coordinator.md`` Rule F.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from supply_chain_triage.modules.triage.models.classification import (  # noqa: TC001 — runtime-needed by Pydantic
    ClassificationResult,
)
from supply_chain_triage.modules.triage.models.common_types import (  # noqa: TC001
    EscalationPriority,
    TriageStatus,
)
from supply_chain_triage.modules.triage.models.impact import (  # noqa: TC001 — runtime-needed by Pydantic
    ImpactResult,
)


class TriageResult(BaseModel):
    """Final structured triage result returned to the UI."""

    model_config = ConfigDict(extra="forbid")

    event_id: str
    status: TriageStatus
    coordinator_trace: list[dict[str, Any]] = Field(default_factory=list)
    classification: ClassificationResult | None = None
    impact: ImpactResult | None = None  # None when Rule F applied
    summary: str
    processing_time_ms: int = Field(..., ge=0)
    errors: list[str] = Field(default_factory=list)
    escalation_priority: EscalationPriority | None = None
