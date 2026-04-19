"""ADK discovery shim — exposes the triage pipeline for `adk web`.

The real factory + callbacks live in
``supply_chain_triage.modules.triage.pipeline``. This file exists purely so
`adk web src/.../modules/triage/agents` discovers the full pipeline as a
sibling of `classifier` and `impact`, matching the Makefile `dev` target.

Do NOT add orchestration logic here — it belongs in ``pipeline/``.
"""

from __future__ import annotations

from supply_chain_triage.modules.triage.pipeline import create_triage_pipeline

# ADK discovery — `adk web` looks for `root_agent` at module level.
root_agent = create_triage_pipeline()
