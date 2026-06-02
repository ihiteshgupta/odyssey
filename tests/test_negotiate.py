from odyssey.common.types import Intent, Money, Vertical
from odyssey.concierge.negotiate import request_offers


def test_request_offers_inproc_fallback(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    monkeypatch.delenv("ODYSSEY_HOTEL_URL", raising=False)  # no URL → in-process path
    intent = Intent("JFK", "DPS", "2026-09-01", "2026-09-06", 2, Money("USD", 2500.0), ["beachy"])
    resp = request_offers(Vertical.HOTEL, intent, slice_amount=700.0)
    assert resp.fits is True and resp.offers and resp.cheapest.currency == "USD"
