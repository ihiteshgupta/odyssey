from odyssey.common.normalize import activity_to_offer, flight_offer_to_offer, hotel_offer_to_offer
from odyssey.common.types import Vertical


def test_flight_offer_normalization():
    raw = {"id": "1", "price": {"grandTotal": "812.30", "currency": "USD"},
           "itineraries": [{"segments": [{"departure": {"iataCode": "JFK"}, "arrival": {"iataCode": "DPS"}}]}]}
    o = flight_offer_to_offer(raw)
    assert o.vertical == Vertical.FLIGHT and o.price.amount == 812.30 and "JFK" in o.title and "DPS" in o.title


def test_hotel_offer_normalization():
    raw = {"hotel": {"name": "Bali Beach Resort"},
           "offers": [{"id": "H9", "price": {"total": "640.00", "currency": "USD"}}]}
    o = hotel_offer_to_offer(raw)
    assert o.vertical == Vertical.HOTEL and o.price.amount == 640.0 and o.id == "H9"


def test_activity_normalization():
    raw = {"id": "A3", "name": "Ubud Rice Terrace Tour", "price": {"amount": "55.00", "currencyCode": "USD"}}
    o = activity_to_offer(raw)
    assert o.vertical == Vertical.ACTIVITY and o.price.amount == 55.0 and o.title.startswith("Ubud")
