from __future__ import annotations

import asyncio
import os

from odyssey.common.types import Offer, Vertical
from odyssey.data.amadeus import AmadeusClient
from odyssey.data.seed import seeded_source
from odyssey.merchants.catalog_source import CatalogSource

_DEMO = {
    "origin": "JFK",
    "city": "DPS",
    "lat": -8.65,
    "lon": 115.13,
    "depart": "2026-09-01",
    "ret": "2026-09-06",
    "adults": 2,
}


class _LiveSource:
    def __init__(self, vertical: Vertical):
        self._v = vertical
        self._seed = seeded_source(vertical)

    def _client(self) -> AmadeusClient:
        return AmadeusClient(
            os.environ.get("AMADEUS_BASE_URL", "https://test.api.amadeus.com"),
            os.environ.get("AMADEUS_CLIENT_ID", ""),
            os.environ.get("AMADEUS_CLIENT_SECRET", ""),
        )

    async def _fetch(self) -> list[Offer]:
        c = self._client()
        if self._v is Vertical.FLIGHT:
            return await c.search_flights(
                _DEMO["origin"], _DEMO["city"], _DEMO["depart"], _DEMO["ret"], _DEMO["adults"]
            )
        if self._v is Vertical.HOTEL:
            return await c.search_hotels(
                _DEMO["city"], _DEMO["depart"], _DEMO["ret"], _DEMO["adults"]
            )
        return await c.search_activities(_DEMO["lat"], _DEMO["lon"])

    def search(self, query: str, max_price: float | None) -> list[Offer]:
        try:
            offers = asyncio.run(self._fetch())
        except Exception:
            offers = []
        if not offers:
            offers = self._seed.search(query, max_price)
        return [o for o in offers if max_price is None or o.price.amount <= max_price]

    def get(self, offer_id: str) -> Offer | None:
        found = next((o for o in self.search("", None) if o.id == offer_id), None)
        return found or self._seed.get(offer_id)


def make_source(vertical: Vertical) -> CatalogSource:
    mode = os.environ.get("ODYSSEY_DATA_MODE", "SEED").upper()
    if mode == "SEED":
        return seeded_source(vertical)
    if mode == "SCRAPE":
        from odyssey.data.scrape import ScrapeSource  # lazy — keeps SEED cold-start free

        return ScrapeSource(vertical)
    return _LiveSource(vertical)
