"""`RoutingClient`: the turn-by-turn-distance abstraction the route planner
(`route_planner.py`) needs. `OsrmRoutingClient` follows the same
retry/backoff shape as `StripePaymentProvider`/`ElectricityMapsClient` —
retry transport failures and 5xx responses, never a 4xx (a definitive
"can't route this" answer). It defaults to OSRM's free public demo
server, which needs no API key (unlike Stripe/ElectricityMaps) but is
rate-limited and unsuited to real production traffic — swap
`routing_base_url` for a paid provider (Mapbox/HERE/Google) before launch.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol

import httpx

from evagg.driver_app.geo import haversine_km


class RoutingError(Exception):
    pass


@dataclass(frozen=True)
class RouteEstimate:
    distance_km: float
    duration_minutes: float


class RoutingClient(Protocol):
    async def get_route(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteEstimate:
        """`origin`/`destination` are `(lat, lng)` pairs."""
        ...


class FakeRoutingClient:
    """Straight-line (haversine) distance at an assumed average speed —
    used in `app_mode=testing` in place of a real routing provider, and in
    unit tests for deterministic, network-free results."""

    def __init__(self, average_speed_kmh: float = 70.0) -> None:
        self._average_speed_kmh = average_speed_kmh

    async def get_route(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteEstimate:
        distance_km = haversine_km(origin, destination)
        duration_minutes = distance_km / self._average_speed_kmh * 60
        return RouteEstimate(distance_km=distance_km, duration_minutes=duration_minutes)


class OsrmRoutingClient:
    """Real HTTP adapter against OSRM's `/route/v1/driving/{coords}` API."""

    def __init__(
        self,
        base_url: str = "https://router.project-osrm.org",
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.5,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._http_client = http_client

    async def get_route(self, origin: tuple[float, float], destination: tuple[float, float]) -> RouteEstimate:
        client = self._http_client or httpx.AsyncClient()
        origin_lat, origin_lng = origin
        dest_lat, dest_lng = destination
        coords = f"{origin_lng},{origin_lat};{dest_lng},{dest_lat}"
        last_exc: Exception | None = None

        for attempt in range(self._max_attempts):
            try:
                response = await client.get(
                    f"{self._base_url}/route/v1/driving/{coords}",
                    params={"overview": "false"},
                )
            except httpx.HTTPError as exc:
                last_exc = exc
                if attempt < self._max_attempts - 1:
                    await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
                continue

            if response.status_code >= 500:
                last_exc = RoutingError(f"routing provider server error (status {response.status_code})")
                if attempt < self._max_attempts - 1:
                    await asyncio.sleep(self._backoff_base_seconds * (2**attempt))
                continue

            try:
                data = response.json()
            except ValueError as exc:
                raise RoutingError("malformed routing provider response body") from exc

            if response.status_code >= 400:
                raise RoutingError(data.get("message", f"routing request rejected (status {response.status_code})"))

            if data.get("code") != "Ok" or not data.get("routes"):
                raise RoutingError(f"routing provider returned no route: {data.get('code')!r}")

            route = data["routes"][0]
            return RouteEstimate(
                distance_km=route["distance"] / 1000,
                duration_minutes=route["duration"] / 60,
            )

        raise RoutingError(f"routing request failed after {self._max_attempts} attempts") from last_exc
