"""Pipeline-level constants for deterministic rule engine.

Rule B safety keywords (pre-LLM gate) and the placeholder ClassificationResult
written when Rule B short-circuits the pipeline.

Kept separate from ``classifier/agent.py``'s post-LLM keyword set: Rule B
fires before any Gemini call; the classifier's own keyword scan runs after
the formatter produces output. Different purposes, different lists.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Rule B — safety keyword list
# ---------------------------------------------------------------------------

# Tier 1 scope: English + Hindi-transliterated (Hinglish).
# Native Devanagari Hindi deferred to Tier 2 (needs Unicode-aware tokenization).
# Matching: NFKC-normalised, casefolded substring — see callbacks._rule_b_safety_check.

_RULE_B_SAFETY_KEYWORDS_EN: frozenset[str] = frozenset(
    {
        "accident",
        "injury",
        "injured",
        "death",
        "killed",
        "fatality",
        "fire",
        "spill",
        "hazmat",
        "hazardous",
        "medical emergency",
        "collapsed",
        "hospitalized",
        "chemical leak",
        "tanker explosion",
        "overturned",
    }
)

_RULE_B_SAFETY_KEYWORDS_HI: frozenset[str] = frozenset(
    {
        "durghatna",
        "chot",
        "maut",
        "marne",
        "aag",
        "jaan ka khatra",
        "hospital",
        "bimari",
        "zakhmi",
        "khatarnak",
    }
)

_RULE_B_SAFETY_KEYWORDS: frozenset[str] = _RULE_B_SAFETY_KEYWORDS_EN | _RULE_B_SAFETY_KEYWORDS_HI

# ---------------------------------------------------------------------------
# Rule B — safety placeholder ClassificationResult
# ---------------------------------------------------------------------------

# Written to triage:classification when Rule B short-circuits so downstream
# runner assembly (which always reads this key) never gets a KeyError.
# matched_terms is populated at call-time by the callback.
_SAFETY_PLACEHOLDER_BASE: dict[str, Any] = {
    "exception_type": "safety_incident",
    "subtype": "safety_keyword_match",
    "severity": "CRITICAL",
    "urgency_hours": 0,
    "confidence": 1.0,
    "key_facts": [{"key": "trigger", "value": "safety_keyword_match"}],
    "reasoning": "Rule B keyword detection — short-circuited before classifier.",
    "requires_human_approval": True,
    "tools_used": [],
    "safety_escalation": {
        "trigger_type": "keyword_detection",
        "matched_terms": [],  # populated at call-time
        "escalation_reason": "Rule B short-circuit — pre-LLM safety gate",
    },
}
