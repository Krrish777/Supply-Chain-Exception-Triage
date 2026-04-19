"""Unit tests for supply_chain_triage.core.config.

Strict TDD (ADR-005): these tests are written BEFORE the implementation.
They should fail on first run (ImportError / NotImplementedError / AssertionError)
and then pass after ``core/config.py`` is implemented.
"""

from __future__ import annotations

import pytest

from supply_chain_triage.core.config import (
    SecretNotFoundError,
    get_secret,
    get_settings,
)


class TestSecretNotFoundError:
    def test_inherits_from_exception(self) -> None:
        # Given: SecretNotFoundError type
        # When: checking its MRO
        # Then: it is a subclass of Exception (so callers can catch it normally)
        assert issubclass(SecretNotFoundError, Exception)


class TestGetSecret:
    def test_reads_from_env_first(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Given: an environment variable set for a secret key
        monkeypatch.setenv("SCT_SECRET__GEMINI_API_KEY", "local-dev-value")
        # When: get_secret is called for that key
        value = get_secret("GEMINI_API_KEY")
        # Then: it returns the env-var value (local-dev fallback wins; no GCP call)
        assert value == "local-dev-value"

    def test_raises_when_not_found_anywhere(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Given: no env var set AND no GCP Secret Manager access (emulator-style isolation)
        monkeypatch.delenv("SCT_SECRET__MISSING_KEY", raising=False)
        monkeypatch.setenv("SCT_DISABLE_SECRET_MANAGER", "1")
        # When: get_secret is called for an unset key
        # Then: SecretNotFoundError is raised naming the key
        with pytest.raises(SecretNotFoundError, match="MISSING_KEY"):
            get_secret("MISSING_KEY")


class TestSettings:
    def test_constructs_with_required_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Given: required env vars are set
        monkeypatch.setenv("GCP_PROJECT_ID", "sct-test-project")
        monkeypatch.setenv("FIREBASE_PROJECT_ID", "sct-test-firebase")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:3000"]')
        # Reset cache so the monkeypatched env is used
        get_settings.cache_clear()
        # When: Settings is constructed via get_settings()
        settings = get_settings()
        # Then: fields reflect the env
        assert settings.gcp_project_id == "sct-test-project"
        assert settings.firebase_project_id == "sct-test-firebase"
        assert settings.cors_allowed_origins == ["http://localhost:3000"]
        assert settings.llm_provider == "gemini"
        assert settings.llm_model_id == "gemini-2.5-flash"

    def test_reads_llm_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GCP_PROJECT_ID", "sct-test-project")
        monkeypatch.setenv("FIREBASE_PROJECT_ID", "sct-test-firebase")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:3000"]')
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.setenv("LLM_MODEL_ID", "openai/gpt-oss-20b")
        get_settings.cache_clear()

        settings = get_settings()

        assert settings.llm_provider == "groq"
        assert settings.llm_model_id == "openai/gpt-oss-20b"

    def test_get_settings_is_cached(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Given: env set and settings obtained once
        monkeypatch.setenv("GCP_PROJECT_ID", "proj-1")
        monkeypatch.setenv("FIREBASE_PROJECT_ID", "fb-1")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:3000"]')
        get_settings.cache_clear()
        a = get_settings()
        # When: get_settings is called again
        b = get_settings()
        # Then: the same instance is returned (lru_cache)
        assert a is b
