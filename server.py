"""Cloud Run entrypoint for the Odyssey concierge.

Serves the ADK dev chat UI + API for the concierge agent found under `deploy_agents/`.
Run with: `uvicorn server:app --host 0.0.0.0 --port $PORT`
(the shared merchant image's CMD does exactly this when MERCHANT_MODULE=server:app).
"""

import logging
import os

from google.adk.cli.fast_api import get_fast_api_app

# Surface Odyssey's own INFO logs (e.g. the per-round A2A negotiation trace
# "negotiate[hotel] via A2A slice=… fits=…") in stdout so Cloud Run / the demo
# log panel can show the agent-to-agent negotiation as it happens.
logging.basicConfig(level=logging.INFO)
logging.getLogger("odyssey").setLevel(logging.INFO)

# Cloud Trace: opt-in via env. NOTE: enabling the Cloud Trace exporter at import
# can delay container startup past Cloud Run's health-check window, so it is OFF
# by default; the ADK dev-UI Trace/Events tab shows the multi-agent span tree
# without this. Set ODYSSEY_TRACE_TO_CLOUD=TRUE only with a generous startup probe.
_TRACE = os.environ.get("ODYSSEY_TRACE_TO_CLOUD", "").upper() == "TRUE"

app = get_fast_api_app(
    agents_dir="deploy_agents",
    web=True,
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8080")),
    trace_to_cloud=_TRACE,
)
