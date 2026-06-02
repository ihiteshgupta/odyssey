from __future__ import annotations

from odyssey.common.types import Intent, Vertical


def allocate(intent: Intent) -> dict[Vertical, float]:
    """Split intent.total_budget.amount across the 3 verticals.

    Proportional split: FLIGHT 45%, HOTEL 40%, ACTIVITY 15%.
    The ACTIVITY slice absorbs any floating-point remainder so sum == total exactly.
    """
    total = intent.total_budget.amount
    flight = round(total * 0.45, 2)
    hotel = round(total * 0.40, 2)
    activity = round(total - flight - hotel, 2)
    return {
        Vertical.FLIGHT: flight,
        Vertical.HOTEL: hotel,
        Vertical.ACTIVITY: activity,
    }


def reallocate(
    slices: dict[Vertical, float],
    needs: dict[Vertical, float],
    total: float,
) -> dict[Vertical, float]:
    """Shift budget from verticals with slack to overspent ones.

    Each vertical receives at least its stated need as a floor; any remaining
    budget is distributed proportionally to the original slice weights.
    If sum(needs) > total the needs are scaled down to fit (best-feasible).
    Sum of result == total (within float tolerance).
    """
    need_sum = sum(needs.values())
    if need_sum > total and need_sum > 0:
        # Infeasible: scale all needs down proportionally so sum == total
        return {v: round(needs[v] / need_sum * total, 2) for v in slices}

    leftover = total - need_sum
    slice_sum = sum(slices.values()) or 1.0
    out = {
        v: round(needs[v] + leftover * (slices[v] / slice_sum), 2)
        for v in slices
    }
    # Fix any rounding drift so sum is exact
    drift = round(total - sum(out.values()), 2)
    first = next(iter(out))
    out[first] = round(out[first] + drift, 2)
    return out
