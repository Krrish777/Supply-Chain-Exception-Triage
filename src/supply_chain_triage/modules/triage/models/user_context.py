"""UserContext — user profile fetched from Supermemory, rendered for prompt.

The ``.to_markdown()`` method emits THREE sections (Identity, Volume & Workload,
Communication Preferences) — these are the contents of the Coordinator's
``<user_context>`` XML dynamic block. Business Context lives in
``CompanyProfile.to_markdown()``; Learned Preferences lives in
``render_learned_preferences()`` in ``learned_preferences.py``. See
``docs/research/zettel-vault-coordinator-inconsistency.md``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class WorkingHours(BaseModel):
    """HH:MM start/end bounds for a user's working day."""

    model_config = ConfigDict(extra="forbid")
    start: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end: str = Field(..., pattern=r"^\d{2}:\d{2}$")


class UserContext(BaseModel):
    """Exception Coordinator persona + preferences."""

    model_config = ConfigDict(extra="forbid")

    user_id: str
    company_id: str

    # Identity
    name: str
    email: str
    role: str
    experience_years: int = Field(..., ge=0)
    city: str
    state: str
    timezone: str

    # Volume & workload
    avg_daily_shipments: int = Field(..., ge=0)
    avg_daily_exceptions: int = Field(..., ge=0)
    busiest_days: list[str] = Field(default_factory=list)
    workload_classification: str

    # Communication preferences
    preferred_language: str  # REQUIRED per Test 1.9
    tone: str
    formality: str
    notification_channels: list[str] = Field(default_factory=list)

    working_hours: WorkingHours

    # Learned preferences (populated over time by Supermemory).
    # CR8: dict[str, float] — the Impact agent reads these as numeric weights
    # (value_weight, churn_weight, reputation_weight). `Any` previously let
    # garbage through that would surface as prompt-injection-adjacent bugs
    # downstream.
    override_patterns: list[str] = Field(default_factory=list)
    learned_priorities: dict[str, float] = Field(default_factory=dict)

    def to_markdown(self) -> str:
        """Render UserContext as the 3-section markdown block for prompt injection."""
        return (
            f"## Identity\n"
            f"- Name: {self.name}\n"
            f"- Role: {self.role}\n"
            f"- Experience: {self.experience_years} years in logistics\n"
            f"- Location: {self.city}, {self.state}\n"
            f"- Working hours: {self.timezone}, "
            f"{self.working_hours.start}-{self.working_hours.end}\n\n"
            f"## Volume & Workload\n"
            f"- Daily volume: {self.avg_daily_shipments} shipments handled\n"
            f"- Exception rate: {self.avg_daily_exceptions} per day\n"
            f"- Peak days: {', '.join(self.busiest_days) or 'n/a'}\n"
            f"- Burden level: {self.workload_classification}\n\n"
            f"## Communication Preferences\n"
            f"- Preferred language: {self.preferred_language}\n"
            f"- Communication style: {self.tone}\n"
            f"- Formality: {self.formality}\n"
            f"- Notification channels: "
            f"{', '.join(self.notification_channels) or 'n/a'}\n"
        )
