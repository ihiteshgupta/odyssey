"""Regression tests for the code-review security/correctness fixes.

Each test pins a specific finding so the hole can't silently reopen. Runs fully
offline in SEED mode (no Gemini key, no network).
"""
from __future__ import annotations

import hashlib
import json

import pytest

from odyssey.common.types import Intent, Money, Vertical
from odyssey.protocols import ap2_adapter as ap2
from odyssey.protocols.ap2_adapter import (
    build_cart_mandate,
    build_payment_mandate,
    verify_cart_mandate,
    verify_payment_mandate,
)


# ── #1 signature downgrade / algorithm confusion ──────────────────────────────
def test_ecdsa_mode_rejects_keyless_stub_signature():
    """A correctly-computed keyless STUB-SIG (which an attacker can build from the
    public cart fields returned by create_checkout) must NOT verify in ECDSA mode."""
    cm = build_cart_mandate("c1", "X", Money("USD", 10.0), "Y", 15)
    payload = ap2._cart_payload(cm)
    forged = ap2.STUB_PREFIX + hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()
    assert forged == ap2._stub_sign(payload)  # this is a *valid* stub signature
    cm.merchant_authorization = forged
    assert verify_cart_mandate(cm) is False  # ...yet rejected: verify is pinned to ECDSA


# ── #5 user signature must bind the payment mandate's own total ───────────────
def test_tampered_payment_total_fails_verification():
    cm = build_cart_mandate("c1", "X", Money("USD", 10.0), "Y", 15)
    pm = build_payment_mandate(cart=cm, merchant_agent="hotel_merchant")
    pm.payment_mandate_contents.payment_details_total.amount.value = 999999.0
    assert verify_payment_mandate(pm, cart=cm) is False


# ── #6 signed cart payload must bind the item label ───────────────────────────
def test_tampered_cart_label_fails_verification():
    cm = build_cart_mandate("c1", "X", Money("USD", 10.0), "Economy seat", 15)
    cm.contents.payment_request.details.total.label = "First class suite + champagne"
    assert verify_cart_mandate(cm) is False


def test_valid_payment_mandate_still_verifies():
    cm = build_cart_mandate("c1", "Bali Beach Resort", Money("USD", 640.0), "Hotel", 15)
    pm = build_payment_mandate(cart=cm, merchant_agent="hotel_merchant")
    assert verify_payment_mandate(pm, cart=cm) is True


# ── #2 guardrail must trust the SIGNED total, and fail closed ─────────────────
class _Tool:
    def __init__(self, name):
        self.name = name


class _Ctx:
    def __init__(self, state):
        self.state = state


def _guard(name, state):
    from odyssey.concierge.guardrail import before_tool_callback

    return before_tool_callback(_Tool(name), {}, _Ctx(state))


def test_guardrail_uses_signed_total_over_recorded_price():
    """A merchant-signed cart total of 3000 must be caught even when the recorded
    negotiation price lies low (100) under a 2500 budget."""
    cm = build_cart_mandate("c1", "M", Money("USD", 3000.0), "Hotel", 15).model_dump()
    state = {
        "cart_mandates": [{"price": 100.0, "cart_mandate": cm}],
        "total_budget": 2500.0,
        "budget_currency": "USD",
    }
    res = _guard("complete_trip", state)
    assert res is not None and "budget" in str(res).lower()


def test_guardrail_fails_closed_on_unverifiable_amount():
    res = _guard("complete_trip", {"cart_mandates": [{}], "total_budget": 2500.0})
    assert res is not None and res.get("denied") is True


def test_guardrail_denies_currency_mismatch():
    state = {
        "cart_mandates": [{"price": 100.0, "currency": "EUR"}],
        "total_budget": 2500.0,
        "budget_currency": "USD",
    }
    res = _guard("complete_trip", state)
    assert res is not None and "currency" in str(res).lower()


# ── #11 float-money comparison must not deny a within-budget cart ─────────────
def test_guardrail_no_float_drift_false_denial():
    # 18.42 + 19.35 + 26.69 == 64.46 exactly in cents; bare-float sum is 64.4600000…1
    state = {
        "cart_mandates": [{"price": 18.42}, {"price": 19.35}, {"price": 26.69}],
        "total_budget": 64.46,
    }
    assert _guard("complete_trip", state) is None  # allowed (was wrongly denied by >)


# ── #4 idempotency: cancel then complete with same key must NOT confirm ───────
from ap2.models.mandate import CartMandate  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from odyssey.data.seed import seeded_source  # noqa: E402
from odyssey.merchants.ucp_server import make_ucp_app  # noqa: E402

_client = TestClient(make_ucp_app("H", Vertical.HOTEL, seeded_source(Vertical.HOTEL)))


def _rpc(name, arguments):
    return _client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": name, "arguments": arguments}},
    ).json()["result"]


def _new_checkout():
    found = _rpc("search_catalog", {"query": "bali"})["products"]
    created = _rpc("create_checkout", {"meta": {"ucp-agent": "t"},
                                       "checkout": {"items": [{"id": found[0]["id"]}]}})
    return created["checkout"]


