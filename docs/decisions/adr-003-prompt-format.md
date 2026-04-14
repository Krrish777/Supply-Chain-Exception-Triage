---
title: "ADR-003: Prompt Format — Hybrid Markdown + XML"
type: deep-dive
domains: [supply-chain, prompt-engineering]
last_updated: 2026-04-10
status: active
confidence: high
sources: ["[[Supply-Chain-Agent-Spec-Coordinator]]", "[[Supply-Chain-Research-Sources]]"]
---

# ADR-003: Prompt Format — Hybrid Markdown + XML Delimiters

## Status
Accepted

## Date
2026-04-10

## Context

Agent system prompts need a format decision that balances:
1. Model comprehension (does Gemini 2.5 Flash parse the structure reliably?)
2. Token cost (XML is verbose; Markdown is compact)
3. Prompt-injection resilience (dynamic content must be clearly delimited)
4. Maintainability (human authors can read it)
5. Separation of static instructions vs dynamic per-request context

This matters because the Coordinator prompt ([[Supply-Chain-Agent-Spec-Coordinator]]) has a large static block (role, architectural rules, delegation rules A–F, output requirements) AND dynamic blocks (user_context, company_context, recent_history, runtime_context) injected via ADK's `before_model_callback`.

## Decision

**Use hybrid Markdown + XML**: Markdown headers (`##`, `###`) for the static hierarchy, XML tags (`<user_context>…</user_context>`) for delimiting dynamically injected content blocks.

Example from Coordinator prompt:

```markdown
# Exception Triage Coordinator

## Role
You are the Exception Triage Coordinator...

## Delegation Rules
### Rule B: Driver Safety Override
...

---

<user_context>
{dynamically injected user markdown}
</user_context>

<runtime_context>
- Current timestamp: {...}
- Active festival: {...}
</runtime_context>
```

## Alternatives Considered

- **Pure Markdown**: ~80% cheaper in tokens than XML (per Roberto Dias Duarte comparison). Rejected for dynamic content because there's no clear "end" delimiter — prompt-injection attacks inside user_context could blend into the static instructions.
- **Pure XML**: Anthropic's historical preference. Rejected because Gemini parses Markdown headers better for hierarchy, and XML on everything is 5x token cost.
- **JSON**: Clean for structured data, bad for instructions + narrative mixed together. Rejected — models interpret JSON as data, not instructions.
- **YAML**: Concise but whitespace-sensitive; fragile when humans edit prompts.

Per the [Delimiter Hypothesis 2026 benchmark](https://systima.ai/blog/delimiter-hypothesis), all three major formats (Markdown, XML, JSON) achieve ~98.4% boundary recognition scores on modern LLMs. **Format rarely matters — except Markdown is the weak link for injection boundaries.** Hybrid gives us Markdown's cheapness for the bulk and XML's robustness for the attack surface.

## Consequences

### Positive
- Compact static prompts (Markdown) — lower token cost on the 80% that rarely changes
- Clear injection boundaries (XML) — prompt-injection defense for the 20% that comes from untrusted memory/user data
- Matches both Anthropic's and Google's published best practices
- Human-readable (critical when debugging agent behavior)
- `before_model_callback` can safely override `system_instruction` without format surprises

### Negative
- Two formats in one file — slightly more cognitive load for new engineers
- Must document the rule: "static = Markdown, dynamic = XML"
- Template-rendering logic must respect XML escaping of dynamic content (no raw `<` or `>` in injected values)

### Neutral
- All prompt files live in `src/supply_chain_triage/agents/prompts/*.md`
- Dynamic blocks are populated via `middleware/context_injection.py` with HTML-safe escaping before insertion
- Future sprints follow the same pattern; ADR is binding

## References

- [The Delimiter Hypothesis — Systima (March 2026)](https://systima.ai/blog/delimiter-hypothesis)
- [Anthropic Claude 4 Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/claude-4-best-practices)
- [Markdown vs XML comparison — Roberto Dias Duarte](https://www.robertodiasduarte.com.br/en/markdown-vs-xml-em-prompts-para-llms-uma-analise-comparativa/)
- [Does Prompt Formatting Have Any Impact on LLM Performance? — arXiv](https://arxiv.org/html/2411.10541v1)
- [One-Stop Developer Guide — OpenAI, Anthropic, Google](https://dev.to/kenangain/one-stop-developer-guide-to-prompt-engineering-across-openai-anthropic-and-google-4bfb)
- [[Supply-Chain-Agent-Spec-Coordinator]] — prompt template using this format
- [[Supply-Chain-Research-Sources]] Topic 3 — format research reading list
