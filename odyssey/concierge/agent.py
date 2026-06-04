from __future__ import annotations

import logging
import os

from ap2.models.mandate import CartMandate
from google.adk.agents import LlmAgent
from google.adk.agents.remote_a2a_agent import AGENT_CARD_WELL_KNOWN_PATH, RemoteA2aAgent
from google.adk.tools import FunctionTool
from google.adk.tools.agent_tool import AgentTool

from odyssey.common.types import Intent, Money, Offer, Vertical
from odyssey.concierge.clients import merchant_url, ucp_client_for
from odyssey.concierge.guardrail import before_tool_callback
from odyssey.concierge.negotiate import request_offers
from odyssey.concierge.policy import allocate, reallocate
from odyssey.protocols.ap2_adapter import build_intent_mandate, build_payment_mandate, cart_total

MODEL = "gemini-3.5-flash"
MAX_ROUNDS = 3
log = logging.getLogger("odyssey.concierge")


def _ucp_meta(base: dict) -> dict:
    """Attach the shared-secret UCP token to a request's meta when one is configured
    (ODYSSEY_UCP_TOKEN). No-op otherwise, so local/SEED demos need no token."""
    token = os.environ.get("ODYSSEY_UCP_TOKEN")
    return {**base, "ucp-token": token} if token else base



_VERTS = (Vertical.FLIGHT, Vertical.HOTEL, Vertical.ACTIVITY)
_DEFAULT_PORT = {"flight": 8001, "hotel": 8002, "activity": 8003}


# ---- retained spike agent (tests/test_hitl_guardrail_spike.py) ----
def _search_offers() -> dict:
    """Search demo offers. Always allowed."""
    return {"offers": [{"id": "demo-1", "title": "Demo item", "price": "10.00 USD"}]}


def _complete_purchase_demo(offer_id: str) -> dict:
    """Book the selected offer (demo). Requires explicit human confirmation."""
    return {"status": "confirmed", "offer_id": offer_id, "note": "SIMULATED — no real charge"}


def build_spike_agent() -> LlmAgent:
    return LlmAgent(
        name="odyssey_spike",
        model=MODEL,
        instruction="Demo. search_offers then complete_purchase. Never book without searching.",
        tools=[
            FunctionTool(_search_offers),
            FunctionTool(_complete_purchase_demo, require_confirmation=True),
        ],
        before_tool_callback=before_tool_callback,
    )


# ---- real concierge logic ----
def plan_trip(
    destination: str,
    origin: str,
    start: str,
    end: str,
    party_size: int,
    total_budget: float,
    prefs: list[str],
    tool_context=None,
) -> dict:
    """Build the AP2 IntentMandate, negotiate offers over A2A, assemble a trip cart via each
    merchant's create_checkout. Writes cart_mandates + total_budget into session state when
    tool_context is present."""
    intent = Intent(
        origin,
        destination,
        start,
        end,
        party_size,
        Money("USD", float(total_budget)),
        list(prefs),
    )
    im = build_intent_mandate(
        f"{start}..{end} trip to {destination} from {origin} for {party_size}, "
        f"budget {total_budget} USD, prefs: {', '.join(prefs) or 'none'}"
    )
    log.info("intent: %s", im.natural_language_description)
    budget_currency = intent.total_budget.currency
    slices = allocate(intent)
    # `chosen` is reset EACH round: it must hold offers that all fit under ONE
    # consistent budget allocation, never a mix of offers selected under different
    # (earlier, larger) slices that were never jointly validated as feasible.
    chosen: dict[Vertical, Offer] = {}
    for rnd in range(MAX_ROUNDS):
        needs, ok, chosen = {}, True, {}
        for v in _VERTS:
            resp = request_offers(v, intent, slices[v], context_id=f"{destination}-{start}")
            needs[v] = resp.cheapest.amount
            log.info(
                "round %d %s slice=%.0f fits=%s cheapest=%.0f",
                rnd,
                v.value,
                slices[v],
                resp.fits,
                resp.cheapest.amount,
            )
            if resp.fits and resp.offers:
                chosen[v] = min(resp.offers, key=lambda o: float(o.price.amount))
            else:
                ok = False
        if ok and len(chosen) == 3:
            break
        slices = reallocate(slices, needs, total=float(total_budget))
    carts, items = [], []
    currency_mismatch = False
    for v, offer in chosen.items():
        uc = ucp_client_for(v)
        created = uc.call(
            "create_checkout",
            {
                "meta": _ucp_meta({"ucp-agent": "odyssey"}),
                "checkout": {"items": [{"id": offer.id}]},
            },
        )["checkout"]
        cart_md = created["cart_mandate"]
        # Budget against the SIGNED cart total (what is actually charged), not the
        # negotiated offer price — the two can drift in LIVE mode / under a bad merchant.
        signed_amount, signed_currency = cart_total(cart_md)
        if signed_currency != budget_currency:
            currency_mismatch = True
        carts.append(
            {
                "vertical": v.value,
                "offer_id": offer.id,
                "title": offer.title,
                "price": signed_amount,
                "currency": signed_currency,
                "checkout_id": created["id"],
                "cart_mandate": cart_md,
                "merchant_agent": f"{v.value}_merchant",
            }
        )
        items.append(
            {
                "vertical": v.value,
                "title": offer.title,
                "price": signed_amount,
                "currency": signed_currency,
                "cart_mandate": cart_md,
            }
        )
    total = round(sum(c["price"] for c in carts), 2)
    within = (
        not currency_mismatch
        and len(items) == 3
        and int(round(total * 100)) <= int(round(float(total_budget) * 100))
    )
    if tool_context is not None:
        tool_context.state["cart_mandates"] = carts
        tool_context.state["total_budget"] = float(total_budget)
        tool_context.state["budget_currency"] = budget_currency
    return {
        "within_budget": within,
        "total": total,
        "items": items,
        "_carts": carts,
    }


