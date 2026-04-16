"""Impact agent package.

Two-agent pattern (fetcher+formatter) via SequentialAgent. The fetcher calls
tools to retrieve affected shipments, customer profiles, route/hub data, and
compute financial impact; the formatter applies ``output_schema=ImpactResult``
to produce structured output with priority reasoning.

The ``from . import agent`` import is required so ``adk web`` discovers
``root_agent`` -- see ADK discovery contract.
"""

from . import agent

__all__ = ["agent"]
