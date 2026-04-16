"""Classifier agent I/O schemas.

``TriageAgentInput`` is the thin envelope sent by the test endpoint.
``ClassificationResult`` lives in ``modules/triage/models/classification.py``
(shared across agents) and is reused here as the formatter's ``output_schema``.
"""

from __future__ import annotations

from supply_chain_triage.modules.triage.models.api_envelopes import TriageAgentInput

ClassifierInput = TriageAgentInput
