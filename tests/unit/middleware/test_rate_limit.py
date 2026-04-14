"""Rate-limit middleware stub tests (CR5 parity with the other 4 middlewares).

Real enforcement lands Sprint 4 — this test exists so Sprint 0 coverage
reporting has something to measure on ``rate_limit.py``, preventing a 0%
baseline from becoming a false alarm at the Tier 2 coverage-gate flip.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from supply_chain_triage.middleware.rate_limit import RateLimitMiddleware


class TestRateLimitMiddlewareIsPassThroughInSprint0:
    def test_stub_does_not_reject_requests(self) -> None:
        # Given: an app wrapped in the stub RateLimitMiddleware
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware)

        @app.get("/ok")
        def ok() -> dict[str, str]:
            return {"status": "ok"}

        client = TestClient(app)

        # When: making 50 rapid requests (would be 429'd under real enforcement)
        responses = [client.get("/ok") for _ in range(50)]

        # Then: all 200 — Sprint 0 stub is pass-through. Real enforcement
        # (token-bucket + Redis backend) lands Sprint 4 per rate_limit.py TODO.
        assert all(r.status_code == 200 for r in responses)
