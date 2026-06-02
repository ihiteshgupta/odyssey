"""A2A DataPart negotiation round-trip client.

Sends a NegotiationRequest as an A2A DataPart to a merchant agent's A2A
endpoint, receives the NegotiationResponse (structured DataPart preferred,
else JSON-from-text fallback), and returns the raw dict.

The function ``a2a_negotiate`` is the public entry point; it is lazily
imported by ``odyssey.concierge.negotiate._a2a_request_offers`` so this
module only needs to import cleanly offline (no Gemini key required at import
time).
"""
from __future__ import annotations

import asyncio
import json
import re

from odyssey.common.types import Intent, Vertical


def _request_payload(
    vertical: Vertical, intent: Intent, slice_amount: float
) -> dict:
    return {
        "kind": "NegotiationRequest",
        "vertical": vertical.value,
        "intent": {
            "origin": intent.origin,
            "destination": intent.destination,
            "start_date": intent.start_date,
            "end_date": intent.end_date,
            "party_size": intent.party_size,
            "prefs": intent.prefs,
        },
        "budget_slice": {
            "currency": intent.total_budget.currency,
            "max": slice_amount,
        },
    }


def _extract_json(text: str) -> dict:
    """Parse the first JSON object from *text* (tolerant fallback)."""
    text = (text or "").strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    return json.loads(m.group(0) if m else text)


def _parts_to_result(parts: list) -> dict | None:
    """Scan a list of ``Part`` objects; return first DataPart.data or None."""
    for part in parts or []:
        root = getattr(part, "root", part)
        data = getattr(root, "data", None)
        if data is not None:
            return data  # type: ignore[return-value]
    return None


async def _negotiate_async(
    url: str,
    vertical: Vertical,
    intent: Intent,
    slice_amount: float,
    context_id: str | None,
) -> dict:
    """Async implementation of the A2A DataPart negotiation round-trip.

    Iteration note: ``Client.send_message`` is an ``AsyncGenerator`` that
    yields either:
    - ``tuple[Task, TaskStatusUpdateEvent | TaskArtifactUpdateEvent | None]``
    - ``Message``

    We scan every item for the first DataPart payload, or accumulate text as
    a fallback for ``_extract_json``.
    """
    import httpx
    from a2a.client import A2ACardResolver, ClientConfig, ClientFactory
    from a2a.types import DataPart, Message, Part, Role, TextPart

    payload = _request_payload(vertical, intent, slice_amount)
    instruction = (
        f"Call find_offers with query='{intent.destination}' "
        f"and budget_slice={slice_amount}, "
        "and return its JSON result verbatim."
    )

    async with httpx.AsyncClient(timeout=30.0) as http:
        card = await A2ACardResolver(
            httpx_client=http, base_url=url.rstrip("/")
        ).get_agent_card()

        client = ClientFactory(
            ClientConfig(httpx_client=http, streaming=False)
        ).create(card)

        msg = Message(
            message_id="neg-1",
            role=Role.user,
            context_id=context_id,
            parts=[
                Part(root=DataPart(data=payload)),
                Part(root=TextPart(text=instruction)),
            ],
        )

        last_text = ""
        async for event in client.send_message(msg):
            # event is either tuple[Task, UpdateEvent|None] or Message
            if isinstance(event, tuple):
                task, _update = event
                # Check task artifacts first
                for artifact in task.artifacts or []:
                    result = _parts_to_result(artifact.parts or [])
                    if result is not None:
                        return result
                # Then task history messages
                for hist_msg in task.history or []:
                    result = _parts_to_result(hist_msg.parts or [])
                    if result is not None:
                        return result
                    for part in hist_msg.parts or []:
                        root = getattr(part, "root", part)
                        text = getattr(root, "text", None)
                        if text:
                            last_text = text
            else:
                # Direct Message reply
                result = _parts_to_result(event.parts or [])
                if result is not None:
                    return result
                for part in event.parts or []:
                    root = getattr(part, "root", part)
                    text = getattr(root, "text", None)
                    if text:
                        last_text = text

        return _extract_json(last_text)


def a2a_negotiate(
    url: str,
    vertical: Vertical,
    intent: Intent,
    slice_amount: float,
    context_id: str | None = None,
) -> dict:
    """Send a NegotiationRequest DataPart to *url* and return the raw offer dict.

    Returns a dict with keys: ``offers``, ``fits``, ``cheapest``,
    ``nearest_above`` (optional), ``note`` (optional) — the same shape
    produced by ``odyssey.merchants.agents.negotiate_offers``.

    Requires a running A2A-compatible merchant agent at *url* and a valid
    Gemini backend (Vertex AI or ``GOOGLE_API_KEY``) for the agent.

    Loop-safe: callers like the ADK concierge invoke this from inside a running
    event loop, where ``asyncio.run`` raises 'cannot be called from a running
    event loop'. In that case we run the coroutine on a fresh loop in a worker
    thread so the real cross-service A2A call actually happens (instead of the
    request_offers in-process fallback).
    """
    def _run() -> dict:
        return asyncio.run(
            _negotiate_async(url, vertical, intent, slice_amount, context_id)
        )

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return _run()
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
        return ex.submit(_run).result()
