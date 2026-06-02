from __future__ import annotations

CHECKOUT_TOOLS = {"complete_trip", "complete_purchase", "complete_checkout"}


def before_tool_callback(tool, args, tool_context):
    """Deny-by-default gate. Return None to proceed, a dict to SHORT-CIRCUIT (deny).
    Spike version: block any checkout tool when no cart mandates are in session state.
    Extended in Task 14 (budget rule)."""
    name = getattr(tool, "name", "")
    state = getattr(tool_context, "state", {}) or {}
    if name in CHECKOUT_TOOLS and not state.get("cart_mandates"):
        return {"denied": True, "reason": f"deny: {name} requires an assembled cart"}

    # Budget rule (Task 14): for a checkout tool with an assembled cart, deny if it exceeds budget.
    # DESIGN CHOICE: fail-closed on missing total_budget — this is a payment gate, so we must not
    # allow a checkout to proceed when we cannot verify the spend is within the user's budget.
    if name in CHECKOUT_TOOLS:
        budget = state.get("total_budget")
        spent = sum(c.get("price", 0.0) for c in state.get("cart_mandates", []))
        if budget is None:
            return {
                "denied": True,
                "reason": "deny: missing total_budget, cannot verify budget",
            }
        if spent > budget:
            return {
                "denied": True,
                "reason": f"deny: cart total {spent} exceeds budget {budget}",
            }

    return None