def finalize_trip(
    carts: list[dict],
    total_budget: float | None = None,
    budget_currency: str | None = None,
) -> dict:
    """Issue user-signed PaymentMandates and book each item through its merchant's
    complete_checkout UCP op.

    Defense in depth: when a budget is supplied, the spend is re-checked HERE — at the
    function that actually authorizes payment — against the SIGNED cart totals, so the
    budget invariant doesn't rely solely on the name-keyed before_tool_callback gate.
    """
    if not carts:
        return {"status": "refused", "reason": "no assembled cart"}
    if total_budget is not None:
        amounts: list[float] = []
        for c in carts:
            try:
                amount, currency = cart_total(c["cart_mandate"])
            except (KeyError, TypeError, ValueError):
                return {"status": "refused", "reason": "cart with no verifiable amount"}
            if budget_currency is not None and currency != budget_currency:
                return {
                    "status": "refused",
                    "reason": f"currency mismatch: {currency} != {budget_currency}",
                }
            amounts.append(amount)
        spent = round(sum(amounts), 2)
        if int(round(spent * 100)) > int(round(float(total_budget) * 100)):
            return {
                "status": "refused",
                "reason": f"cart total {spent} exceeds budget {total_budget}",
            }
    confirmations = []
    for c in carts:
        cm = CartMandate.model_validate(c["cart_mandate"])
        pm = build_payment_mandate(cart=cm, merchant_agent=c["merchant_agent"])
        uc = ucp_client_for(Vertical(c["vertical"]))
        try:
            res = uc.call(
                "complete_checkout",
                {
                    "meta": _ucp_meta(
                        {"ucp-agent": "odyssey", "idempotency-key": c["checkout_id"]}
                    ),
                    "id": c["checkout_id"],
                    "checkout": {"payment_mandate": pm.model_dump()},
                },
            )
        except RuntimeError as e:  # UCP transport / dispatch error surfaced by the client
            return {"status": "error", "reason": str(e), "vertical": c["vertical"]}
        order = res.get("order", {})
        if order.get("status") != "confirmed":
            return {
                "status": "error",
                "reason": res.get("error", "checkout failed"),
                "vertical": c["vertical"],
            }
        confirmations.append(
            {"vertical": c["vertical"], "confirmation": order["confirmation"]}
        )
    return {
        "status": "confirmed",
        "confirmations": confirmations,
        "note": "SIMULATED booking — no real money moved",
    }


def complete_trip(tool_context) -> dict:
    """Book all assembled items. Gated by require_confirmation + guardrail.
    Reads carts + budget from session state and re-checks budget at the spend boundary."""
    state = tool_context.state
    return finalize_trip(
        carts=state.get("cart_mandates", []),
        total_budget=state.get("total_budget"),
        budget_currency=state.get("budget_currency"),
    )


def _remote_merchant(vertical: Vertical) -> AgentTool:
    url = merchant_url(vertical) or f"http://localhost:{_DEFAULT_PORT[vertical.value]}"
    remote = RemoteA2aAgent(
        name=f"{vertical.value}_merchant",
        description=f"{vertical.value} merchant agent",
        agent_card=f"{url.rstrip('/')}{AGENT_CARD_WELL_KNOWN_PATH}",
        use_legacy=False,
    )
    return AgentTool(agent=remote)


def build_concierge() -> LlmAgent:
    return LlmAgent(
        name="odyssey_concierge",
        model=MODEL,
        instruction=(
            "You are Odyssey, a travel concierge. Collect origin, destination, dates, "
            "party size, total budget, and preferences. Call plan_trip to assemble a "
            "flight+hotel+activities itinerary within budget. Show the full itinerary and "
            "grand total, then ask the user to confirm. ONLY after they confirm, call "
            "complete_trip to book everything. If plan_trip is not within_budget, tell the "
            "user the closest fit and ask them to relax ONE constraint (budget or dates). "
            "Never claim a booking before complete_trip returns status 'confirmed'."
        ),
        tools=[
            FunctionTool(plan_trip),
            FunctionTool(complete_trip, require_confirmation=True),
            _remote_merchant(Vertical.FLIGHT),
            _remote_merchant(Vertical.HOTEL),
            _remote_merchant(Vertical.ACTIVITY),
        ],
        before_tool_callback=before_tool_callback,
    )


root_agent = build_concierge()
