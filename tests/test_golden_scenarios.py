import pytest

from odyssey.concierge.agent import finalize_trip, plan_trip


@pytest.fixture(autouse=True)
def seed(monkeypatch):
    monkeypatch.setenv("ODYSSEY_DATA_MODE", "SEED")
    for v in ("FLIGHT", "HOTEL", "ACTIVITY"):
        monkeypatch.delenv(f"ODYSSEY_{v}_URL", raising=False)

def test_in_budget_books_three():
    plan = plan_trip("DPS", "JFK", "2026-09-01", "2026-09-06", 2, 2500.0, ["beachy"])
    assert plan["within_budget"] and len(plan["items"]) == 3
    out = finalize_trip(plan["_carts"])
    assert out["status"] == "confirmed" and len(out["confirmations"]) == 3

def test_tight_budget_flags():
    plan = plan_trip("DPS", "JFK", "2026-09-01", "2026-09-06", 2, 700.0, [])
    assert plan["within_budget"] is False

def test_zero_real_charges():
    plan = plan_trip("DPS", "JFK", "2026-09-01", "2026-09-06", 2, 2500.0, [])
    out = finalize_trip(plan["_carts"])
    assert "SIMULATED" in out["note"]
