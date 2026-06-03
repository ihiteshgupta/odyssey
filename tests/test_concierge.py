import pytest

from odyssey.concierge.agent import finalize_trip, plan_trip


@pytest.fixture(autouse=True)
def seed(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    for v in ("FLIGHT", "HOTEL", "ACTIVITY"):
        monkeypatch.delenv(f"ODYSSEY_{v}_URL", raising=False)   # in-process negotiation + UCP


def test_plan_trip_in_budget():
    plan = plan_trip(destination="DPS", origin="JFK", start="2026-09-01", end="2026-09-06",
                     party_size=2, total_budget=2500.0, prefs=["beachy"])
    assert plan["within_budget"] is True
    assert {i["vertical"] for i in plan["items"]} == {"flight", "hotel", "activity"}
    assert plan["total"] <= 2500.0
    assert all(i["cart_mandate"]["merchant_authorization"].startswith("ECDSA-P256:") for i in plan["items"])


def test_finalize_refuses_without_carts():
    assert finalize_trip(carts=[])["status"] == "refused"


def test_finalize_books_via_ucp():
    plan = plan_trip(destination="DPS", origin="JFK", start="2026-09-01", end="2026-09-06",
                     party_size=2, total_budget=2500.0, prefs=["beachy"])
    out = finalize_trip(carts=plan["_carts"])
    assert out["status"] == "confirmed" and len(out["confirmations"]) == 3
    assert all(c["confirmation"].startswith("OD-") for c in out["confirmations"])
    assert out["note"].startswith("SIMULATED")
