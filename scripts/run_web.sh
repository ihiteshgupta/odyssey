#!/usr/bin/env bash
set -euo pipefail
export $(grep -v '^#' .env | xargs) 2>/dev/null || true
echo "ODYSSEY concierge — simulated payments only."
uv run adk web odyssey/concierge
