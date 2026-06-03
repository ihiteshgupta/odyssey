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
import logging
import re
import time

from odyssey.common.types import Intent, Vertical

log = logging.getLogger("odyssey.a2a")


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


def _coerce_offer_dict(d: object) -> dict | None:
    """Return the NegotiationResponse dict from *d*, unwrapping known nestings.

    ADK surfaces the find_offers result over A2A as a DataPart whose ``.data`` is
    ``{"name": "find_offers", "response": {<offer dict>}}``, and the merchant LLM's
    text echo wraps it under ``find_offers_response``. The offer dict itself has
    ``fits``/``offers`` keys. We accept direct, ``response``, or ``find_offers_response``.
    """
    if not isinstance(d, dict):
        return None
    if "fits" in d or "offers" in d:
        return d
    for key in ("response", "find_offers_response", "result"):
        inner = d.get(key)
        if isinstance(inner, dict) and ("fits" in inner or "offers" in inner):
            return inner
    return None


def _extract_json(text: str) -> dict | None:
    """Parse the first JSON object from *text* that yields an offer dict."""
    text = (text or "").strip()
    for pat in (r"\{.*\}", r"\{.*?\}"):
        m = re.search(pat, text, re.DOTALL)
        if not m:
            continue
        try:
            got = _coerce_offer_dict(json.loads(m.group(0)))
        except (json.JSONDecodeError, ValueError):
            continue
        if got is not None:
            return got
    return None


def _parts_to_result(parts: list) -> dict | None:
    """Scan ``Part`` objects for the find_offers result.

    The reliable source is the tool-response ``DataPart`` (``.data.response``);
    a ``TextPart`` JSON echo is a fallback. Returns the offer dict or None.
    """
    for part in parts or []:
        root = getattr(part, "root", part)
        got = _coerce_offer_dict(getattr(root, "data", None))
        if got is not None:
            return got
        text = getattr(root, "text", None)
        if text:
            got = _extract_json(text)
            if got is not None:
                return got
    return None


def _extract_usage(parts: list) -> dict | None:
    """Pull the merchant LLM ``usage_metadata`` threaded across A2A, if present.

    The merchant's ``after_model_callback`` emits the real token counts either as
    a ``DataPart`` (``.data.usage_metadata``) or, on the to_a2a text path, as a
    ``__odyssey_usage__`` JSON sentinel in a ``TextPart``. Returns the usage dict
    (``prompt_token_count`` / ``candidates_token_count`` / ``total_token_count``)
    or ``None`` when the framework dropped it (then the caller estimates).
    """
    for part in parts or []:
        root = getattr(part, "root", part)
        data = getattr(root, "data", None)
        if isinstance(data, dict):
            usage = data.get("usage_metadata") or data.get("__odyssey_usage__")
            if isinstance(usage, dict):
                return usage
        text = getattr(root, "text", None)
        if text and "__odyssey_usage__" in text:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if not m:
                continue
            try:
                usage = json.loads(m.group(0)).get("__odyssey_usage__")
            except (json.JSONDecodeError, ValueError):
                continue
            if isinstance(usage, dict):
                return usage
    return None


def _estimate_usage(prompt_text: str, response_text: str) -> dict:
    """Deterministic ~4-chars/token estimate, used only when the real merchant
    ``usage_metadata`` didn't survive the A2A hop. Flagged ``estimated`` so the
    cost log is honest about the source."""
    return {
        "prompt_token_count": max(1, len(prompt_text or "") // 4),
        "candidates_token_count": max(1, len(response_text or "") // 4),
        "estimated": True,
    }


def _result_with_usage(parts: list, prompt_text: str) -> dict | None:
    """``_parts_to_result`` + attach a ``_odyssey_usage`` (real if threaded, else
    estimated) so the concierge can log a real cost/turn number."""
    result = _parts_to_result(parts)
    if result is None:
        return None
    usage = _extract_usage(parts) or _estimate_usage(prompt_text, json.dumps(result))
    result = dict(result)
    result["_odyssey_usage"] = usage
    return result


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
    prompt_text = json.dumps(payload) + instruction

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
                    result = _result_with_usage(artifact.parts or [], prompt_text)
                    if result is not None:
                        return result
                # Then task history messages
                for hist_msg in task.history or []:
                    result = _result_with_usage(hist_msg.parts or [], prompt_text)
                    if result is not None:
                        return result
                    for part in hist_msg.parts or []:
                        root = getattr(part, "root", part)
                        text = getattr(root, "text", None)
                        if text:
                            last_text = text
            else:
                # Direct Message reply
                result = _result_with_usage(event.parts or [], prompt_text)
                if result is not None:
                    return result
                for part in event.parts or []:
                    root = getattr(part, "root", part)
                    text = getattr(root, "text", None)
                    if text:
                        last_text = text

        result = _extract_json(last_text)
        if result is None:
            raise ValueError(
                "A2A merchant returned no parseable NegotiationResponse"
            )
        result = dict(result)
        result["_odyssey_usage"] = _estimate_usage(prompt_text, last_text)
        return result


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

    # Observability: time the full A2A round-trip (in-loop or threaded path).
    _t0 = time.perf_counter()
    try:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return _run()
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(_run).result()
    finally:
        roundtrip_ms = round((time.perf_counter() - _t0) * 1000, 1)
        log.info(
            "a2a_roundtrip_ms=%s merchant=%s slice=%s",
            roundtrip_ms,
            vertical.value,
            slice_amount,
        )
