#!/usr/bin/env bash
# Make all Odyssey Cloud Run services publicly invokable.
# PREREQUISITE: an org admin must first allow `allUsers` for this project by relaxing the
# `iam.allowedPolicyMemberDomains` org policy (see docs/DEPLOYMENT.md "Going public").
# Until then, these bindings fail with FAILED_PRECONDITION (org policy).
set -euo pipefail

PROJECT="${PROJECT:-odyssey-hackathon-498211}"
REGION="${REGION:-asia-south1}"

for SVC in odyssey-flight odyssey-hotel odyssey-activity odyssey-concierge; do
  echo "== $SVC =="
  gcloud run services add-iam-policy-binding "$SVC" \
    --region="$REGION" --project="$PROJECT" \
    --member="allUsers" --role="roles/run.invoker" --quiet
done

echo ""
echo "Public demo URL (concierge):"
gcloud run services describe odyssey-concierge --region="$REGION" --project="$PROJECT" \
  --format='value(status.url)'
