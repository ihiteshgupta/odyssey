"""A2A negotiation resilience: bounded retry + backoff, and a strict no-mask mode.

Before: request_offers tried A2A once and on ANY exception silently degraded to
the in-process fallback — a single transient blip abandoned cross-process
negotiation and hid the failure (the pattern that masked the 3-bug cascade).
After: retry with backoff before degrading, and ODYSSEY_A2A_STRICT to surface a
persistent failure instead of masking it. All offline (sleep patched out).
"""
from __future__ import annotations

import pytest

import odyssey.concierge.negotiate as neg
from odyssey.common.types import Intent, Money, Vertical

_INTENT = Intent("JFK", "DPS", "2026-09-01", "2026-09-06", 2, Money("USD", 2500.0), ["beachy"])
_GOOD = {
    "offers": [
        {"id": "h1", "vertical": "hotel", "title": "Seaside", "price": {"currency": "USD", "value": 600.0}}
    ],
    "fits": True,
    "cheapest": 600.0,
    "nearest_above": None,
    "note": "",
}


def _boom(*_a, **_k):
    raise RuntimeError("transient A2A blip")


@pytest.fixture(autouse=True)
def _fast_and_remote(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    monkeypatch.setattr(neg.time, "sleep", lambda *_a, **_k: None)  # no real backoff wait
    monkeypatch.setattr(neg, "merchant_url", lambda _v: "https://merchant.example")  # force A2A path


def test_a2a_retries_transient_then_succeeds(monkeypatch):
    monkeypatch.setattr(neg, "A2A_MAX_ATTEMPTS", 3)
    monkeypatch.setattr(neg, "A2A_STRICT", False)
    calls = {"n": 0}

    def flaky(*_a, **_k):
        calls["n"] += 1
        if calls["n"] < 3:
            raise RuntimeError("transient A2A blip")
        return _GOOD

    monkeypatch.setattr(neg, "_a2a_request_offers", flaky)
    resp = neg.request_offers(Vertical.HOTEL, _INTENT, slice_amount=700.0)
    assert calls["n"] == 3  # retried instead of giving up on the first blip
    assert resp.fits is True and resp.offers[0].price.amount == 600.0  # used the A2A result


def test_a2a_exhausts_attempts_then_falls_back(monkeypatch):
    monkeypatch.setattr(neg, "A2A_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(neg, "A2A_STRICT", False)
    calls = {"n": 0}

    def always_fail(*_a, **_k):
        calls["n"] += 1
        raise RuntimeError("merchant down")

    monkeypatch.setattr(neg, "_a2a_request_offers", always_fail)
    resp = neg.request_offers(Vertical.HOTEL, _INTENT, slice_amount=700.0)
    assert calls["n"] == 2  # exhausted the bounded attempts
    assert resp.fits is True and resp.offers  # degraded to in-process SEED (still serves the trip)


def test_a2a_strict_mode_surfaces_failure(monkeypatch):
    monkeypatch.setattr(neg, "A2A_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(neg, "A2A_STRICT", True)
    monkeypatch.setattr(neg, "_a2a_request_offers", _boom)
    with pytest.raises(RuntimeError, match="transient A2A blip"):
        neg.request_offers(Vertical.HOTEL, _INTENT, slice_amount=700.0)  # no silent mask
