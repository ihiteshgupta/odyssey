from __future__ import annotations

import logging

from odyssey.common.types import Intent, Money, NegotiationResponse, Offer, Vertical
from odyssey.concierge.clients import merchant_url
from odyssey.merchants.agents import negotiate_offers

log = logging.getLogger("odyssey.negotiate")

# ── Observability: estimated cost/turn ────────────────────────────────────────
# Gemini 2.5 Flash list price (USD per token), from Google's published
# per-1M-token rates: $0.30 / 1M input tokens, $2.50 / 1M output tokens.
# Constants so the math is auditable and updatable in one place.
GEMINI_2_5_FLASH_INPUT_USD_PER_TOKEN = 0.30 / 1_000_000
GEMINI_2_5_FLASH_OUTPUT_USD_PER_TOKEN = 2.50 / 1_000_000


def _usage_from(obj: object) -> object | None:
    """Best-effort: pull a Gemini ``usage_metadata`` off a response-like object.

    The A2A round-trip returns a plain offer dict, so token counts are usually
    only reachable when the merchant attaches usage under a ``usage`` /
    ``usage_metadata`` key or when a genai response object is threaded through.
    Returns the usage object/mapping, or ``None`` when unreachable.
    """
    usage = getattr(obj, "usage_metadata", None)
    if usage is not None:
        return usage
    if isinstance(obj, dict):
        return obj.get("usage_metadata") or obj.get("usage")
    return None


def _count(usage: object, *names: str) -> int | None:
    for name in names:
        val = getattr(usage, name, None)
        if val is None and isinstance(usage, dict):
            val = usage.get(name)
        if val is not None:
            return int(val)
    return None


def _log_estimated_cost(vertical: Vertical, source: object) -> None:
    """Log the USD cost/turn for one negotiation. The A2A path attaches token
    counts under ``_odyssey_usage`` (real when the merchant threaded its
    ``usage_metadata``, else a flagged estimate); the in-process path makes no
    LLM call, so its cost is a genuine 0.0. Always non-breaking (never raises)."""
    try:
        usage = None
        estimated = False
        if isinstance(source, dict) and isinstance(source.get("_odyssey_usage"), dict):
            usage = source["_odyssey_usage"]
            estimated = bool(usage.get("estimated"))
        else:
            usage = _usage_from(source)
        if usage is None:
            # No LLM was invoked (in-process UCP search fallback) → real zero cost.
            log.info("cost[%s] no LLM call (in-process) cost_usd=0.0", vertical.value)
            return
        in_tok = _count(usage, "prompt_token_count", "input_tokens", "input_token_count")
        out_tok = _count(
            usage, "candidates_token_count", "output_tokens", "output_token_count"
        )
        cost_usd = round(
            (in_tok or 0) * GEMINI_2_5_FLASH_INPUT_USD_PER_TOKEN
            + (out_tok or 0) * GEMINI_2_5_FLASH_OUTPUT_USD_PER_TOKEN,
            6,
        )
        log.info(
            "cost[%s] in_tokens=%s out_tokens=%s cost_usd=%s estimated=%s",
            vertical.value,
            in_tok,
            out_tok,
            cost_usd,
            estimated,
        )
    except Exception as e:  # observability must never break negotiation
        log.debug("cost[%s] estimate skipped (%s)", vertical.value, e)


def _to_offer(d: dict) -> Offer:
    return Offer(
        id=d["id"],
        vertical=Vertical(d["vertical"]),
        title=d["title"],
        price=Money(d["price"]["currency"], float(d["price"]["value"])),
        raw=d,
    )


def _raw_to_response(raw: dict, currency: str) -> NegotiationResponse:
    return NegotiationResponse(
        offers=[_to_offer(o) for o in raw["offers"]],
        fits=raw["fits"],
        cheapest=Money(currency, float(raw["cheapest"])),
        nearest_above=(
            Money(currency, float(raw["nearest_above"]))
            if raw.get("nearest_above") is not None
            else None
        ),
        note=raw.get("note", ""),
    )


def request_offers(
    vertical: Vertical,
    intent: Intent,
    slice_amount: float,
    context_id: str | None = None,
) -> NegotiationResponse:
    """Ask a merchant agent for offers within a slice.

    PRIMARY path = A2A DataPart round-trip when the merchant URL is set;
    FALLBACK = in-process negotiate_offers. Logs the path + fit.
    """
    cur = intent.total_budget.currency
    url = merchant_url(vertical)
    if url:
        try:
            raw = _a2a_request_offers(url, vertical, intent, slice_amount, context_id)
            log.info(
                "negotiate[%s] via A2A slice=%.0f fits=%s",
                vertical.value,
                slice_amount,
                raw["fits"],
            )
            _log_estimated_cost(vertical, raw)
            return _raw_to_response(raw, cur)
        except Exception as e:
            log.warning(
                "negotiate[%s] A2A failed (%s); falling back in-process", vertical.value, e
            )
    raw = negotiate_offers(vertical, query=intent.destination, budget_slice=slice_amount)
    log.info(
        "negotiate[%s] in-process slice=%.0f fits=%s", vertical.value, slice_amount, raw["fits"]
    )
    _log_estimated_cost(vertical, raw)
    return _raw_to_response(raw, cur)


def _a2a_request_offers(
    url: str,
    vertical: Vertical,
    intent: Intent,
    slice_amount: float,
    context_id: str | None,
) -> dict:
    """Send a NegotiationRequest as an A2A DataPart and parse the NegotiationResponse.

    Implemented in Task 11 (a2a_client.a2a_negotiate). Imported lazily so Task 10 doesn't
    depend on it.
    """
    from odyssey.concierge.a2a_client import a2a_negotiate

    return a2a_negotiate(url, vertical, intent, slice_amount, context_id)
