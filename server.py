"""Cloud Run entrypoint for the Odyssey concierge.

Serves the ADK dev chat UI + API for the concierge agent found under `deploy_agents/`.
Run with: `uvicorn server:app --host 0.0.0.0 --port $PORT`
(the shared merchant image's CMD does exactly this when MERCHANT_MODULE=server:app).
"""

import os

from google.adk.cli.fast_api import get_fast_api_app

app = get_fast_api_app(
    agents_dir="deploy_agents",
    web=True,
    host="0.0.0.0",
    port=int(os.environ.get("PORT", "8080")),
)
