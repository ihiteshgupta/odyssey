"""Cloud Run entrypoint for the Odyssey concierge.

Serves the ADK dev chat UI + API for the concierge agent found under `deploy_agents/`.
Run with: `uvicorn server:app --host 0.0.0.0 --port $PORT`
(the shared merchant image's CMD does exactly this when MERCHANT_MODULE=server:app).
"""

import os

from google.adk.cli.fast_api import get_fast_api_app

# Cloud Trace: emit the multi-agent call waterfall (concierge → A2A merchant agents,
# tool calls, Gemini spans) to Cloud Trace when running on GCP. Toggled by env so local
# runs stay offline. On Cloud Run set ODYSSEY_TRACE_TO_CLOUD=TRUE.
_TRACE = os.environ.get("ODYSSEY_TRACE_TO_CLOUD", "").upper() == "TRUE"

app = get_fast_api_app(
    agents_dir="deploy_agents",
    web=True,
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8080")),
    trace_to_cloud=_TRACE,
)
