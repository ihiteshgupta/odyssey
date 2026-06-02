import httpx
import pytest
import respx

from odyssey.data.amadeus import AmadeusClient

BASE = "https://test.api.amadeus.com"


@respx.mock
@pytest.mark.asyncio
async def test_token_cached_and_flights_parsed():
    tok = respx.post(f"{BASE}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "T", "expires_in": 1799}))
    respx.get(f"{BASE}/v2/shopping/flight-offers").mock(return_value=httpx.Response(200, json={"data": [
        {"id": "1", "price": {"grandTotal": "812.30", "currency": "USD"},
         "itineraries": [{"segments": [{"departure": {"iataCode": "JFK"}, "arrival": {"iataCode": "DPS"}}]}]}]}))
    c = AmadeusClient(BASE, "k", "s")
    offers = await c.search_flights("JFK", "DPS", "2026-09-01", "2026-09-06", 2)
    await c.search_flights("JFK", "DPS", "2026-09-01", "2026-09-06", 2)
    assert offers[0].price.amount == 812.30 and tok.call_count == 1


@respx.mock
@pytest.mark.asyncio
async def test_hotels_two_call_flow():
    respx.post(f"{BASE}/v1/security/oauth2/token").mock(
        return_value=httpx.Response(200, json={"access_token": "T", "expires_in": 1799}))
    respx.get(f"{BASE}/v1/reference-data/locations/hotels/by-city").mock(
        return_value=httpx.Response(200, json={"data": [{"hotelId": "ABCD1234"}]}))
    respx.get(f"{BASE}/v3/shopping/hotel-offers").mock(return_value=httpx.Response(200, json={"data": [
        {"hotel": {"name": "Bali Beach Resort"}, "offers": [{"id": "H9", "price": {"total": "640.00", "currency": "USD"}}]}]}))
    c = AmadeusClient(BASE, "k", "s")
    offers = await c.search_hotels("DPS", "2026-09-01", "2026-09-06", 2)
    assert offers[0].price.amount == 640.0 and offers[0].title == "Bali Beach Resort"
