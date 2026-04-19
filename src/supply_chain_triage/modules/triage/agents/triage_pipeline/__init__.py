"""ADK discovery package for the full triage pipeline.

Thin shim so `adk web src/.../modules/triage/agents` picks up the
SequentialAgent alongside the standalone `classifier` and `impact`
agent folders. The real factory lives in
``supply_chain_triage.modules.triage.pipeline``.
"""
