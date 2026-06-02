from starlette.testclient import TestClient

from odyssey.common.types import Vertical
from odyssey.merchants.agents import make_merchant_app, negotiate_offers


def test_negotiate_offers_fit(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    resp = negotiate_offers(Vertical.HOTEL, query="bali", budget_slice=700.0)
    assert resp["fits"] is True and resp["cheapest"] <= 700.0 and resp["offers"]


def test_negotiate_offers_no_fit(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    resp = negotiate_offers(Vertical.HOTEL, query="bali", budget_slice=100.0)
    assert resp["fits"] is False and resp["nearest_above"] == 640.0


def test_merchant_serves_card_and_ucp(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    # A2A routes are registered during lifespan startup; use context manager to trigger it.
    with TestClient(make_merchant_app(Vertical.HOTEL, port=8002)) as client:
        assert client.get("/.well-known/agent-card.json").status_code == 200
        assert "dev.ucp.shopping.checkout" in client.get("/.well-known/ucp").json()["ucp"]["capabilities"]
