"""
Scrape-based CatalogSource backed by public Wikivoyage pages via Firecrawl.

POLITENESS NOTE: We scrape only publicly-licensed Wikivoyage pages (CC BY-SA),
throttle to one URL at a time, and cache results for ``ttl`` seconds (default 15 min)
to avoid hammering the server on repeated searches.

Data quality note: prices extracted from travel-guide prose are *indicative*; always
display them with the ``note`` field from ``Offer.raw``.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from datetime import datetime, timezone
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator

from odyssey.common.types import Money, Offer, Vertical
from odyssey.data.seed import seeded_source

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Pydantic extraction models
# ---------------------------------------------------------------------------


def _to_float(v: Any) -> float:
    """Coerce a price value to float; raise ValueError on anything unusable."""
    if v is None:
        raise ValueError("missing price")
    s = "".join(c for c in str(v) if c.isdigit() or c == ".")
    if not s:
        raise ValueError("no numeric price")
    return float(s)


class ScrapedOffer(BaseModel):
    title: str
    price: Annotated[float, BeforeValidator(_to_float)]
    currency: str = "USD"


class ScrapedOffers(BaseModel):
    offers: list[ScrapedOffer]


# ---------------------------------------------------------------------------
# Default scrape targets (Wikivoyage only covers activities, not flights/hotels)
# ---------------------------------------------------------------------------

_TARGETS: dict[Vertical, list[str]] = {
    Vertical.ACTIVITY: ["https://en.wikivoyage.org/wiki/Bali"],
}

# Module-level TTL cache: {(vertical, targets_tuple): (timestamp, offers)}
_CACHE: dict[tuple[Any, ...], tuple[float, list[Offer]]] = {}

# Extraction prompt sent to Firecrawl's structured-JSON endpoint
_EXTRACT_PROMPT = (
    "Extract every listed activity, tour, or attraction with a title, its numeric price, "
    "and the 3-letter ISO currency code (e.g. USD, EUR, IDR). "
    "Skip items that have no explicit price."
)


# ---------------------------------------------------------------------------
# Helper — build a stable 12-char ID from URL + title
# ---------------------------------------------------------------------------


def _offer_id(url: str, title: str) -> str:
    raw = f"{url}|{title}"
    return hashlib.sha1(raw.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# ScrapeSource
# ---------------------------------------------------------------------------


class ScrapeSource:
    """
    CatalogSource that scrapes configured public pages via Firecrawl and maps
    the extracted structured data to ``Offer`` objects.

    Falls back to the seed source whenever:
    - the vertical has no configured scrape targets (e.g. FLIGHT, HOTEL), OR
    - a network/parse error occurs, OR
    - Firecrawl returns zero usable offers.

    The ``client`` parameter is injectable for offline unit tests (pass any
    object with a ``.scrape(url, formats=..., only_main_content=...)`` method
    that returns an object with a ``.json`` attribute).
    """

    def __init__(
        self,
        vertical: Vertical,
        targets: list[str] | None = None,
        client: Any = None,
        ttl: float = 900.0,
    ) -> None:
        self._vertical = vertical
        self._ttl = ttl
        self._seed = seeded_source(vertical)

        # Resolve targets: explicit arg > env override > module default > empty
        if targets is not None:
            self._targets = targets
        else:
            env_urls = os.environ.get("ODYSSEY_SCRAPE_URLS", "").strip()
            if env_urls and vertical in _TARGETS:
                self._targets = [u.strip() for u in env_urls.split(",") if u.strip()]
            else:
                self._targets = _TARGETS.get(vertical, [])

        # Lazy-init the real Firecrawl client only if no injectable client given
        self._client = client  # may be None; resolved lazily in _get_client()

    def _get_client(self) -> Any:
        """Return the injectable test client or a real Firecrawl instance."""
        if self._client is not None:
            return self._client
        # Import here so that importing sources.py in SEED mode doesn't
        # require a FIRECRAWL_API_KEY at module load time.
        from firecrawl import Firecrawl  # noqa: PLC0415

        api_key = os.environ.get("FIRECRAWL_API_KEY", "")
        return Firecrawl(api_key=api_key)

    # ------------------------------------------------------------------
    # Internal scraping logic
    # ------------------------------------------------------------------

    def _scrape_url(self, url: str) -> list[Offer]:
        """Scrape one URL; return a (possibly empty) list of Offer objects."""
        from firecrawl.v2.types import JsonFormat  # noqa: PLC0415

        client = self._get_client()
        doc = client.scrape(
            url,
            formats=[
                JsonFormat(
                    type="json",
                    schema=ScrapedOffers.model_json_schema(),
                    prompt=_EXTRACT_PROMPT,
                )
            ],
            only_main_content=True,
        )

        # Defensively access the .json attribute
        raw: Any = None
        if hasattr(doc, "json"):
            raw = doc.json
        elif isinstance(doc, dict):
            raw = doc.get("json") or doc.get("data", {}).get("json")

        if not raw:
            return []

        # Extract the raw list of offer dicts defensively
        raw_items: Any = None
        if isinstance(raw, dict):
            raw_items = raw.get("offers")
        if not isinstance(raw_items, list):
            logger.warning("Unexpected ScrapedOffers shape from %s: %r", url, raw)
            return []

        offers: list[Offer] = []
        fetched_at = datetime.now(timezone.utc).isoformat()
        for raw_item in raw_items:
            # Validate each row individually so bad rows are dropped, good rows kept
            try:
                item = ScrapedOffer.model_validate(raw_item)
            except Exception as exc:
                _d = raw_item if isinstance(raw_item, dict) else {}
                title = _d.get("title", "<row>")
                logger.warning("Dropping invalid offer row %r from %s: %s", title, url, exc)
                continue
            try:
                offer = Offer(
                    id=_offer_id(url, item.title),
                    vertical=self._vertical,
                    title=item.title,
                    price=Money(item.currency.upper(), round(item.price, 2)),
                    raw={
                        "source": url,
                        "fetched_at": fetched_at,
                        "method": "public-web-scrape",
                        "note": "indicative pricing",
                    },
                )
                offers.append(offer)
            except Exception as exc:
                logger.warning("Dropping offer %r from %s: %s", item.title, url, exc)

        return offers

    def _fetch_all(self) -> list[Offer]:
        """Scrape every configured target URL and aggregate offers."""
        all_offers: list[Offer] = []
        for url in self._targets:
            try:
                all_offers.extend(self._scrape_url(url))
            except Exception as exc:
                logger.warning("Error scraping %s: %s", url, exc)
        return all_offers

    def _cached_offers(self) -> list[Offer] | None:
        """Return cached offers if still within TTL, else None."""
        key = (self._vertical, tuple(self._targets))
        entry = _CACHE.get(key)
        if entry is None:
            return None
        ts, offers = entry
        if time.monotonic() - ts <= self._ttl:
            return offers
        return None

    def _store_cache(self, offers: list[Offer]) -> None:
        key = (self._vertical, tuple(self._targets))
        _CACHE[key] = (time.monotonic(), offers)

    # ------------------------------------------------------------------
    # CatalogSource interface
    # ------------------------------------------------------------------

    def search(self, query: str, max_price: float | None) -> list[Offer]:
        # Flights and hotels are NOT on Wikivoyage — delegate to seed honestly
        if self._vertical not in _TARGETS and not self._targets:
            return self._seed.search(query, max_price)

        # Check TTL cache first
        cached = self._cached_offers()
        if cached is not None:
            return [o for o in cached if max_price is None or o.price.amount <= max_price]

        # Scrape live
        try:
            offers = self._fetch_all()
        except Exception as exc:
            logger.warning("Top-level scrape failure for %s: %s", self._vertical, exc)
            offers = []

        if not offers:
            logger.info("No offers scraped for %s; falling back to seed", self._vertical)
            return self._seed.search(query, max_price)

        self._store_cache(offers)
        return [o for o in offers if max_price is None or o.price.amount <= max_price]

    def get(self, offer_id: str) -> Offer | None:
        all_offers = self.search("", None)
        found = next((o for o in all_offers if o.id == offer_id), None)
        return found or self._seed.get(offer_id)
