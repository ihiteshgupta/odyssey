from odyssey.common.types import Vertical
from odyssey.merchants.sources import make_source


def test_seed_mode(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    offers = make_source(Vertical.HOTEL).search("bali", 1000)
    assert offers and all(o.price.amount <= 1000 for o in offers)


def test_live_falls_back_on_error(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "LIVE")
    monkeypatch.setenv("AMADEUS_CLIENT_ID", "")    # force auth failure → fallback
    offers = make_source(Vertical.FLIGHT).search("anything", None)
    assert offers, "must fall back to seeded inventory"
