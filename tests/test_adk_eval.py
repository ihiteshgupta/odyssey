"""ADK AgentEvaluator harness for the Odyssey concierge.

Runs Google's official ADK evaluation against ``evals/odyssey.evalset.json``,
scoring the two happy-path cases (Bali $2500 booking and the $700 infeasible
no-booking gate) on:

  * ``tool_trajectory_avg_score`` — did the agent fire plan_trip / complete_trip
    in the expected order (1.0 = exact trajectory match), and
  * ``response_match_score``     — ROUGE overlap of the final response text.

Thresholds live in ``test_config.json`` at the repo root (ADK auto-discovers a
``test_config.json`` next to the evalset / cwd).

LIVE-ONLY: AgentEvaluator actually runs the LlmAgent, so it needs a Gemini
backend. We skip when no creds are present — identical guard to the two other
live tests (test_a2a_contract.py, test_hitl_guardrail_spike.py) — so the
offline SEED suite and CI stay green with this test SKIPPED, not failed.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

# Same skip-guard family as the existing 2 live tests: require a Gemini key.
# Also accept a Vertex project (GOOGLE_CLOUD_PROJECT) so the eval can run under
# either backend; absent both → SKIP (never fail the offline suite / CI).
_HAS_GEMINI_CREDS = bool(
    os.environ.get("GOOGLE_API_KEY") or os.environ.get("GOOGLE_CLOUD_PROJECT")
)

pytestmark = pytest.mark.skipif(
    not _HAS_GEMINI_CREDS,
    reason="needs Gemini/Vertex creds (GOOGLE_API_KEY or GOOGLE_CLOUD_PROJECT) to run AgentEvaluator",
)

# Verified agent module: ADK's AgentEvaluator._get_agent_for_eval requires the
# module to either expose a member `agent` OR have a name ending in `.agent`,
# then reads `root_agent` off it. `odyssey.concierge` (empty __init__) fails
# that check; `odyssey.concierge.agent` (ends with `.agent`, exposes
# `root_agent`) is the resolvable path.
_AGENT_MODULE = "odyssey.concierge.agent"
_EVALSET = str(Path(__file__).resolve().parents[1] / "evals" / "odyssey.evalset.json")


@pytest.mark.asyncio
async def test_concierge_evalset_meets_thresholds(monkeypatch):
    """AgentEvaluator must clear the test_config.json thresholds for both cases."""
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    # Force in-process merchant negotiation (no live A2A merchants needed).
    for v in ("FLIGHT", "HOTEL", "ACTIVITY"):
        monkeypatch.delenv(f"ODYSSEY_{v}_URL", raising=False)

    from google.adk.evaluation.agent_evaluator import AgentEvaluator

    await AgentEvaluator.evaluate(
        agent_module=_AGENT_MODULE,
        eval_dataset_file_path_or_dir=_EVALSET,
    )
