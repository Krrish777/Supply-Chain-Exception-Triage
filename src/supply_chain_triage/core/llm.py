"""LLM provider/model resolution for the application.

This is the narrow bridge between env-backed settings and the ADK model object
expected by the agent factories. Gemini stays string-based; Groq is wrapped via
ADK's LiteLLM connector.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from supply_chain_triage.core.config import SecretNotFoundError, get_secret

_DEFAULT_PROVIDER = "gemini"
_DEFAULT_MODEL_ID = "gemini-2.5-flash"


@dataclass(frozen=True, slots=True)
class ResolvedLlmModel:
    """Resolved model object and its human-readable name."""

    provider: str
    model_id: str
    model_name: str
    model: Any


@lru_cache(maxsize=1)
def get_resolved_llm_model() -> ResolvedLlmModel:
    """Resolve the active model from env-backed settings.

    Gemini returns the raw model string expected by ADK. Groq uses ADK's
    LiteLlm connector with the Groq provider prefix so the rest of the codebase
    can stay provider-agnostic.
    """
    provider = os.environ.get("LLM_PROVIDER", _DEFAULT_PROVIDER).strip().lower()
    model_id = os.environ.get("LLM_MODEL_ID", _DEFAULT_MODEL_ID).strip()

    if provider not in {"gemini", "groq"}:
        raise ValueError("LLM_PROVIDER must be 'gemini' or 'groq'")
    if not model_id:
        raise ValueError("LLM_MODEL_ID must not be empty")

    if provider == "gemini":
        return ResolvedLlmModel(
            provider=provider,
            model_id=model_id,
            model_name=model_id,
            model=model_id,
        )

    if provider == "groq":
        _ensure_groq_api_key()
        litellm_model = model_id if model_id.startswith("groq/") else f"groq/{model_id}"

        from google.adk.models.lite_llm import LiteLlm

        return ResolvedLlmModel(
            provider=provider,
            model_id=model_id,
            model_name=litellm_model,
            model=LiteLlm(model=litellm_model),
        )

    raise ValueError(f"Unsupported llm_provider {provider!r}")


def _ensure_groq_api_key() -> None:
    """Export a Groq API key into the env if it is only stored as a secret."""
    if os.environ.get("GROQ_API_KEY"):
        return

    try:
        os.environ["GROQ_API_KEY"] = get_secret("GROQ_API_KEY")
    except SecretNotFoundError as exc:
        raise SecretNotFoundError(
            "GROQ_API_KEY is required when LLM_PROVIDER=groq; set GROQ_API_KEY "
            "or SCT_SECRET__GROQ_API_KEY"
        ) from exc
