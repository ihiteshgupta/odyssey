"""Tests that each merchant's A2A agent card advertises its public Cloud Run URL
when the ODYSSEY_*_URL environment variable is set at import time.
"""

from __future__ import annotations

import importlib

from starlette.testclient import TestClient


def test_card_advertises_public_url_when_env_set(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    monkeypatch.setenv("ODYSSEY_HOTEL_URL", "https://odyssey-hotel-demo.example.run.app")
    import odyssey.merchants.agents as agents

    importlib.reload(agents)  # rebuild module-level apps with the env var present
    try:
        with TestClient(agents.hotel_app) as client:
            card = client.get("/.well-known/agent-card.json").json()
            assert card["url"].rstrip("/") == "https://odyssey-hotel-demo.example.run.app"
    finally:
        monkeypatch.delenv("ODYSSEY_HOTEL_URL", raising=False)
        importlib.reload(agents)  # restore default module state for other tests


def test_card_uses_default_url_when_env_not_set(monkeypatch):
    """Without ODYSSEY_*_URL the card url should be the local host:port default."""
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    monkeypatch.delenv("ODYSSEY_HOTEL_URL", raising=False)

    import odyssey.merchants.agents as agents
    from odyssey.common.types import Vertical

    app = agents.make_merchant_app(Vertical.HOTEL, port=8002)
    with TestClient(app) as client:
        card = client.get("/.well-known/agent-card.json").json()
        # Default url built by to_a2a includes localhost:8002
        assert "localhost" in card["url"] or "8002" in card["url"]
