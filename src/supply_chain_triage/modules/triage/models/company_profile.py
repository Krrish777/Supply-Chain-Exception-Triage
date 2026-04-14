"""CompanyProfile — company metadata, required by Classifier severity validator.

``avg_daily_revenue_inr`` is REQUIRED for Classifier Rule 3 (5% relative
revenue threshold → HIGH severity). See
``docs/research/Supply-Chain-Agent-Spec-Classifier.md`` §200-209.

``.to_markdown()`` emits the ``## Business Context`` section for the
Coordinator's ``<company_context>`` XML dynamic block.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class CustomerPortfolio(BaseModel):
    """Customer mix + top customers. Nested inside CompanyProfile."""

    model_config = ConfigDict(extra="forbid")
    d2c_percentage: float = Field(..., ge=0.0, le=1.0)
    b2b_percentage: float = Field(..., ge=0.0, le=1.0)
    b2b_enterprise_percentage: float = Field(..., ge=0.0, le=1.0)
    top_customers: list[str] = Field(default_factory=list)


class CompanyProfile(BaseModel):
    """Company profile stored in Firestore + Supermemory."""

    model_config = ConfigDict(extra="forbid")

    company_id: str = Field(..., min_length=1)
    name: str
    profile_summary: str

    num_trucks: int = Field(..., ge=0)
    num_employees: int = Field(..., ge=0)
    regions_of_operation: list[str] = Field(default_factory=list)
    carriers: list[str] = Field(default_factory=list)

    customer_portfolio: CustomerPortfolio

    avg_daily_revenue_inr: int = Field(
        ...,
        ge=0,
        description="Daily revenue in INR — REQUIRED for Classifier Rule 3 severity validator",
    )

    active: bool = True

    def to_markdown(self) -> str:
        """Render the ``## Business Context`` section for ``<company_context>``."""
        portfolio = self.customer_portfolio
        portfolio_line = (
            f"D2C {int(portfolio.d2c_percentage * 100)}% / "
            f"B2B {int(portfolio.b2b_percentage * 100)}% / "
            f"B2B-ent {int(portfolio.b2b_enterprise_percentage * 100)}%"
        )
        top = ", ".join(portfolio.top_customers) or "n/a"
        regions = ", ".join(self.regions_of_operation) or "n/a"
        carriers = ", ".join(self.carriers) or "n/a"
        return (
            f"## Business Context\n"
            f"- Company: {self.name}\n"
            f"- Size: {self.num_trucks} trucks, {self.num_employees} employees\n"
            f"- Regions of operation: {regions}\n"
            f"- Carrier network: {carriers}\n"
            f"- Customer portfolio: {portfolio_line}\n"
            f"- Top priority customers: {top}\n"
            f"- Avg daily revenue: ₹{self.avg_daily_revenue_inr}  "
            f"# Used by Classifier Rule 3 (5% relative threshold)\n"
        )
