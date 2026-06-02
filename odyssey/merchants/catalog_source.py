from __future__ import annotations

from typing import Protocol

from odyssey.common.types import Offer


class CatalogSource(Protocol):
    def search(self, query: str, max_price: float | None) -> list[Offer]: ...
    def get(self, offer_id: str) -> Offer | None: ...
