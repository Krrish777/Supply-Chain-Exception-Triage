"""Unit tests for env-driven LLM resolution."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

from supply_chain_triage.core.config import get_settings
from supply_chain_triage.core.llm import get_resolved_llm_model


class TestResolvedLlmModel:
    def test_defaults_to_gemini_string_model(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GCP_PROJECT_ID", "sct-test-project")
        monkeypatch.setenv("FIREBASE_PROJECT_ID", "sct-test-firebase")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:3000"]')
        get_settings.cache_clear()
        get_resolved_llm_model.cache_clear()

        resolved = get_resolved_llm_model()

        assert resolved.provider == "gemini"
        assert resolved.model_id == "gemini-2.5-flash"
        assert resolved.model_name == "gemini-2.5-flash"
        assert resolved.model == "gemini-2.5-flash"

    def test_groq_uses_litellm_wrapper_and_exports_key(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("GCP_PROJECT_ID", "sct-test-project")
        monkeypatch.setenv("FIREBASE_PROJECT_ID", "sct-test-firebase")
        monkeypatch.setenv("CORS_ALLOWED_ORIGINS", '["http://localhost:3000"]')
        monkeypatch.setenv("LLM_PROVIDER", "groq")
        monkeypatch.setenv("LLM_MODEL_ID", "openai/gpt-oss-20b")
        monkeypatch.setenv("SCT_SECRET__GROQ_API_KEY", "test-groq-key")
        monkeypatch.delenv("GROQ_API_KEY", raising=False)
        get_settings.cache_clear()
        get_resolved_llm_model.cache_clear()

        resolved = get_resolved_llm_model()

        assert resolved.provider == "groq"
        assert resolved.model_id == "openai/gpt-oss-20b"
        assert resolved.model_name == "groq/openai/gpt-oss-20b"
        assert resolved.model.__class__.__name__ == "LiteLlm"
        assert os.environ["GROQ_API_KEY"] == "test-groq-key"
