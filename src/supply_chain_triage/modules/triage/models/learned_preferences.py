"""Learned-preferences rendering helper.

Produces the ``## Learned Preferences`` section fed into the Coordinator's
``<learned_behaviors>`` XML dynamic block. Separated from :class:`UserContext`
because the vault Coordinator spec has internal drift — see
``docs/research/zettel-vault-coordinator-inconsistency.md``. Keeping this as
a free function (not a UserContext method) makes the split explicit.
"""

from __future__ import annotations

from supply_chain_triage.modules.triage.models.user_context import (  # noqa: TC001 — runtime type in function signature
    UserContext,
)


def render_learned_preferences(user_context: UserContext) -> str:
    """Render learned preferences as markdown for ``<learned_behaviors>`` block.

    Sources from ``user_context.override_patterns`` + ``learned_priorities``.
    Output format mirrors UserContext.to_markdown's section style.
    """
    patterns = user_context.override_patterns
    priorities = user_context.learned_priorities

    patterns_line = ", ".join(patterns) if patterns else "none recorded"

    if priorities:
        priorities_lines = "\n".join(f"  - {k}: {v}" for k, v in priorities.items())
        priorities_block = f"- Preferred priority ordering:\n{priorities_lines}"
    else:
        priorities_block = "- Preferred priority ordering: none learned yet"

    return f"## Learned Preferences\n- Override patterns: {patterns_line}\n{priorities_block}\n"
