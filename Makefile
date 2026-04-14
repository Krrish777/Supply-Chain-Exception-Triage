# Thin passthroughs. The real tooling config lives in pyproject.toml;
# rules of engagement live in .claude/rules/. This Makefile just makes common
# commands one-keystroke instead of two.

.PHONY: help sync lint format type test test-unit test-int eval emulators dev clean check pre-commit

help:
	@echo "Targets:"
	@echo "  sync        — uv sync --all-extras"
	@echo "  lint        — uv run ruff check ."
	@echo "  format      — uv run ruff format ."
	@echo "  type        — uv run mypy src"
	@echo "  test        — uv run pytest"
	@echo "  test-unit   — uv run pytest tests/unit/"
	@echo "  test-int    — uv run pytest -m integration"
	@echo "  eval        — adk eval <agent_dir> <evalset>  (reminder)"
	@echo "  emulators   — firebase emulators:start --only firestore,auth"
	@echo "  dev         — adk web (on modules/triage/agents)"
	@echo "  pre-commit  — uv run pre-commit run --all-files"
	@echo "  check       — sync lint type test"

sync:
	uv sync --all-extras

lint:
	uv run ruff check .

format:
	uv run ruff format .

type:
	uv run mypy src

test:
	uv run pytest

test-unit:
	uv run pytest tests/unit/

test-int:
	uv run pytest -m integration

eval:
	@echo "Run: adk eval <agent_dir> <evalset>"
	@echo "Agents live under src/supply_chain_triage/modules/*/agents/"
	@echo "Evalsets live under evals/<agent_name>/"

emulators:
	firebase emulators:start --only firestore,auth

dev:
	adk web src/supply_chain_triage/modules/triage/agents

pre-commit:
	uv run pre-commit run --all-files

clean:
	rm -rf .venv .pytest_cache .ruff_cache .mypy_cache coverage.xml htmlcov/ __pycache__

check: sync lint type test