def test_cancel_then_complete_same_key_is_not_confirmed():
    checkout = _new_checkout()
    cid = checkout["id"]
    cm = CartMandate.model_validate(checkout["cart_mandate"])
    pm = build_payment_mandate(cart=cm, merchant_agent="hotel_merchant")
    _rpc("cancel_checkout", {"meta": {"ucp-agent": "t", "idempotency-key": "shared"}, "id": cid})
    res = _rpc("complete_checkout", {"meta": {"ucp-agent": "t", "idempotency-key": "shared"},
                                     "id": cid, "checkout": {"payment_mandate": pm.model_dump()}})
    assert res.get("error"), f"canceled key replayed as: {res}"
    assert res.get("order", {}).get("status") != "confirmed"


def test_forged_keyless_stub_rejected_end_to_end():
    """The headline attack: an anonymous client reconstructs a VALID keyless stub
    signature from the public cart fields and submits it to complete_checkout. The
    ECDSA-pinned verifier must reject it (was previously confirmed)."""
    checkout = _new_checkout()
    cid = checkout["id"]
    cm = CartMandate.model_validate(checkout["cart_mandate"])
    pm = build_payment_mandate(cart=cm, merchant_agent="hotel_merchant")
    # forge user_authorization with a keyless SHA-256 stub over the real signed payload
    payload = ap2._payment_payload(cm, pm.payment_mandate_contents)
    pm.user_authorization = ap2.STUB_PREFIX + hashlib.sha256(
        json.dumps(payload, sort_keys=True).encode()
    ).hexdigest()
    res = _rpc("complete_checkout", {"meta": {"ucp-agent": "atk", "idempotency-key": "atk1"},
                                     "id": cid, "checkout": {"payment_mandate": pm.model_dump()}})
    assert res.get("error") == "mandate verification failed"


# ── #15 create_checkout with an unknown id returns a clean error (no 500) ──────
def test_create_checkout_unknown_id_returns_error():
    res = _rpc("create_checkout", {"meta": {"ucp-agent": "t"},
                                   "checkout": {"items": [{"id": "does-not-exist"}]}})
    assert "error" in res


# ── #7 UCP mutating ops require the shared-secret token when configured ───────
def test_ucp_token_enforced_when_configured(monkeypatch):
    monkeypatch.setenv("ODYSSEY_UCP_TOKEN", "s3cret")
    app = TestClient(make_ucp_app("H", Vertical.HOTEL, seeded_source(Vertical.HOTEL)))

    def rpc(name, args):
        return app.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                  "params": {"name": name, "arguments": args}},
        ).json()["result"]

    # mutating op WITHOUT the token → unauthorized
    blocked = rpc("create_checkout", {"meta": {"ucp-agent": "t"},
                                      "checkout": {"items": [{"id": "seed-hotel-1"}]}})
    assert "unauthorized" in blocked.get("error", "")
    # mutating op WITH the correct token → allowed
    ok = rpc("create_checkout", {"meta": {"ucp-agent": "t", "ucp-token": "s3cret"},
                                 "checkout": {"items": [{"id": "seed-hotel-1"}]}})
    assert ok["checkout"]["id"].startswith("ck-")
    # read op stays open (token gate is only for state-changing ops)
    assert rpc("search_catalog", {"query": "bali"})["products"]


# ── #8 finalize_trip enforces budget at the spend boundary ────────────────────
def test_finalize_refuses_over_budget(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    for v in ("FLIGHT", "HOTEL", "ACTIVITY"):
        monkeypatch.delenv(f"ODYSSEY_{v}_URL", raising=False)
    from odyssey.concierge.agent import finalize_trip, plan_trip

    plan = plan_trip("DPS", "JFK", "2026-09-01", "2026-09-06", 2, 2500.0, ["beachy"])
    out = finalize_trip(plan["_carts"], total_budget=10.0, budget_currency="USD")
    assert out["status"] == "refused" and "budget" in out["reason"].lower()


# ── #10 incomplete A2A response degrades (or, STRICT, surfaces) — no KeyError ──
import odyssey.concierge.negotiate as neg  # noqa: E402

_INTENT = Intent("JFK", "DPS", "2026-09-01", "2026-09-06", 2, Money("USD", 2500.0), ["beachy"])


@pytest.fixture
def _force_a2a(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    monkeypatch.setattr(neg, "merchant_url", lambda _v: "https://merchant.example")
    monkeypatch.setattr(neg, "A2A_MAX_ATTEMPTS", 1)
    monkeypatch.setattr(neg.time, "sleep", lambda *_a, **_k: None)


def test_incomplete_a2a_response_degrades(_force_a2a, monkeypatch):
    monkeypatch.setattr(neg, "A2A_STRICT", False)
    # offers present but fits/cheapest missing → must NOT crash on raw["fits"]/["cheapest"]
    monkeypatch.setattr(
        neg, "_a2a_request_offers",
        lambda *a, **k: {"offers": [
            {"id": "x", "vertical": "hotel", "title": "T", "price": {"currency": "USD", "value": 500.0}}
        ]},
    )
    resp = neg.request_offers(Vertical.HOTEL, _INTENT, slice_amount=700.0)
    assert resp.fits is True and resp.offers  # degraded to in-process SEED


def test_incomplete_a2a_response_strict_raises(_force_a2a, monkeypatch):
    monkeypatch.setattr(neg, "A2A_STRICT", True)
    monkeypatch.setattr(neg, "_a2a_request_offers", lambda *a, **k: {"offers": []})
    with pytest.raises(ValueError, match="missing keys"):
        neg.request_offers(Vertical.HOTEL, _INTENT, slice_amount=700.0)
