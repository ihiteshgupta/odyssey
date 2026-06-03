from __future__ import annotations

import logging
import os
import time

from odyssey.common.types import Intent, Money, NegotiationResponse, Offer, Vertical
from odyssey.concierge.clients import merchant_url
from odyssey.merchants.agents import negotiate_offers

log = logging.getLogger("odyssey.negotiate")

# ── Resilience: bounded retry + strict no-mask mode ───────────────────────────
# The in-process fallback is convenient but it MASKS real cross-process A2A
# failures (it is what hid the original 3-bug cascade). So we (1) retry transient
# failures with exponential backoff before degrading, and (2) allow a STRICT mode
# that surfaces a persistent failure instead of silently serving in-process.
A2A_MAX_ATTEMPTS = max(1, int(os.getenv("ODYSSEY_A2A_MAX_ATTEMPTS", "3")))
A2A_BACKOFF_BASE_S = float(os.getenv("ODYSSEY_A2A_BACKOFF_BASE_S", "0.25"))
A2A_STRICT = os.getenv("ODYSSEY_A2A_STRICT", "").upper() == "TRUE"

# ── Observability: estimated cost/turn ────────────────────────────────────────
# Gemini 3.5 Flash list price (USD per token), from Google's published
# per-1M-token rates: $1.50 / 1M input tokens, $9.00 / 1M output tokens.
# Constants so the math is auditable and updatable in one place.
GEMINI_3_5_FLASH_INPUT_USD_PER_TOKEN = 1.50 / 1_000_000
GEMINI_3_5_FLASH_OUTPUT_USD_PER_TOKEN = 9.00 / 1_000_000


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
            (in_tok or 0) * GEMINI_3_5_FLASH_INPUT_USD_PER_TOKEN
            + (out_tok or 0) * GEMINI_3_5_FLASH_OUTPUT_USD_PER_TOKEN,
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


def _a2a_with_retry(
    url: str,
    vertical: Vertical,
    intent: Intent,
    slice_amount: float,
    context_id: str | None,
) -> dict | None:
    """Call the cross-process A2A merchant with bounded exponential backoff.

    Returns the offer dict on success. When every attempt fails: raises the last
    exception under STRICT mode (surface, don't mask), else returns ``None`` to
    let the caller degrade in-process — logged loudly, never a silent mask."""
    last_exc: Exception | None = None
    for attempt in range(1, A2A_MAX_ATTEMPTS + 1):
        try:
            return _a2a_request_offers(url, vertical, intent, slice_amount, context_id)
        except Exception as e:
            last_exc = e
            log.warning(
                "negotiate[%s] A2A attempt %d/%d failed (%s)",
                vertical.value, attempt, A2A_MAX_ATTEMPTS, e,
            )
            if attempt < A2A_MAX_ATTEMPTS:
                time.sleep(min(A2A_BACKOFF_BASE_S * 2 ** (attempt - 1), 2.0))
    if A2A_STRICT and last_exc is not None:
        log.error(
            "negotiate[%s] A2A exhausted %d attempts; STRICT → surfacing failure",
            vertical.value, A2A_MAX_ATTEMPTS,
        )
        raise last_exc
    log.warning(
        "negotiate[%s] A2A exhausted %d attempts; degrading to in-process fallback",
        vertical.value, A2A_MAX_ATTEMPTS,
    )
    return None


def request_offers(
    vertical: Vertical,
    intent: Intent,
    slice_amount: float,
    context_id: str | None = None,
) -> NegotiationResponse:
    """Ask a merchant agent for offers within a slice.

    PRIMARY path = A2A DataPart round-trip (with bounded retry) when the merchant
    URL is set; FALLBACK = in-process negotiate_offers (unless STRICT). Logs the
    path + fit.
    """
    cur = intent.total_budget.currency
    url = merchant_url(vertical)
    if url:
        raw = _a2a_with_retry(url, vertical, intent, slice_amount, context_id)
        if raw is not None:
            log.info(
                "negotiate[%s] via A2A slice=%.0f fits=%s",
                vertical.value,
                slice_amount,
                raw["fits"],
            )
            _log_estimated_cost(vertical, raw)
            return _raw_to_response(raw, cur)
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
