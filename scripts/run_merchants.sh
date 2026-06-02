#!/usr/bin/env bash
set -euo pipefail
echo "ODYSSEY: simulated payments — AP2 signatures are stubbed; NO real money moves."
uv run uvicorn odyssey.merchants.agents:flight_app   --host localhost --port 8001 &
uv run uvicorn odyssey.merchants.agents:hotel_app    --host localhost --port 8002 &
uv run uvicorn odyssey.merchants.agents:activity_app --host localhost --port 8003 &
wait
