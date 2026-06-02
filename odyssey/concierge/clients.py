from __future__ import annotations

import os

import httpx
from fastapi.testclient import TestClient as _UcpTestClient

from odyssey.common.types import Vertical
from odyssey.merchants.sources import make_source
from odyssey.merchants.ucp_server import make_ucp_app
from odyssey.protocols.ucp_client import UCPClient

_URL_ENV = {
    Vertical.FLIGHT: "ODYSSEY_FLIGHT_URL",
    Vertical.HOTEL: "ODYSSEY_HOTEL_URL",
    Vertical.ACTIVITY: "ODYSSEY_ACTIVITY_URL",
}


def merchant_url(vertical: Vertical) -> str | None:
    return os.environ.get(_URL_ENV[vertical])


def ucp_client_for(vertical: Vertical) -> UCPClient:
    """Return a UCPClient for the merchant.

    Uses an httpx client to the live merchant URL if set and reachable, otherwise falls back to
    an in-process UCP app (suitable for tests and SEED mode demos).
    """
    url = merchant_url(vertical)
    if url:
        try:
            t = httpx.Client(base_url=url.rstrip("/"), timeout=10.0)
            t.get("/.well-known/ucp").raise_for_status()
            return UCPClient(transport=t)
        except Exception:
            pass
    return UCPClient(
        transport=_UcpTestClient(
            make_ucp_app(f"{vertical.value} merchant", vertical, make_source(vertical))
        )
    )
