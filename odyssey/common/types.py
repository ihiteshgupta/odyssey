from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Vertical(str, Enum):
    FLIGHT = "flight"
    HOTEL = "hotel"
    ACTIVITY = "activity"


@dataclass(frozen=True)
class Money:
    currency: str
    amount: float

    def __add__(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError(f"currency mismatch: {self.currency} != {other.currency}")
        return Money(self.currency, round(self.amount + other.amount, 2))

    def __le__(self, other: "Money") -> bool:
        if self.currency != other.currency:
            raise ValueError("currency mismatch")
        return self.amount <= other.amount


@dataclass(frozen=True)
class Offer:
    id: str
    vertical: Vertical
    title: str
    price: Money
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class Intent:
    origin: str
    destination: str
    start_date: str
    end_date: str
    party_size: int
    total_budget: Money
    prefs: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class NegotiationRequest:
    intent: Intent
    budget_slice: Money
    round: int = 0


@dataclass(frozen=True)
class NegotiationResponse:
    offers: list[Offer]
    fits: bool
    cheapest: Money
    nearest_above: Money | None
    note: str = ""


@dataclass
class ItineraryItem:
    offer: Offer
    cart_mandate: dict | None = None
    confirmation: str | None = None


@dataclass
class Itinerary:
    items: list[ItineraryItem] = field(default_factory=list)

    def total(self, currency: str) -> Money:
        tot = Money(currency, 0.0)
        for it in self.items:
            tot = tot + it.offer.price
        return tot


class TripState(str, Enum):
    INTENT = "intent"
    NEGOTIATE = "negotiate"
    ASSEMBLE = "assemble"
    CONFIRM = "confirm"
    CHECKOUT = "checkout"
    DONE = "done"
