from odyssey.common.types import Intent, Money, Vertical
from odyssey.concierge.policy import allocate, reallocate

INTENT = Intent("JFK", "DPS", "2026-09-01", "2026-09-06", 2, Money("USD", 2500.0), ["foodie"])


def test_allocate_sums_to_total():
    s = allocate(INTENT)
    assert set(s) == {Vertical.FLIGHT, Vertical.HOTEL, Vertical.ACTIVITY}
    assert abs(sum(s.values()) - 2500.0) < 1e-6


def test_reallocate_shifts_to_overspent():
    slices = {Vertical.FLIGHT: 1100.0, Vertical.HOTEL: 1000.0, Vertical.ACTIVITY: 400.0}
    needs = {Vertical.FLIGHT: 900.0, Vertical.HOTEL: 1200.0, Vertical.ACTIVITY: 380.0}
    fixed = reallocate(slices, needs, total=2500.0)
    assert fixed[Vertical.HOTEL] >= 1200.0 and abs(sum(fixed.values()) - 2500.0) < 1e-6
