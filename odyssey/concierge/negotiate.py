from __future__ import annotations

import logging

from odyssey.common.types import Intent, Money, NegotiationResponse, Offer, Vertical
from odyssey.concierge.clients import merchant_url
from odyssey.merchants.agents import negotiate_offers

log = logging.getLogger("odyssey.negotiate")


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
            return _raw_to_response(raw, cur)
        except Exception as e:
            log.warning(
                "negotiate[%s] A2A failed (%s); falling back in-process", vertical.value, e
            )
    raw = negotiate_offers(vertical, query=intent.destination, budget_slice=slice_amount)
    log.info(
        "negotiate[%s] in-process slice=%.0f fits=%s", vertical.value, slice_amount, raw["fits"]
    )
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
