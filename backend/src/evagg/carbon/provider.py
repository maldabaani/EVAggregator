"""Task 1.4 — third-party grid carbon intensity provider (Electricity Maps).

`ElectricityMapsClient` retries transient failures with exponential backoff
before giving up; the caller (`CarbonIntensityService`) is what decides to
fall back to a stale cached value once retries are exhausted.

`MockCarbonProvider` is the `app_mode=testing` stand-in — wired by
`evagg.composition` instead of `ElectricityMapsClient` so the carbon
endpoint returns plausible values with no API key.
"""

from __future__ import annotations

import asyncio
import hashlib
from typing import Protocol

import httpx


class CarbonProviderError(Exception):
    pass


class CarbonProvider(Protocol):
    async def fetch_intensity(self, provider_zone_id: str) -> float: ...


class ElectricityMapsClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.electricitymap.org/v3",
        max_attempts: int = 3,
        backoff_base_seconds: float = 0.5,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._http_client = http_client

    async def fetch_intensity(self, provider_zone_id: str) -> float:
        client = self._http_client or httpx.AsyncClient()
        last_exc: Exception | None = None

        for attempt in range(self._max_attempts):
            try:
                response = await client.get(
                    f"{self._base_url}/carbon-intensity/latest",
                    params={"zone": provider_zone_id},
                    headers={"auth-token": self._api_key},
                )
                response.raise_for_status()
                data = response.json()
                return float(data["carbonIntensity"])
            except (httpx.HTTPError, KeyError, ValueError, TypeError) as exc:
                last_exc = exc
                if attempt < self._max_attempts - 1:
                    await asyncio.sleep(self._backoff_base_seconds * (2**attempt))

        raise CarbonProviderError(
            f"failed to fetch carbon intensity for zone {provider_zone_id} after {self._max_attempts} attempts"
        ) from last_exc


class MockCarbonProvider:
    """Deterministic stand-in for `ElectricityMapsClient`: no API key, no
    network call, but every zone still gets a stable, plausible-looking
    gCO2/kWh value (derived from the zone id, not random) so repeated
    lookups and cache-hit assertions behave the same as a real provider."""

    _BASE_VALUE = 120.0
    _SPREAD = 380.0

    def __init__(self, overrides: dict[str, float] | None = None) -> None:
        self._overrides = dict(overrides or {})

    def set_response(self, provider_zone_id: str, value: float) -> None:
        self._overrides[provider_zone_id] = value

    async def fetch_intensity(self, provider_zone_id: str) -> float:
        if provider_zone_id in self._overrides:
            return self._overrides[provider_zone_id]
        digest = hashlib.sha256(provider_zone_id.encode()).digest()
        fraction = int.from_bytes(digest[:4], "big") / 0xFFFFFFFF
        return round(self._BASE_VALUE + fraction * self._SPREAD, 1)
