#!/usr/bin/env python3
"""PreToolUse hook: reject Edit/Write to paths outside the placement allowlist.

The allowlist mirrors the placement table in `.claude/rules/placement.md`.
Update this file and that table together; they are the same contract.

Exit codes:
    0 — path is allowed (or not a file write)
    2 — path violates placement rule (stderr surfaced to Claude)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path, PurePosixPath

ALLOWLIST: tuple[str, ...] = (
    # src — core / middleware / runners / utils
    "src/supply_chain_triage/core/**/*.py",
    "src/supply_chain_triage/middleware/**/*.py",
    "src/supply_chain_triage/runners/**/*.py",
    "src/supply_chain_triage/utils/**/*.py",
    "src/supply_chain_triage/main.py",
    "src/supply_chain_triage/__init__.py",
    # modules — agent subpackages (strict shape)
    "src/supply_chain_triage/modules/*/__init__.py",
    "src/supply_chain_triage/modules/*/agents/__init__.py",
    "src/supply_chain_triage/modules/*/agents/*/__init__.py",
    "src/supply_chain_triage/modules/*/agents/*/agent.py",
    "src/supply_chain_triage/modules/*/agents/*/schemas.py",
    "src/supply_chain_triage/modules/*/agents/*/tools.py",
    "src/supply_chain_triage/modules/*/agents/*/prompts/*.md",
    # modules — shared per-module buckets
    "src/supply_chain_triage/modules/*/tools/**/*.py",
    "src/supply_chain_triage/modules/*/memory/**/*.py",
    "src/supply_chain_triage/modules/*/models/**/*.py",
    "src/supply_chain_triage/modules/*/guardrails/**/*.py",
    # modules — pipeline orchestration layer (assembles SequentialAgent + callbacks)
    "src/supply_chain_triage/modules/*/pipeline/**/*.py",
    # tests
    "tests/unit/**/*.py",
    "tests/integration/**/*.py",
    "tests/e2e/**/*.py",
    "tests/fixtures/**/*.py",
    "tests/__init__.py",
    "tests/conftest.py",
    # evals
    "evals/*/**",
    # docs
    "docs/**/*.md",
    # scripts (bash + python automation + seed data)
    "scripts/*.sh",
    "scripts/*.py",
    "scripts/seed/*.json",
    # infra (non-code Firebase/Firestore config)
    "infra/firestore.rules",
    "infra/firestore.indexes.json",
    "firebase.json",
    # root config + tooling
    "pyproject.toml",
    "uv.lock",
    "Makefile",
    "Dockerfile",
    ".dockerignore",
    ".gitignore",
    ".pre-commit-config.yaml",
    ".python-version",
    ".env.template",
    ".env",
    ".secrets.baseline",
    ".gitleaksignore",
    "README.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "LICENSE",
    "CLAUDE.md",
    "firestore.rules",
    "firestore.indexes.json",
    # GitHub
    ".github/**",
    # Claude project config + rules + hooks
    ".claude/**",
    # Session memory (remember plugin)
    ".remember/**",
)


def is_allowed(rel_path: str) -> bool:
    """Return True if the normalized relative path matches any allowlist glob.

    Uses ``PurePosixPath.full_match`` (Python 3.13+) so ``**`` matches
    zero or more path segments, matching standard glob semantics. ``fnmatch``
    does NOT support ``**`` recursively.

    Uses ``.removeprefix("./")`` instead of ``.lstrip("./")`` to avoid eating
    leading dots on dotfiles (``.env``, ``.secrets.baseline``, etc.).
    """
    normalized = rel_path.replace("\\", "/").removeprefix("./")
    p = PurePosixPath(normalized)
    return any(p.full_match(pattern) for pattern in ALLOWLIST)


def extract_paths(tool_name: str, tool_input: dict) -> list[str]:
    """Extract target paths from the tool call payload."""
    if tool_name in {"Edit", "Write"}:
        fp = tool_input.get("file_path")
        return [fp] if fp else []
    if tool_name == "MultiEdit":
        fp = tool_input.get("file_path")
        return [fp] if fp else []
    return []


def to_relative(abs_path: str) -> str | None:
    """Convert an absolute path to repo-relative, or None if outside repo."""
    try:
        cwd = PurePosixPath(str(Path.cwd()).replace("\\", "/"))
        target = PurePosixPath(abs_path.replace("\\", "/"))
        return str(target.relative_to(cwd))
    except ValueError:
        return None  # Outside project tree — not our concern


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError:
        return 0  # No payload → let the tool run.

    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    paths = extract_paths(tool_name, tool_input)
    if not paths:
        return 0

    for abs_path in paths:
        rel = to_relative(abs_path)
        if rel is None:
            continue  # Outside project tree — not our concern
        if not is_allowed(rel):
            sys.stderr.write(
                f"[placement-hook] Rejected write to {rel!r}.\n"
                f"This path is not in the allowlist derived from "
                f".claude/rules/placement.md.\n"
                f"If the file type is legitimate, update the placement table AND "
                f"the ALLOWLIST tuple in .claude/hooks/check_placement.py together.\n"
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
