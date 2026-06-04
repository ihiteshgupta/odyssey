from __future__ import annotations

import asyncio
import logging
import os

from odyssey.common.types import Offer, Vertical
from odyssey.data.amadeus import AmadeusClient
from odyssey.data.seed import seeded_source
from odyssey.merchants.catalog_source import CatalogSource

logger = logging.getLogger(__name__)

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

    def _fetch_sync(self) -> list[Offer]:
        """Run the async Amadeus fetch from a sync context, loop-safe.

        ``asyncio.run`` raises inside a running event loop (the UCP ``/mcp`` route is
        async), which previously turned EVERY in-loop LIVE search into a silent seed
        fallback. When a loop is already running we run the coroutine on a worker thread."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._fetch())
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
            return ex.submit(lambda: asyncio.run(self._fetch())).result()

    def search(self, query: str, max_price: float | None) -> list[Offer]:
        try:
            offers = self._fetch_sync()
        except Exception as exc:
            # Log loudly — a swallowed auth/network error must not masquerade as
            # "healthy live mode serving seed data".
            logger.warning("LIVE fetch for %s failed (%s); falling back to seed", self._v, exc)
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
