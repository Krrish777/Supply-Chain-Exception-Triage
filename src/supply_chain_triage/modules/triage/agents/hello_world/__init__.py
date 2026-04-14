"""Hello-world agent package.

The `from . import agent` import is required so `adk web` discovers
`root_agent` on this package — see .claude/rules/agents.md §11 + ADK
discovery contract (https://google.github.io/adk-docs/get-started/quickstart/).
"""

from . import agent

__all__ = ["agent"]
