from __future__ import annotations

from odyssey.protocols.ap2_adapter import cart_total

CHECKOUT_TOOLS = {"complete_trip", "complete_purchase", "complete_checkout"}


def _entry_amount_currency(entry: dict) -> tuple[float | None, str | None]:
    """Authoritative ``(amount, currency)`` for one cart entry.

    Prefers the cryptographically signed ``CartMandate`` total over the
    concierge-recorded ``price`` (the two can drift in LIVE mode or under a
    malicious merchant). Returns ``(None, None)`` when neither is usable so the
    caller can fail closed instead of silently treating it as $0.
    """
    cm = entry.get("cart_mandate")
    if isinstance(cm, dict):
        try:
            return cart_total(cm)
        except (KeyError, TypeError, ValueError):
            return (None, None)
    price = entry.get("price")
    if isinstance(price, (int, float)) and not isinstance(price, bool):
        return (float(price), entry.get("currency"))
    return (None, None)


def before_tool_callback(tool, args, tool_context):
    """Deny-by-default gate. Return None to proceed, a dict to SHORT-CIRCUIT (deny).

    Blocks any checkout tool when no cart mandates are in session state, and denies a
    checkout whose total exceeds the user's budget. Spend is derived from the SIGNED
    cart total (not the recorded negotiation price), compared in integer minor units,
    and currency-matched against the budget — and the gate fails closed on any missing
    budget / amount / currency.
    """
    name = getattr(tool, "name", "")
    state = getattr(tool_context, "state", {}) or {}
    if name not in CHECKOUT_TOOLS:
        return None
    if not state.get("cart_mandates"):
        return {"denied": True, "reason": f"deny: {name} requires an assembled cart"}

    amounts: list[float] = []
    currencies: list[str | None] = []
    for entry in state.get("cart_mandates", []):
        amount, currency = _entry_amount_currency(entry)
        # Fail closed: a cart entry whose amount we cannot determine must not pass the
        # gate (previously a missing 'price' silently counted as $0.00).
        if amount is None:
            return {
                "denied": True,
                "reason": "deny: cart entry with no verifiable amount (fail-closed)",
            }
        amounts.append(amount)
        currencies.append(currency)

    # Currency must match the budget currency when both are known — bare-float summing
    # across currencies (e.g. EUR offers vs a USD budget) is meaningless.
    budget_currency = state.get("budget_currency")
    if budget_currency is not None:
        mismatched = [c for c in currencies if c is not None and c != budget_currency]
        if mismatched:
            return {
                "denied": True,
                "reason": (
                    f"deny: cart currency {mismatched[0]} != "
                    f"budget currency {budget_currency}"
                ),
            }

    budget = state.get("total_budget")
    if budget is None:
        return {
            "denied": True,
            "reason": "deny: missing total_budget, cannot verify budget",
        }

    # Compare in integer minor units to avoid float-accumulation drift across 2dp amounts.
    spent = round(sum(amounts), 2)
    if int(round(spent * 100)) > int(round(float(budget) * 100)):
        return {
            "denied": True,
            "reason": f"deny: cart total {spent} exceeds budget {budget}",
        }

    return None
