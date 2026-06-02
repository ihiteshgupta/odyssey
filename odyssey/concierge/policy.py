from __future__ import annotations

from odyssey.common.types import Intent, Vertical


def allocate(intent: Intent) -> dict[Vertical, float]:
    """Split intent.total_budget.amount across the 3 verticals.

    The returned values MUST sum to the total.
    DESIGN CHOICE (yours): proportional (e.g. flight 45% / hotel 40% / activities 15%)
    vs preference-weighted (read intent.prefs, e.g. 'foodie' -> more to activities).
    """
    raise NotImplementedError("TODO(you): implement budget allocation")


def reallocate(
    slices: dict[Vertical, float],
    needs: dict[Vertical, float],
    total: float,
) -> dict[Vertical, float]:
    """Shift budget from verticals with slack to overspent ones.

    Given current per-vertical slices and each vertical's actual cheapest 'need',
    return adjusted slices where sum(result) == total.
    DESIGN CHOICE (yours): how aggressively to shift; what to do if sum(needs) > total
    (return best feasible).
    """
    raise NotImplementedError("TODO(you): implement budget reallocation")
