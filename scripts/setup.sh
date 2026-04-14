#!/usr/bin/env bash
# Idempotent Sprint 0 dev setup.
# Safe to run multiple times. Exits non-zero on hard failures; warns on soft checks.
set -euo pipefail

echo "=== Supply Chain Triage — dev setup ==="

# 1. Python 3.13
if ! command -v python3.13 &>/dev/null && ! python3 --version 2>/dev/null | grep -q "3.13"; then
  echo "Python 3.13 not found. Install from python.org or pyenv, or let uv manage it (uv python install 3.13)." >&2
  exit 1
fi
echo "✓ Python 3.13"

# 2. uv (install if missing)
if ! command -v uv &>/dev/null; then
  echo "Installing uv..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi
echo "✓ uv $(uv --version | awk '{print $2}')"

# 3. Sync dependencies (creates/updates .venv, writes uv.lock)
uv sync --all-extras
echo "✓ dependencies installed"

# 4. Ensure .secrets.baseline exists BEFORE pre-commit installs hooks.
if [ ! -f ".secrets.baseline" ]; then
  uv run detect-secrets scan > .secrets.baseline
  echo "✓ .secrets.baseline created (was missing)"
else
  echo "✓ .secrets.baseline present"
fi

# 5. Pre-commit hooks (user-owned config; install if present)
if [ -f ".pre-commit-config.yaml" ]; then
  uv run pre-commit install
  uv run pre-commit install --hook-type commit-msg
  echo "✓ pre-commit hooks installed"
else
  echo "⚠ .pre-commit-config.yaml not present — skip pre-commit install (user will populate)"
fi

# 6. gcloud CLI check (soft)
if ! command -v gcloud &>/dev/null; then
  echo "⚠ gcloud CLI not found. Install from cloud.google.com/sdk — needed for Sprint 0 GCP bootstrap." >&2
else
  echo "✓ gcloud $(gcloud --version 2>/dev/null | head -1 | awk '{print $4}')"
fi

# 7. firebase CLI check (soft)
if ! command -v firebase &>/dev/null; then
  echo "⚠ firebase CLI not found. Run: npm i -g firebase-tools — needed for Firestore emulator." >&2
else
  echo "✓ firebase $(firebase --version)"
fi

# 8. Java 17 JRE (soft — needed by Firestore emulator)
if ! command -v java &>/dev/null; then
  echo "⚠ Java not found. Firestore emulator requires JRE 17+." >&2
else
  echo "✓ Java $(java -version 2>&1 | head -1)"
fi

# 9. .env check (soft)
if [ ! -f ".env" ]; then
  if [ -f ".env.template" ]; then
    echo "⚠ .env missing. Copy .env.template to .env and fill in values." >&2
  else
    echo "⚠ .env and .env.template both missing — user needs to populate both." >&2
  fi
fi

# 10. Package import smoke test
if uv run python -c "import supply_chain_triage" 2>/dev/null; then
  echo "✓ package import OK"
else
  echo "⚠ package import failed — may be expected in very early Sprint 0 (modules not yet built)"
fi

echo "=== setup complete ==="
echo "Next: make test (or: uv run pytest)"
