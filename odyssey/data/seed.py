from __future__ import annotations

from odyssey.common.types import Money, Offer, Vertical
from odyssey.merchants.catalog_source import CatalogSource

_SEED: dict[Vertical, list[Offer]] = {
    Vertical.HOTEL: [
        Offer("seed-hotel-1", Vertical.HOTEL, "Bali Beach Resort", Money("USD", 640.0)),
        Offer("seed-hotel-2", Vertical.HOTEL, "Ubud Jungle Villa", Money("USD", 880.0)),
    ],
    Vertical.FLIGHT: [
        Offer("seed-flight-1", Vertical.FLIGHT, "Flight JFK→DPS", Money("USD", 812.0)),
        Offer("seed-flight-2", Vertical.FLIGHT, "Flight JFK→DPS (nonstop)", Money("USD", 1180.0)),
    ],
    Vertical.ACTIVITY: [
        Offer("seed-act-1", Vertical.ACTIVITY, "Ubud Rice Terrace Tour", Money("USD", 55.0)),
        Offer("seed-act-2", Vertical.ACTIVITY, "Sunset Beach Dinner", Money("USD", 120.0)),
    ],
}


class _SeedSource:
    def __init__(self, vertical: Vertical) -> None:
        self._offers = _SEED[vertical]

    def search(self, query: str, max_price: float | None) -> list[Offer]:
        return [o for o in self._offers if max_price is None or o.price.amount <= max_price]

    def get(self, offer_id: str) -> Offer | None:
        return next((o for o in self._offers if o.id == offer_id), None)


def seeded_source(vertical: Vertical) -> CatalogSource:
    return _SeedSource(vertical)
