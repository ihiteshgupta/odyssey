from __future__ import annotations

import time

import httpx

from odyssey.common.normalize import activity_to_offer, flight_offer_to_offer, hotel_offer_to_offer
from odyssey.common.types import Offer


class AmadeusClient:
    def __init__(self, base_url: str, client_id: str, client_secret: str):
        self._base = base_url.rstrip("/")
        self._id = client_id
        self._secret = client_secret
        self._token: str | None = None
        self._expiry = 0.0
        self._http = httpx.AsyncClient(timeout=20.0)

    async def _auth(self) -> str:
        if self._token and time.monotonic() < self._expiry - 30:
            return self._token
        r = await self._http.post(
            f"{self._base}/v1/security/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._id,
                "client_secret": self._secret,
            },
        )
        r.raise_for_status()
        body = r.json()
        self._token = body["access_token"]
        self._expiry = time.monotonic() + float(body.get("expires_in", 1799))
        return self._token

    async def _get(self, path: str, params: dict) -> dict:
        token = await self._auth()
        r = await self._http.get(
            f"{self._base}{path}",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        r.raise_for_status()
        return r.json()

    async def search_flights(
        self, origin: str, destination: str, departure_date: str, return_date: str, adults: int
    ) -> list[Offer]:
        data = await self._get(
            "/v2/shopping/flight-offers",
            {
                "originLocationCode": origin,
                "destinationLocationCode": destination,
                "departureDate": departure_date,
                "returnDate": return_date,
                "adults": adults,
                "currencyCode": "USD",
                "max": 10,
            },
        )
        return [flight_offer_to_offer(d) for d in data.get("data", [])]

    async def search_hotels(
        self, city_code: str, check_in: str, check_out: str, adults: int
    ) -> list[Offer]:
        listing = await self._get(
            "/v1/reference-data/locations/hotels/by-city", {"cityCode": city_code}
        )
        ids = [h["hotelId"] for h in listing.get("data", [])][:20]
        if not ids:
            return []
        data = await self._get(
            "/v3/shopping/hotel-offers",
            {
                "hotelIds": ",".join(ids),
                "adults": adults,
                "checkInDate": check_in,
                "checkOutDate": check_out,
                "currency": "USD",
            },
        )
        return [hotel_offer_to_offer(d) for d in data.get("data", [])]

    async def search_activities(
        self, latitude: float, longitude: float, radius: int = 20
    ) -> list[Offer]:
        data = await self._get(
            "/v1/shopping/activities",
            {"latitude": latitude, "longitude": longitude, "radius": radius},
        )
        return [activity_to_offer(d) for d in data.get("data", [])]
