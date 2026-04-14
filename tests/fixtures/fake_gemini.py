"""Minimal fake Gemini client for unit tests.

Satisfies the small subset of the Gemini surface that Sprint 1+ agents will
exercise. Keeps tests deterministic and network-free. Not a substitute for
``adk eval`` (which runs against real Gemini) — that lives in ``evals/``.

Sprint 0 ships the fake's shape. Sprint 1 grows the canned-response list as
classifier test cases appear.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeGeminiUsageMetadata:
    """Mirrors ``google.genai.types.UsageMetadata`` minimally."""

    prompt_token_count: int = 0
    candidates_token_count: int = 0


@dataclass
class FakeGeminiResponse:
    """Mirrors ``google.genai.types.GenerateContentResponse`` minimally."""

    text: str = ""
    usage_metadata: FakeGeminiUsageMetadata = field(default_factory=FakeGeminiUsageMetadata)


class FakeGeminiClient:
    """In-memory substitute for the Gemini client.

    Configure responses via ``set_response(prompt_substring, response_text)``.
    ``generate_content(prompt)`` returns the first matching canned response,
    or a default fallback if nothing matches.
    """

    def __init__(self, default_response: str = "(fake gemini default)") -> None:
        self._default_response = default_response
        self._canned: list[tuple[str, str]] = []
        self.calls: list[dict[str, Any]] = []

    def set_response(self, prompt_substring: str, response_text: str) -> None:
        """Register a canned response triggered by a substring of the prompt."""
        self._canned.append((prompt_substring, response_text))

    def generate_content(self, prompt: str, **kwargs: Any) -> FakeGeminiResponse:
        """Return the first canned response whose trigger appears in the prompt."""
        self.calls.append({"prompt": prompt, "kwargs": kwargs})
        for trigger, text in self._canned:
            if trigger in prompt:
                return FakeGeminiResponse(
                    text=text,
                    usage_metadata=FakeGeminiUsageMetadata(
                        prompt_token_count=len(prompt) // 4,
                        candidates_token_count=len(text) // 4,
                    ),
                )
        return FakeGeminiResponse(
            text=self._default_response,
            usage_metadata=FakeGeminiUsageMetadata(
                prompt_token_count=len(prompt) // 4,
                candidates_token_count=len(self._default_response) // 4,
            ),
        )
