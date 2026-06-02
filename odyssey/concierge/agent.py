from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from odyssey.concierge.guardrail import before_tool_callback

MODEL = "gemini-2.5-flash"


def _search_offers() -> dict:
    """Search demo offers. Always allowed."""
    return {"offers": [{"id": "demo-1", "title": "Demo item", "price": "10.00 USD"}]}


def _complete_purchase(offer_id: str) -> dict:
    """Book the selected offer. Requires explicit human confirmation."""
    return {"status": "confirmed", "offer_id": offer_id, "note": "SIMULATED — no real charge"}


def build_spike_agent() -> LlmAgent:
    return LlmAgent(
        name="odyssey_spike",
        model=MODEL,
        instruction=(
            "Demo. Use search_offers, then complete_purchase. Never book without searching."
        ),
        tools=[
            FunctionTool(_search_offers),
            FunctionTool(_complete_purchase, require_confirmation=True),
        ],
        before_tool_callback=before_tool_callback,
    )
