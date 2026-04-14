"""Firebase Auth middleware tests (test-plan Area 2, tests 2.1–2.6)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from firebase_admin import auth as firebase_auth

from supply_chain_triage.middleware.firebase_auth import FirebaseAuthMiddleware

if TYPE_CHECKING:
    from pytest_mock import MockerFixture


def _app_with_auth() -> FastAPI:
    app = FastAPI()
    app.add_middleware(
        FirebaseAuthMiddleware,
        public_paths=frozenset({"/health"}),
    )

    @app.get("/protected")
    def protected(request: Request) -> dict[str, object]:
        return {
            "user_id": request.state.user_id,
            "company_id": request.state.company_id,
            "email": getattr(request.state, "email", None),
        }

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


class TestFirebaseAuth:
    def test_valid_jwt_passes(self, mocker: MockerFixture) -> None:
        # Given: mocked verify_id_token returning valid claims including company_id
        mocker.patch.object(
            firebase_auth,
            "verify_id_token",
            return_value={"uid": "u1", "email": "a@b.c", "company_id": "comp_1"},
        )
        client = TestClient(_app_with_auth())
        # When: GET /protected with Bearer token
        resp = client.get("/protected", headers={"Authorization": "Bearer token"})
        # Then: 200 and state attached correctly
        assert resp.status_code == 200
        body = resp.json()
        assert body["user_id"] == "u1"
        assert body["company_id"] == "comp_1"

    def test_expired_token_returns_401(self, mocker: MockerFixture) -> None:
        mocker.patch.object(
            firebase_auth,
            "verify_id_token",
            side_effect=firebase_auth.ExpiredIdTokenError("expired", cause=Exception()),
        )
        client = TestClient(_app_with_auth())
        resp = client.get("/protected", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 401
        assert resp.json() == {"error": "token_expired"}

    def test_tampered_signature_returns_401(self, mocker: MockerFixture) -> None:
        mocker.patch.object(
            firebase_auth,
            "verify_id_token",
            side_effect=firebase_auth.InvalidIdTokenError("bad sig"),
        )
        client = TestClient(_app_with_auth())
        resp = client.get("/protected", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 401
        assert resp.json() == {"error": "invalid_signature"}

    def test_missing_auth_header_returns_401(self) -> None:
        client = TestClient(_app_with_auth())
        resp = client.get("/protected")
        assert resp.status_code == 401
        assert resp.json() == {"error": "missing_credentials"}

    def test_missing_company_claim_returns_403(self, mocker: MockerFixture) -> None:
        mocker.patch.object(
            firebase_auth,
            "verify_id_token",
            return_value={"uid": "u1"},  # no company_id
        )
        client = TestClient(_app_with_auth())
        resp = client.get("/protected", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 403
        assert resp.json() == {"error": "missing_company_claim"}

    def test_generic_valueerror_returns_401(self, mocker: MockerFixture) -> None:
        # Given: verify_id_token raises bare ValueError (covers the except-Exception branch)
        mocker.patch.object(firebase_auth, "verify_id_token", side_effect=ValueError("boom"))
        client = TestClient(_app_with_auth())
        resp = client.get("/protected", headers={"Authorization": "Bearer token"})
        assert resp.status_code == 401
        assert resp.json() == {"error": "invalid_token"}

    def test_public_path_skips_auth(self) -> None:
        # Given: /health is in public_paths
        client = TestClient(_app_with_auth())
        # When: GET /health with no Authorization header
        resp = client.get("/health")
        # Then: 200 (auth not enforced on public paths)
        assert resp.status_code == 200
