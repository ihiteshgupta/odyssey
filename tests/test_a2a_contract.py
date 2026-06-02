"""A2A DataPart contract test — Task 11.

Requires a live Gemini key (GOOGLE_API_KEY) to exercise the merchant LLM.
Without the key the test is skipped; collection must succeed unconditionally.
"""
import os

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("GOOGLE_API_KEY"),
    reason="needs Gemini key to run the merchant LLM",
)


@pytest.mark.asyncio
async def test_datapart_round_trip_against_live_merchant(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    import threading
    import time

    import httpx
    import uvicorn

    from odyssey.common.types import Intent, Money, Vertical
    from odyssey.concierge.a2a_client import a2a_negotiate
    from odyssey.merchants.agents import make_merchant_app

    app = make_merchant_app(Vertical.HOTEL, port=8092)
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=8092, log_level="error")
    )
    th = threading.Thread(target=server.run, daemon=True)
    th.start()

    for _ in range(50):
        try:
            httpx.get(
                "http://127.0.0.1:8092/.well-known/agent-card.json", timeout=1
            )
            break
        except Exception:
            time.sleep(0.1)

    try:
        intent = Intent(
            "JFK",
            "DPS",
            "2026-09-01",
            "2026-09-06",
            2,
            Money("USD", 2500.0),
            ["beachy"],
        )
        raw = a2a_negotiate(
            "http://127.0.0.1:8092",
            Vertical.HOTEL,
            intent,
            slice_amount=700.0,
            context_id="trip-1",
        )
        assert {"offers", "fits", "cheapest"}.issubset(raw.keys())
        assert isinstance(raw["fits"], bool)
    finally:
        server.should_exit = True
