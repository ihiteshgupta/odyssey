import pytest
from fastapi.testclient import TestClient

from odyssey.common.types import Vertical
from odyssey.data.seed import seeded_source
from odyssey.merchants.ucp_server import make_ucp_app
from odyssey.protocols.ucp_client import UCPClient


@pytest.fixture
def uc():
    app = make_ucp_app("H", Vertical.HOTEL, seeded_source(Vertical.HOTEL))
    return UCPClient(transport=TestClient(app))


def test_discover_then_search(uc):
    assert "dev.ucp.shopping.checkout" in uc.discover()
    products = uc.call("search_catalog", {"query": "bali"})["products"]
    assert any("Bali" in p["title"] for p in products)


def test_create_checkout(uc):
    res = uc.call("create_checkout", {"meta": {"ucp-agent": "x"}, "checkout": {"items": [{"id": "seed-hotel-1"}]}})
    assert res["checkout"]["id"].startswith("ck-")
