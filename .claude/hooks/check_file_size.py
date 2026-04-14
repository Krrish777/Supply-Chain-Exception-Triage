#!/usr/bin/env python3
"""Enforce per-path file-size limits from .claude/rules/code-quality.md.

Invoked as a pre-commit hook: receives changed file paths as argv, exits
non-zero when any file exceeds its bucket limit. Patterns ordered most-specific
first; first match wins.

Limits are soft caps — the rule file calls them advisories — but at commit time
they become binding. Override a specific file by adding a comment on line 1
containing `# size-override: <reason>` (audited in review, grep-able).
"""

from __future__ import annotations

import sys
from fnmatch import fnmatch
from pathlib import Path

# (glob, limit) pairs — first match wins. Keep in sync with
# .claude/rules/code-quality.md §1.
LIMITS: tuple[tuple[str, int], ...] = (
    ("src/supply_chain_triage/modules/*/agents/*/agent.py", 150),
    ("src/supply_chain_triage/modules/*/agents/*/schemas.py", 100),
    ("src/supply_chain_triage/modules/*/agents/*/tools.py", 200),
    ("src/supply_chain_triage/modules/*/agents/*/prompts/*.md", 500),
    ("src/supply_chain_triage/modules/*/tools/**/*.py", 300),
    ("src/supply_chain_triage/modules/*/memory/**/*.py", 200),
    ("src/supply_chain_triage/modules/*/models/**/*.py", 200),
    ("src/supply_chain_triage/modules/*/guardrails/**/*.py", 150),
    ("src/supply_chain_triage/runners/**/*.py", 200),
    ("src/supply_chain_triage/middleware/**/*.py", 150),
    ("src/supply_chain_triage/core/**/*.py", 150),
    # Canonical logging entry point — architecture-layers.md §2 narrow exception.
    # Intentionally the single home for processors + handlers + helpers. Higher
    # cap than the rest of utils/ because splitting fragments the one-file intent.
    ("src/supply_chain_triage/utils/logging.py", 500),
    ("src/supply_chain_triage/utils/**/*.py", 200),
    # Catch-all for any other project Python / markdown.
    ("src/**/*.py", 300),
    ("tests/**/*.py", 400),
    ("docs/sessions/*.md", 400),
)

OVERRIDE_MARKER = "size-override:"


def limit_for(path: str) -> int | None:
    """Return the line-count limit for a path, or None if no rule applies."""
    norm = path.replace("\\", "/").lstrip("./")
    for pattern, limit in LIMITS:
        if fnmatch(norm, pattern):
            return limit
    return None


def has_override(path: Path) -> bool:
    """Check whether line 1 carries a size-override marker."""
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            first = f.readline()
    except OSError:
        return False
    return OVERRIDE_MARKER in first


def count_lines(path: Path) -> int:
    """Count newline-delimited lines in the file."""
    try:
        with path.open("rb") as f:
            return sum(1 for _ in f)
    except OSError:
        return 0


def main(argv: list[str]) -> int:
    violations: list[str] = []
    for raw in argv[1:]:
        path = Path(raw)
        if not path.is_file():
            continue
        limit = limit_for(raw)
        if limit is None:
            continue
        if has_override(path):
            continue
        n = count_lines(path)
        if n > limit:
            violations.append(f"  {raw}: {n} lines > {limit}")

    if violations:
        sys.stderr.write(
            "[file-size-hook] The following files exceed their limits from "
            ".claude/rules/code-quality.md:\n"
            + "\n".join(violations)
            + "\n\nEither split the file, or add `# size-override: <reason>` "
            "on line 1 to opt out.\n"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
