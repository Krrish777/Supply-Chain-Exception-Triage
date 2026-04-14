#!/usr/bin/env bash
# Deployment — DEFERRED to Sprint 5.
#
# Resolved Decision #7 of Sprint 0 PRD v2: deployment target is chosen at Sprint 5
# after Tier 1 prototype (hackathon submission Apr 24) ships. Four options are
# researched in the vault note Supply-Chain-Deployment-Options-Research.
#
# This stub exists so:
#   - `deploy.yml` GitHub Actions workflow has something to call (user-owned)
#   - The setup.sh onboarding doesn't fail on missing script
#   - Sprint 5 knows exactly which file to overwrite
#
# TODO(sprint-5): replace with real Cloud Run (or Agent Engine or GKE) deploy steps.
set -euo pipefail

echo "Deployment deferred to Sprint 5."
echo "See docs/research/ for deployment option research when it lands."
echo "TODO(sprint-5): implement after deployment target is chosen."
exit 0
