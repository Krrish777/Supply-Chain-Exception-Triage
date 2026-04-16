"""Classifier agent package.

Two-agent pattern (fetcher+formatter) via SequentialAgent. The fetcher calls
tools to retrieve exception + company context from Firestore; the formatter
applies ``output_schema=ClassificationResult`` to produce structured output.

The ``from . import agent`` import is required so ``adk web`` discovers
``root_agent`` — see ADK discovery contract.
"""

from . import agent

__all__ = ["agent"]
