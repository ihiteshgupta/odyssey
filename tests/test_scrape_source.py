"""
Offline unit tests for ScrapeSource.

All tests inject a fake Firecrawl client — no real API key required.
The fake client's .scrape() returns a simple namespace whose .json attribute
holds a dict matching the ScrapedOffers schema.
"""
from __future__ import annotations

from odyssey.common.types import Vertical
from odyssey.data.scrape import _CACHE, ScrapeSource

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakeDoc:
    """Minimal stand-in for a Firecrawl Document."""

    def __init__(self, json_data):
        self.json = json_data


class FakeClient:
    """Fake Firecrawl client with a controllable .scrape() method."""

    def __init__(self, response_json=None, raise_exc=None):
        self._response_json = response_json
        self._raise_exc = raise_exc
        self.call_count = 0

    def scrape(self, url, *, formats=None, only_main_content=None, **kwargs):
        self.call_count += 1
        if self._raise_exc is not None:
            raise self._raise_exc
        return FakeDoc(self._response_json)


_BALI_TARGETS = ["https://en.wikivoyage.org/wiki/Bali"]

_GOOD_RESPONSE = {
    "offers": [
        {"title": "Ubud Cultural Tour", "price": "35.00", "currency": "USD"},
        {"title": "Kuta Surf Lesson", "price": "50", "currency": "USD"},
    ]
}


def _make_source(client, vertical=Vertical.ACTIVITY, ttl=900.0):
    """Create a ScrapeSource with an injected fake client and a clean cache."""
    _CACHE.clear()
    return ScrapeSource(vertical=vertical, targets=_BALI_TARGETS, client=client, ttl=ttl)


# ---------------------------------------------------------------------------
# Test 1 — extraction maps to Offer with correct Money + provenance in raw
# ---------------------------------------------------------------------------


def test_extraction_maps_to_offer():
    client = FakeClient(response_json=_GOOD_RESPONSE)
    src = _make_source(client)
    offers = src.search("", None)

    assert len(offers) == 2
    titles = {o.title for o in offers}
    assert "Ubud Cultural Tour" in titles
    assert "Kuta Surf Lesson" in titles

    tour = next(o for o in offers if o.title == "Ubud Cultural Tour")
    assert tour.price.currency == "USD"
    assert tour.price.amount == 35.00
    assert tour.vertical == Vertical.ACTIVITY
    assert tour.raw["method"] == "public-web-scrape"
    assert tour.raw["note"] == "indicative pricing"
    assert "fetched_at" in tour.raw
    assert tour.raw["source"] == _BALI_TARGETS[0]
    # id is 12-char hex
    assert len(tour.id) == 12


# ---------------------------------------------------------------------------
# Test 2 — bad row (price "N/A" / None) is dropped, good rows kept
# ---------------------------------------------------------------------------


def test_bad_price_row_dropped():
    response = {
        "offers": [
            {"title": "Free Walking Tour", "price": "N/A", "currency": "USD"},
            {"title": "Good Offer", "price": "20", "currency": "USD"},
            {"title": "None Price", "price": None, "currency": "USD"},
        ]
    }
    client = FakeClient(response_json=response)
    src = _make_source(client)
    offers = src.search("", None)

    assert len(offers) == 1
    assert offers[0].title == "Good Offer"


# ---------------------------------------------------------------------------
# Test 3 — scrape raising → falls back to seed (non-empty, no raise)
# ---------------------------------------------------------------------------


def test_scrape_raises_falls_back_to_seed():
    client = FakeClient(raise_exc=TimeoutError("connection timed out"))
    src = _make_source(client)
    offers = src.search("", None)

    assert offers, "fallback must return non-empty seed results"
    # Seed activity offers have seed-act-* ids
    assert all(o.vertical == Vertical.ACTIVITY for o in offers)


# ---------------------------------------------------------------------------
# Test 4 — zero extracted offers → seed fallback
# ---------------------------------------------------------------------------


def test_zero_offers_falls_back_to_seed():
    client = FakeClient(response_json={"offers": []})
    src = _make_source(client)
    offers = src.search("", None)

    assert offers, "zero-offer fallback must return seed results"
    assert all(o.vertical == Vertical.ACTIVITY for o in offers)


# ---------------------------------------------------------------------------
# Test 5 — flight/hotel vertical in SCRAPE → returns seed (not scraped)
# ---------------------------------------------------------------------------


def test_flight_vertical_not_scraped():
    client = FakeClient(response_json=_GOOD_RESPONSE)
    # For FLIGHT there are no default targets; pass empty list explicitly
    _CACHE.clear()
    src = ScrapeSource(vertical=Vertical.FLIGHT, targets=[], client=client, ttl=900.0)
    offers = src.search("", None)

    assert client.call_count == 0, "Firecrawl must NOT be called for FLIGHT"
    assert offers, "must return seed flight offers"
    assert all(o.vertical == Vertical.FLIGHT for o in offers)


def test_hotel_vertical_not_scraped():
    client = FakeClient(response_json=_GOOD_RESPONSE)
    _CACHE.clear()
    src = ScrapeSource(vertical=Vertical.HOTEL, targets=[], client=client, ttl=900.0)
    offers = src.search("", None)

    assert client.call_count == 0, "Firecrawl must NOT be called for HOTEL"
    assert offers, "must return seed hotel offers"
    assert all(o.vertical == Vertical.HOTEL for o in offers)


# ---------------------------------------------------------------------------
# Test 6 — TTL cache: second search within TTL does NOT call client.scrape again
# ---------------------------------------------------------------------------


def test_ttl_cache_prevents_second_scrape():
    client = FakeClient(response_json=_GOOD_RESPONSE)
    src = _make_source(client, ttl=9999.0)

    first = src.search("", None)
    second = src.search("", None)

    assert client.call_count == 1, (
        f"scrape should be called once (got {client.call_count}); "
        "second search should hit the TTL cache"
    )
    assert first == second


# ---------------------------------------------------------------------------
# Integration: make_source with SCRAPE mode creates a ScrapeSource
# ---------------------------------------------------------------------------


def test_make_source_scrape_mode(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SCRAPE")
    from odyssey.data.scrape import ScrapeSource
    from odyssey.merchants.sources import make_source

    src = make_source(Vertical.ACTIVITY)
    assert isinstance(src, ScrapeSource)


def test_make_source_scrape_falls_back_without_key(monkeypatch):
    """With mode=SCRAPE and no API key, the source must still return seed offers."""
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SCRAPE")
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    _CACHE.clear()

    from odyssey.merchants.sources import make_source

    src = make_source(Vertical.ACTIVITY)
    # Inject a client that immediately raises (simulates missing key)
    src._client = FakeClient(raise_exc=Exception("no API key"))
    offers = src.search("", None)

    assert offers, "must fall back to seed when scrape fails (no key)"
