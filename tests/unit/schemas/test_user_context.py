"""Tests for UserContext schema + render_learned_preferences helper
(test-plan §1.9, §1.10, §1.10b)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from supply_chain_triage.modules.triage.models.learned_preferences import (
    render_learned_preferences,
)
from supply_chain_triage.modules.triage.models.user_context import UserContext


def _base_user_context(**overrides: object) -> dict[str, object]:
    base = {
        "user_id": "u_001",
        "company_id": "comp_001",
        "name": "Priya Sharma",
        "email": "priya@nimblefreight.in",
        "role": "Exception Coordinator",
        "experience_years": 6,
        "city": "Pune",
        "state": "Maharashtra",
        "timezone": "Asia/Kolkata",
        "avg_daily_shipments": 45,
        "avg_daily_exceptions": 8,
        "busiest_days": ["Monday", "Thursday"],
        "workload_classification": "heavy",
        "preferred_language": "en-IN",
        "tone": "direct",
        "formality": "semi-formal",
        "notification_channels": ["whatsapp", "email"],
        "working_hours": {"start": "09:00", "end": "19:00"},
        "override_patterns": ["prefer-Trina-Logistics", "skip-carrier-callback-after-7pm"],
        "learned_priorities": {"churn_weight": 0.4, "reputation_weight": 0.3},
    }
    base.update(overrides)
    return base


class TestUserContextPreferredLanguageRequired:
    def test_missing_preferred_language_raises(self) -> None:
        # Given: UserContext dict missing preferred_language
        payload = _base_user_context()
        del payload["preferred_language"]
        # When / Then: ValidationError
        with pytest.raises(ValidationError) as excinfo:
            UserContext.model_validate(payload)
        assert "preferred_language" in str(excinfo.value)


class TestUserContextToMarkdown:
    def test_renders_three_sections(self) -> None:
        # Given: a populated UserContext
        ctx = UserContext.model_validate(_base_user_context())
        # When: .to_markdown() called
        md = ctx.to_markdown()
        # Then: output contains the 3 UserContext section headers
        assert "## Identity" in md
        assert "## Volume & Workload" in md
        assert "## Communication Preferences" in md


class TestRenderLearnedPreferences:
    def test_emits_learned_preferences_header(self) -> None:
        # Given: a UserContext with populated override_patterns + learned_priorities
        ctx = UserContext.model_validate(_base_user_context())
        # When: render_learned_preferences(ctx) called
        md = render_learned_preferences(ctx)
        # Then: output has the section header AND includes the pattern strings
        assert "## Learned Preferences" in md
        assert "prefer-Trina-Logistics" in md
        # And the learned priorities surface somewhere (by key or value)
        assert "churn_weight" in md or "0.4" in md
