from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi.testclient import TestClient as _UcpTestClient
from google.adk.a2a.utils.agent_card_builder import AgentCardBuilder
from google.adk.a2a.utils.agent_to_a2a import to_a2a
from google.adk.agents import LlmAgent
from google.adk.tools import FunctionTool
from google.genai import types

from odyssey.common.types import Vertical
from odyssey.merchants.sources import make_source
from odyssey.merchants.ucp_server import attach_ucp_routes, make_ucp_app
from odyssey.protocols.ucp_client import UCPClient

log = logging.getLogger("odyssey.merchant")

MODEL = "gemini-3.5-flash"

# Thread the merchant's real LLM token usage to the concierge across A2A by
# appending it as a `__odyssey_usage__` sentinel part on the final response.
# On by default; set ODYSSEY_THREAD_USAGE=0 to capture-and-log only (no mutation
# of the response path) if you want the merchant reply left byte-for-byte intact.
_THREAD_USAGE = os.getenv("ODYSSEY_THREAD_USAGE", "1") != "0"
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


def _usage_after_model_cb(vertical: Vertical):
    """ADK ``after_model_callback`` that surfaces the merchant's real LLM token
    usage. It always logs the counts server-side, and (unless ODYSSEY_THREAD_USAGE=0)
    appends a ``__odyssey_usage__`` sentinel text part to the FINAL response so the
    counts survive the to_a2a hop to the concierge. Fully guarded: any failure
    leaves the response untouched so the merchant can never break."""

    def _after_model(callback_context, llm_response):
        try:
            usage = getattr(llm_response, "usage_metadata", None)
            if usage is None:
                return None
            pt = getattr(usage, "prompt_token_count", None)
            ct = getattr(usage, "candidates_token_count", None)
            tt = getattr(usage, "total_token_count", None)
            log.info(
                "merchant_llm[%s] prompt_tokens=%s output_tokens=%s total_tokens=%s",
                vertical.value, pt, ct, tt,
            )
            content = getattr(llm_response, "content", None)
            if not _THREAD_USAGE or content is None:
                return None
            parts = list(getattr(content, "parts", None) or [])
            # Skip the tool-CALL turn; only stamp usage onto the final answer.
            if any(getattr(p, "function_call", None) for p in parts):
                return None
            sentinel = types.Part(
                text=json.dumps(
                    {
                        "__odyssey_usage__": {
                            "prompt_token_count": pt,
                            "candidates_token_count": ct,
                            "total_token_count": tt,
                        }
                    }
                )
            )
            content.parts = parts + [sentinel]
            return llm_response
        except Exception as e:  # never break the merchant response path
            log.debug("merchant usage threading skipped (%s)", e)
            return None

    return _after_model


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
            f"You are a {vertical.value} merchant agent. ALWAYS call the find_offers tool "
            "with the requested query and budget_slice, then respond with ONLY the tool's "
            "raw JSON object as your entire final message — no prose, no markdown, no code "
            "fences, nothing before or after the '{...}'. Never invent prices or fields."
        ),
        tools=[FunctionTool(find_offers)],
        after_model_callback=_usage_after_model_cb(vertical),
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
