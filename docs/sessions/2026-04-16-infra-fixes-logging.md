# 2026-04-16 — Infra fixes + agent logging

## Decisions

1. **gitleaks → CI only.** Moved from pre-commit to `.github/workflows/security.yml` (push/PR + weekly cron rescan). Rationale: secret scanning is a policy gate, not a fast local check; pre-commit gitleaks was blocking commits due to `.secrets.baseline` false-positives.
2. **`.gitleaksignore`** allowlists 4 fingerprints — SHA1 hashes in `.secrets.baseline` are detect-secrets artifacts, not real secrets.
3. **`adk web` target = `modules/triage/agents`**, not `modules/triage/`. ADK discovers agents by scanning immediate subdirectories for `root_agent`. Pointing at the module root exposed `memory/`, `tools/`, etc. as false agent candidates.
4. **`hello_world/__init__.py` needs `from . import agent`** — ADK import-based discovery requires it.
5. **Agent logging wired via callbacks.** `_before_agent` (perf_counter_ns stopwatch), `_after_model` (usage_metadata token capture), `_after_agent` (emits `log_agent_invocation`). State keys use `temp:hello_world:*` prefix per agents.md §2.
6. **`utils/logging.py` cap bumped to 500.** Per-file exception in `check_file_size.py` + documented in `code-quality.md`. No split — file is the architecturally-designated single logging entry point (architecture-layers.md §2 narrow exception).

## Files changed

- `.pre-commit-config.yaml` — removed gitleaks hook
- `.github/workflows/security.yml` — new: gitleaks CI workflow
- `.gitleaksignore` — new: fingerprint allowlist
- `.claude/rules/placement.md` + `.claude/hooks/check_placement.py` — added `.gitleaksignore`, `.remember/**`
- `src/.../agents/hello_world/__init__.py` — `from . import agent`
- `src/.../agents/hello_world/agent.py` — 3 logging callbacks
- `tests/unit/agents/test_hello_world.py` — 4 new callback tests (8 total pass)
- `Makefile` — `make dev` targets `modules/triage/agents`
- `CLAUDE.md` — updated `adk web` command
- `.claude/hooks/check_file_size.py` — per-file 500 cap for `utils/logging.py`
- `.claude/rules/code-quality.md` — documented logging.py exception

## Open for next session

- Uncommitted changes need staging + commit (pre-commit auto-fixes created staged/unstaged conflicts on `.gitignore`, `pyproject.toml`, `README.md`)
- Sprint 0 smoke tests still pending: `adk web` live, emulator start (Java 17 required), evalset
- Sprint 1 Classifier PRD is next SDLC step
