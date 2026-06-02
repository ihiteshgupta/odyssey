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
    return None
