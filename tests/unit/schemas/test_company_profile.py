"""Tests for CompanyProfile schema (test-plan §1.11, §1.12, §1.12b)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from supply_chain_triage.modules.triage.models.company_profile import CompanyProfile


def _base_company(**overrides: object) -> dict[str, object]:
    base = {
        "company_id": "comp_001",
        "name": "NimbleFreight",
        "profile_summary": "Small Pune-based 3PL, 22 trucks, NH-48 corridor focus.",
        "num_trucks": 22,
        "num_employees": 35,
        "regions_of_operation": ["Maharashtra", "Gujarat", "Karnataka"],
        "carriers": ["Delhivery", "BlueDart"],
        "customer_portfolio": {
            "d2c_percentage": 0.3,
            "b2b_percentage": 0.6,
            "b2b_enterprise_percentage": 0.1,
            "top_customers": ["Trina Logistics", "ACE Industries"],
        },
        "avg_daily_revenue_inr": 180_000,
        "active": True,
    }
    base.update(overrides)
    return base


class TestCompanyProfileAvgDailyRevenueRequired:
    def test_missing_avg_daily_revenue_inr_raises(self) -> None:
        # Given: CompanyProfile dict missing avg_daily_revenue_inr
        payload = _base_company()
        del payload["avg_daily_revenue_inr"]
        # When / Then: ValidationError
        # (Required per Classifier Rule 3 — vault Classifier spec lines 200-209.)
        with pytest.raises(ValidationError) as excinfo:
            CompanyProfile.model_validate(payload)
        assert "avg_daily_revenue_inr" in str(excinfo.value)


class TestCompanyProfileRoundTrip:
    def test_customer_portfolio_preserved(self) -> None:
        # Given: CompanyProfile with nested customer_portfolio
        original = _base_company()
        parsed = CompanyProfile.model_validate(original)
        # When: round-tripped
        dumped = parsed.model_dump(mode="json")
        reparsed = CompanyProfile.model_validate(dumped)
        # Then: nested structure preserved
        assert reparsed.customer_portfolio.top_customers == [
            "Trina Logistics",
            "ACE Industries",
        ]
        assert reparsed.customer_portfolio.d2c_percentage == 0.3


class TestCompanyProfileToMarkdown:
    def test_emits_business_context_with_revenue(self) -> None:
        # Given: populated CompanyProfile (NimbleFreight, 22 trucks, revenue 180k)
        profile = CompanyProfile.model_validate(_base_company())
        # When: .to_markdown() called
        md = profile.to_markdown()
        # Then: output has the Business Context header AND name, trucks, revenue
        assert "## Business Context" in md
        assert "NimbleFreight" in md
        assert "22" in md  # num_trucks visible
        # Revenue renders in any human form: 180000 | 180,000 | 180_000
        assert any(form in md for form in ("180000", "180,000", "180_000"))
