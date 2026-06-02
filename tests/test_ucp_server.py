from ap2.models.mandate import CartMandate
from fastapi.testclient import TestClient

from odyssey.common.types import Vertical
from odyssey.data.seed import seeded_source
from odyssey.merchants.ucp_server import make_ucp_app
from odyssey.protocols.ap2_adapter import build_payment_mandate

client = TestClient(make_ucp_app("Bali Beach Resort", Vertical.HOTEL, seeded_source(Vertical.HOTEL)))


def _rpc(name, arguments, rid=1):
    return client.post("/mcp", json={"jsonrpc": "2.0", "id": rid, "method": "tools/call",
                                     "params": {"name": name, "arguments": arguments}}).json()


def test_well_known_lists_capabilities():
    doc = client.get("/.well-known/ucp").json()
    assert "dev.ucp.shopping.checkout" in doc["ucp"]["capabilities"]


def test_create_then_complete_with_valid_mandate():
    found = _rpc("search_catalog", {"query": "bali", "filters": {"max_price": 1000}})["result"]["products"]
    assert found
    created = _rpc("create_checkout", {"meta": {"ucp-agent": "t"},
                                       "checkout": {"items": [{"id": found[0]["id"]}]}})["result"]
    cid = created["checkout"]["id"]
    cm = CartMandate.model_validate(created["checkout"]["cart_mandate"])
    pm = build_payment_mandate(cart=cm, merchant_agent="hotel_merchant")
    done = _rpc("complete_checkout", {"meta": {"ucp-agent": "t", "idempotency-key": "k1"},
                                      "id": cid, "checkout": {"payment_mandate": pm.model_dump()}})["result"]
    assert done["order"]["status"] == "confirmed"


def test_complete_rejects_tampered_mandate():
    found = _rpc("search_catalog", {"query": "bali"})["result"]["products"]
    created = _rpc("create_checkout", {"meta": {"ucp-agent": "t"},
                                       "checkout": {"items": [{"id": found[0]["id"]}]}})["result"]
    cid = created["checkout"]["id"]
    cm = CartMandate.model_validate(created["checkout"]["cart_mandate"])
    pm = build_payment_mandate(cart=cm, merchant_agent="hotel_merchant")
    pm.user_authorization = "STUB-SIG:forged"
    bad = _rpc("complete_checkout", {"meta": {"ucp-agent": "t", "idempotency-key": "k2"},
                                     "id": cid, "checkout": {"payment_mandate": pm.model_dump()}})["result"]
    assert bad["error"] == "mandate verification failed"


def test_complete_requires_idempotency_key():
    found = _rpc("search_catalog", {"query": "bali"})["result"]["products"]
    created = _rpc("create_checkout", {"meta": {"ucp-agent": "t"},
                                       "checkout": {"items": [{"id": found[0]["id"]}]}})["result"]
    bad = _rpc("complete_checkout", {"meta": {"ucp-agent": "t"}, "id": created["checkout"]["id"],
                                     "checkout": {}})["result"]
    assert bad["error"] == "missing idempotency-key"


def test_complete_checkout_idempotent_replay_returns_confirmation():
    found = _rpc("search_catalog", {"query": "bali"})["result"]["products"]
    created = _rpc("create_checkout", {"meta": {"ucp-agent": "t"},
                                       "checkout": {"items": [{"id": found[0]["id"]}]}})["result"]
    cid = created["checkout"]["id"]
    cm = CartMandate.model_validate(created["checkout"]["cart_mandate"])
    pm = build_payment_mandate(cart=cm, merchant_agent="hotel_merchant")
    args = {"meta": {"ucp-agent": "t", "idempotency-key": "replay-key"},
            "id": cid, "checkout": {"payment_mandate": pm.model_dump()}}
    first = _rpc("complete_checkout", args)["result"]
    second = _rpc("complete_checkout", args)["result"]  # same key → replay
    assert first["order"]["status"] == "confirmed" and first["order"]["confirmation"].startswith("OD-")
    assert second["order"].get("idempotent_replay") is True
    assert second["order"]["confirmation"] == first["order"]["confirmation"]
