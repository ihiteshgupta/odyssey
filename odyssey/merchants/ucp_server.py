from __future__ import annotations

import os
import uuid

from ap2.models.mandate import CartMandate, PaymentMandate  # noqa: F401 (used via model_validate)
from fastapi import FastAPI, Request
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse

from odyssey.common.types import Vertical
from odyssey.merchants.catalog_source import CatalogSource
from odyssey.protocols.ap2_adapter import (
    build_cart_mandate,
    build_payment_mandate,
    verify_payment_mandate,
)

# State-changing UCP ops require a shared-secret token WHEN one is configured via
# ODYSSEY_UCP_TOKEN. Opt-in so local/SEED demos and tests keep working with no token,
# but a deployed (publicly reachable) merchant can require it to stop anonymous booking.
_MUTATING_OPS = {"create_checkout", "complete_checkout", "cancel_checkout", "update_checkout"}


def build_dispatch(name: str, vertical: Vertical, source: CatalogSource):
    """Return a dispatch(op, args) -> dict closure with mutable per-merchant state.

    Factored out so Task 9 can attach the same handler to a combined A2A+UCP app.
    """
    carts: dict[str, dict] = {}
    # Idempotency records are namespaced per outcome so a cancel can never satisfy a
    # later complete (or vice versa). `completed` stores the confirmed order so a replay
    # returns the identical confirmation — and a key is only recorded AFTER its operation
    # succeeds (verification included).
    completed: dict[str, dict] = {}
    canceled_keys: set[str] = set()

    def _offer_dict(o):
        return {
            "id": o.id,
            "title": o.title,
            "vertical": o.vertical.value,
            "price": {"value": f"{o.price.amount:.2f}", "currency": o.price.currency},
        }

    def dispatch(op: str, args: dict) -> dict:
        required_token = os.environ.get("ODYSSEY_UCP_TOKEN")
        if op in _MUTATING_OPS and required_token:
            if (args.get("meta") or {}).get("ucp-token") != required_token:
                return {"error": "unauthorized: invalid or missing ucp-token"}

        if op == "search_catalog":
            mp = (args.get("filters") or {}).get("max_price")
            return {"products": [_offer_dict(o) for o in source.search(args.get("query", ""), mp)]}

        if op in ("lookup_catalog", "get_product"):
            ids = args.get("ids") or ([args["id"]] if "id" in args else [])
            return {"products": [_offer_dict(o) for i in ids if (o := source.get(i))]}

        if op == "create_checkout":
            items = (args.get("checkout") or {}).get("items") or []
            if not items or not isinstance(items[0], dict) or "id" not in items[0]:
                return {"error": "create_checkout requires checkout.items[0].id"}
            offer = source.get(items[0]["id"])
            if offer is None:  # stale/unknown id → clean error, not an AttributeError/500
                return {"error": f"unknown offer id {items[0]['id']}"}
            cid = f"ck-{uuid.uuid4().hex[:8]}"
            cm = build_cart_mandate(cid, name, offer.price, offer.title)
            template = build_payment_mandate(cart=cm, merchant_agent=f"{vertical.value}_merchant")
            carts[cid] = {"offer": offer, "cart_mandate": cm}
            return {
                "checkout": {
                    "id": cid,
                    "total": _offer_dict(offer)["price"],
                    "cart_mandate": cm.model_dump(),
                },
                "payment_template": template.model_dump(),
            }

        if op == "get_checkout":
            return {"checkout": {"id": args["id"], "found": args["id"] in carts}}

        if op == "update_checkout":
            return {"checkout": {"id": args["id"], "updated": True}}

        if op in ("complete_checkout", "cancel_checkout"):
            key = (args.get("meta") or {}).get("idempotency-key")
            if not key:
                return {"error": "missing idempotency-key"}
            cid = args.get("id")

            if op == "cancel_checkout":
                if key in canceled_keys:
                    return {"order": {"status": "canceled", "idempotent_replay": True}}
                if key in completed:
                    return {"error": "idempotency-key already used for a completed checkout"}
                canceled_keys.add(key)
                carts.pop(cid, None)
                return {"order": {"status": "canceled"}}

            # complete_checkout — replay only a previously CONFIRMED order (set after verify).
            if key in completed:
                return {"order": {**completed[key], "idempotent_replay": True}}
            if key in canceled_keys:
                return {"error": "idempotency-key already used for a canceled checkout"}
            cart = carts.get(cid)
            if cart is None:
                return {"error": "unknown checkout id"}
            pm_dict = (args.get("checkout") or {}).get("payment_mandate")
            if pm_dict is None:
                return {"error": "missing payment_mandate"}
            pm = PaymentMandate.model_validate(pm_dict)
            if not verify_payment_mandate(pm, cart=cart["cart_mandate"]):
                return {"error": "mandate verification failed"}
            order = {
                "status": "confirmed",
                "id": cid,
                "confirmation": f"OD-{(cid or '')[-6:].upper()}",
            }
            completed[key] = order
            return {"order": order}

        return {"error": f"unknown op {op}"}

    return dispatch


def _ucp_doc() -> dict:
    return {
        "ucp": {
            "version": "2026-04-08",
            "services": {"dev.ucp.shopping": {"endpoint": "/mcp"}},
            "capabilities": {
                "dev.ucp.shopping.catalog": {"transport": "mcp", "endpoint": "/mcp"},
                "dev.ucp.shopping.checkout": {"transport": "mcp", "endpoint": "/mcp"},
            },
        },
        "payment_handlers": {"com.google.pay": {}},
        "signing_keys": [],
    }


def attach_ucp_routes(app, name: str, vertical: Vertical, source: CatalogSource) -> None:
    """Attach GET /.well-known/ucp and POST /mcp to an existing Starlette app (the to_a2a app)."""
    dispatch = build_dispatch(name, vertical, source)

    async def _well_known(request: StarletteRequest):
        return JSONResponse(_ucp_doc())

    async def _mcp(request: StarletteRequest):
        body = await request.json()
        params = body.get("params", {})
        return JSONResponse(
            {
                "jsonrpc": "2.0",
                "id": body.get("id"),
                "result": dispatch(params.get("name"), params.get("arguments", {})),
            }
        )

    app.add_route("/.well-known/ucp", _well_known, methods=["GET"])
    app.add_route("/mcp", _mcp, methods=["POST"])


def make_ucp_app(name: str, vertical: Vertical, source: CatalogSource) -> FastAPI:
    app = FastAPI(title=f"UCP merchant: {name}")
    dispatch = build_dispatch(name, vertical, source)

    @app.get("/.well-known/ucp")
    def well_known():
        return _ucp_doc()

    @app.post("/mcp")
    async def mcp(request: Request):
        body = await request.json()
        params = body.get("params", {})
        return {
            "jsonrpc": "2.0",
            "id": body.get("id"),
            "result": dispatch(params.get("name"), params.get("arguments", {})),
        }

    return app
