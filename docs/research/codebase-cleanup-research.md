# Codebase Cleanup Research

## Date
April 16, 2026

## Goal
Determine which cleanup tools apply to this repository and identify the highest-confidence cleanup areas before implementation.

## Web Research Summary

### Knip
- [Knip](https://knip.dev/) is a JavaScript and TypeScript dead-code tool.
- It finds unused files, exports, and dependencies in JS/TS projects.
- It does not apply to this repository because there is no `package.json` or JS/TS application surface.

### Madge
- [Madge](https://github.com/pahen/madge) generates dependency graphs and finds circular dependencies.
- It is also a JavaScript/TypeScript-oriented tool, with support for CSS preprocessors.
- It does not fit this repository because the codebase is Python-first and does not have a JS dependency graph to analyze.

### Vulture
- [Vulture](https://github.com/jendrikseipp/vulture) finds unused Python code by static analysis.
- It reports dead code with confidence scores and supports whitelists for false positives.
- It is the correct dead-code tool for this repository.

### Import Linter
- [Import Linter](https://import-linter.readthedocs.io/en/latest/) enforces import contracts in Python projects.
- It supports layers, forbidden imports, independence, and acyclic-sibling rules.
- It matches this repository's existing architectural checks and is the right tool for dependency-boundary validation.

## Repo Findings

### What is already in place
- Ruff catches unused imports and several style issues.
- Mypy is configured in strict mode.
- Import Linter is already configured in `pyproject.toml` and enforced in pre-commit.
- The repository has no Node/JS toolchain, so JS-only cleanup tools are not useful here.

### High-confidence cleanup targets
- Shared triage enums and envelope types should be centralized.
- Tier 1 runner orchestration is duplicated and can be factored into one helper.
- The impact callback currently hides failures in its post-processing path and should surface them instead of silently falling back.
- Some module docstrings and comments are overly verbose and can be trimmed.

### Deferred or intentional scaffolding
- The memory layer and guardrails module are intentional architectural scaffolding.
- `render_learned_preferences()` is intentionally separate because later agents may inject it into prompts.
- Demo and sprint scaffolding should only be deleted when the roadmap no longer needs it.

## Implementation Direction

- Use Python-native dead-code checks rather than Knip.
- Use Import Linter for dependency-layer checks rather than Madge.
- Prefer shared model modules and small runtime helpers over larger ad hoc duplication.
- Keep compatibility aliases while consolidating types so the refactor stays incremental.
