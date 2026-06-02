from __future__ import annotations

from odyssey.common.types import Money, Offer, Vertical


def _money(value: object, currency: str) -> Money:
    return Money(currency.upper(), round(float(value), 2))  # type: ignore[arg-type]


def flight_offer_to_offer(raw: dict) -> Offer:
    price = raw["price"]
    segs = raw["itineraries"][0]["segments"]
    origin = segs[0]["departure"]["iataCode"]
    destination = segs[-1]["arrival"]["iataCode"]
    route = f"{origin}→{destination}"
    return Offer(
        id=str(raw["id"]),
        vertical=Vertical.FLIGHT,
        title=f"Flight {route}",
        price=_money(price.get("grandTotal", price.get("total")), price["currency"]),
        raw=raw,
    )


def hotel_offer_to_offer(raw: dict) -> Offer:
    offer0 = raw["offers"][0]
    price = offer0["price"]
    return Offer(
        id=str(offer0["id"]),
        vertical=Vertical.HOTEL,
        title=raw["hotel"]["name"],
        price=_money(price["total"], price["currency"]),
        raw=raw,
    )


def activity_to_offer(raw: dict) -> Offer:
    price = raw["price"]
    currency = price.get("currencyCode", price.get("currency", "USD"))
    return Offer(
        id=str(raw["id"]),
        vertical=Vertical.ACTIVITY,
        title=raw["name"],
        price=_money(price["amount"], currency),
        raw=raw,
    )
