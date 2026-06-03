#!/usr/bin/env bash
# Enable Cloud Trace export on the live Odyssey Cloud Run services + grant the
# runtime service account the Trace role. Idempotent and non-destructive: it
# flips ODYSSEY_TRACE_TO_CLOUD on the EXISTING services (a new revision, same
# image/config) rather than redeploying, and adds startup CPU boost so the
# import-time OpenTelemetry exporter doesn't blow Cloud Run's startup window.
#
# Needs creds: an authenticated gcloud with rights on the project (the deployer
# SA). After running, do a trip from the concierge URL, then open Trace Explorer.
#
# Usage:
#   ./scripts/enable_tracing.sh            # all 4 services
#   TRACE_MERCHANTS=0 ./scripts/enable_tracing.sh   # concierge only
#   ./scripts/enable_tracing.sh --off      # turn tracing back off
set -euo pipefail

PROJECT="${ODYSSEY_PROJECT:-odyssey-hackathon-498211}"
REGION="${ODYSSEY_REGION:-asia-south1}"
RUNTIME_SA="${ODYSSEY_RUNTIME_SA:-odyssey-run@${PROJECT}.iam.gserviceaccount.com}"
TRACE_MERCHANTS="${TRACE_MERCHANTS:-1}"

TRACE_VALUE="TRUE"
if [[ "${1:-}" == "--off" ]]; then TRACE_VALUE="FALSE"; fi

SERVICES=("odyssey-concierge")
if [[ "$TRACE_MERCHANTS" == "1" ]]; then
  SERVICES+=("odyssey-flight" "odyssey-hotel" "odyssey-activity")
fi

echo "→ Project=$PROJECT Region=$REGION  trace=$TRACE_VALUE  services=${SERVICES[*]}"

# 1) Let the runtime SA write traces (idempotent).
echo "→ Granting roles/cloudtrace.agent to $RUNTIME_SA ..."
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/cloudtrace.agent" \
  --condition=None --quiet >/dev/null

# 2) Flip the trace env on each service + startup CPU boost (helps the exporter
#    initialise inside the startup window). --cpu-boost is a no-op if unsupported.
for svc in "${SERVICES[@]}"; do
  echo "→ Updating $svc (ODYSSEY_TRACE_TO_CLOUD=$TRACE_VALUE) ..."
  gcloud run services update "$svc" \
    --project "$PROJECT" --region "$REGION" \
    --update-env-vars "ODYSSEY_TRACE_TO_CLOUD=${TRACE_VALUE}" \
    --cpu-boost --quiet >/dev/null
done

echo
echo "✅ Done. Now run a trip from the concierge, then view spans:"
echo "   Trace Explorer → https://console.cloud.google.com/traces/list?project=${PROJECT}"
echo "   (Filter by service e.g. odyssey-concierge; one trip = a DAG of LLM + A2A tool spans.)"
echo "   No-deploy alternative for the demo: the ADK dev-UI 'Trace'/'Events' tab on the concierge URL."
