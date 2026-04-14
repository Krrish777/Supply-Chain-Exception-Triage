#!/usr/bin/env bash
# One-time GCP + Firebase bootstrap.
# Idempotent: safe to re-run after mistakes.
# Prerequisites: gcloud CLI authenticated (gcloud auth login), GCP project billing enabled.
set -euo pipefail

: "${GCP_PROJECT_ID:?Set GCP_PROJECT_ID in .env first}"
: "${FIREBASE_PROJECT_ID:?Set FIREBASE_PROJECT_ID in .env first}"

echo "=== GCP Bootstrap for $GCP_PROJECT_ID ==="

# 1. Verify billing (Risk 1 pre-check)
if ! gcloud billing projects describe "$GCP_PROJECT_ID" 2>/dev/null | grep -q 'billingEnabled: true'; then
  echo "❌ Billing not enabled on $GCP_PROJECT_ID. Enable at https://console.cloud.google.com/billing" >&2
  exit 1
fi
echo "✓ billing enabled"

# 2. Enable required APIs
gcloud services enable \
  secretmanager.googleapis.com \
  firestore.googleapis.com \
  aiplatform.googleapis.com \
  --project="$GCP_PROJECT_ID"
echo "✓ APIs enabled: secretmanager, firestore, aiplatform"

# 3. Create Firestore database (asia-south1 Mumbai)
gcloud firestore databases create \
  --location=asia-south1 \
  --project="$GCP_PROJECT_ID" \
  2>/dev/null || echo "✓ Firestore DB already exists in asia-south1"

# 4. Create secrets (idempotent)
for secret in GEMINI_API_KEY SUPERMEMORY_API_KEY FIREBASE_SERVICE_ACCOUNT; do
  gcloud secrets create "$secret" \
    --replication-policy=automatic \
    --project="$GCP_PROJECT_ID" \
    2>/dev/null \
    && echo "✓ created secret: $secret" \
    || echo "✓ secret exists: $secret"
done

# 5. Create dev service account
DEV_SA="supply-chain-dev@${GCP_PROJECT_ID}.iam.gserviceaccount.com"
gcloud iam service-accounts create supply-chain-dev \
  --display-name="Supply Chain Dev SA" \
  --project="$GCP_PROJECT_ID" \
  2>/dev/null \
  && echo "✓ created dev SA: $DEV_SA" \
  || echo "✓ dev SA exists: $DEV_SA"

# 6. Grant least-privilege roles to dev SA
for role in roles/secretmanager.secretAccessor roles/datastore.user; do
  gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member="serviceAccount:$DEV_SA" \
    --role="$role" \
    --condition=None \
    --quiet \
    >/dev/null
  echo "✓ granted $role to $DEV_SA"
done

echo
echo "=== GCP Bootstrap complete ==="
echo
echo "Next steps (manual, one-time):"
echo "  1. Add secret versions:"
echo "       echo -n \"<your-gemini-key>\"    | gcloud secrets versions add GEMINI_API_KEY    --data-file=- --project=$GCP_PROJECT_ID"
echo "       echo -n \"<your-supermemory-key>\" | gcloud secrets versions add SUPERMEMORY_API_KEY --data-file=- --project=$GCP_PROJECT_ID"
echo "       gcloud secrets versions add FIREBASE_SERVICE_ACCOUNT --data-file=path/to/firebase-service-account.json --project=$GCP_PROJECT_ID"
echo "  2. Enable Google Sign-In in Firebase console for $FIREBASE_PROJECT_ID."
echo "  3. Create a test user via Firebase console, then run scripts/set_custom_claims.py to attach company_id."
