from __future__ import annotations

import uuid

from ap2.models.mandate import CartMandate, PaymentMandate  # noqa: F401 (used via model_validate)
from fastapi import FastAPI, Request

from odyssey.common.types import Vertical
from odyssey.merchants.catalog_source import CatalogSource
from odyssey.protocols.ap2_adapter import (
    build_cart_mandate,
    build_payment_mandate,
    verify_payment_mandate,
)


def build_dispatch(name: str, vertical: Vertical, source: CatalogSource):
    """Return a dispatch(op, args) -> dict closure with mutable per-merchant state.

    Factored out so Task 9 can attach the same handler to a combined A2A+UCP app.
    """
    carts: dict[str, dict] = {}
    seen_keys: set[str] = set()

    def _offer_dict(o):
        return {
            "id": o.id,
            "title": o.title,
            "vertical": o.vertical.value,
            "price": {"value": f"{o.price.amount:.2f}", "currency": o.price.currency},
        }

    def dispatch(op: str, args: dict) -> dict:
        if op == "search_catalog":
            mp = (args.get("filters") or {}).get("max_price")
            return {"products": [_offer_dict(o) for o in source.search(args.get("query", ""), mp)]}

        if op in ("lookup_catalog", "get_product"):
            ids = args.get("ids") or ([args["id"]] if "id" in args else [])
            return {"products": [_offer_dict(o) for i in ids if (o := source.get(i))]}

        if op == "create_checkout":
            offer = source.get(args["checkout"]["items"][0]["id"])
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
            if key in seen_keys:
                return {"order": {"status": "confirmed", "idempotent_replay": True}}
            cart = carts.get(args["id"])
            if op == "cancel_checkout":
                seen_keys.add(key)
                carts.pop(args["id"], None)
                return {"order": {"status": "canceled"}}
            if cart is None:
                return {"error": "unknown checkout id"}
            pm_dict = (args.get("checkout") or {}).get("payment_mandate")
            if pm_dict is None:
                return {"error": "missing payment_mandate"}
            pm = PaymentMandate.model_validate(pm_dict)
            if not verify_payment_mandate(pm, cart=cart["cart_mandate"]):
                return {"error": "mandate verification failed"}
            seen_keys.add(key)
            return {
                "order": {
                    "status": "confirmed",
                    "id": args["id"],
                    "confirmation": f"OD-{args['id'][-6:].upper()}",
                }
            }

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
