from __future__ import annotations

import asyncio
import os

from fastapi.testclient import TestClient as _UcpTestClient
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool

from odyssey.common.types import Vertical
from odyssey.merchants.sources import make_source
from odyssey.merchants.ucp_server import attach_ucp_routes, make_ucp_app
from odyssey.protocols.ucp_client import UCPClient

MODEL = "gemini-2.5-flash"
_PORT = {Vertical.FLIGHT: 8001, Vertical.HOTEL: 8002, Vertical.ACTIVITY: 8003}

# Env vars each merchant reads at import time to stamp its own public URL into
# the A2A agent card so remote consumers can reach the service on Cloud Run.
_SELF_URL_ENV = {
    Vertical.FLIGHT: "ODYSSEY_FLIGHT_URL",
    Vertical.HOTEL: "ODYSSEY_HOTEL_URL",
    Vertical.ACTIVITY: "ODYSSEY_ACTIVITY_URL",
}


def _inproc_ucp(vertical: Vertical) -> UCPClient:
    return UCPClient(
        transport=_UcpTestClient(
            make_ucp_app(f"{vertical.value} merchant", vertical, make_source(vertical))
        )
    )


def negotiate_offers(vertical: Vertical, query: str, budget_slice: float) -> dict:
    """Structured negotiation → NegotiationResponse dict. Also the merchant agent's tool and the
    in-process fallback for the A2A client (Task 10)."""
    uc = _inproc_ucp(vertical)
    within = uc.call("search_catalog", {"query": query, "filters": {"max_price": budget_slice}})[
        "products"
    ]
    every = uc.call("search_catalog", {"query": query})["products"]
    prices = sorted(float(p["price"]["value"]) for p in every) or [0.0]
    fits = bool(within)
    nearest = next((p for p in prices if p > budget_slice), None)
    return {
        "offers": within,
        "fits": fits,
        "cheapest": prices[0],
        "nearest_above": (nearest if not fits else None),
        "note": (
            "" if fits else f"nearest option is {nearest if nearest is not None else prices[-1]}"
        ),
    }


def _make_merchant_agent(vertical: Vertical) -> LlmAgent:
    def find_offers(query: str, budget_slice: float) -> dict:
        """Find offers within a budget slice; returns a JSON fit signal + offers.

        Return it verbatim.
        """
        return negotiate_offers(vertical, query, budget_slice)

    return LlmAgent(
        name=f"{vertical.value}_merchant",
        model=MODEL,
        instruction=(
            f"You are a {vertical.value} merchant. When asked for offers within a "
            "budget slice, call find_offers and return its JSON result verbatim as your "
            "final response. Never invent prices."
        ),
        tools=[FunctionTool(find_offers)],
    )


def _build_card_sync(agent: LlmAgent, rpc_url: str):
    """Build the A2A AgentCard, working whether or not an event loop is already running.

    Merchants import this module at process startup (no loop) — `asyncio.run` is fine.
    The concierge imports it lazily INSIDE ADK's request handler (a running loop), where
    `asyncio.run` raises 'cannot be called from a running event loop'; in that case we run
    the async build in a fresh loop on a worker thread.
    """
    def _run() -> object:
        return asyncio.run(AgentCardBuilder(agent=agent, rpc_url=rpc_url).build())

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run()
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_run).result()


def make_merchant_app(vertical: Vertical, port: int):
    agent = _make_merchant_agent(vertical)
    public_url = os.environ.get(_SELF_URL_ENV[vertical])
    if public_url:
        # On Cloud Run, stamp the card with the public HTTPS URL so consumers
        # that resolve the agent card get the correct RPC endpoint.
        agent_card = _build_card_sync(agent, public_url.rstrip("/"))
        app = to_a2a(agent, port=port, agent_card=agent_card)
    else:
        # Local dev: let to_a2a build the card using host/port defaults.
        app = to_a2a(agent, port=port)
    attach_ucp_routes(app, f"{vertical.value} merchant", vertical, make_source(vertical))
    return app


flight_app = make_merchant_app(Vertical.FLIGHT, _PORT[Vertical.FLIGHT])
hotel_app = make_merchant_app(Vertical.HOTEL, _PORT[Vertical.HOTEL])
activity_app = make_merchant_app(Vertical.ACTIVITY, _PORT[Vertical.ACTIVITY])
