"""Task 1.4 — third-party grid carbon intensity provider (Electricity Maps).

`ElectricityMapsClient` retries transient failures with exponential backoff
before giving up; the caller (`CarbonIntensityService`) is what decides to
fall back to a stale cached value once retries are exhausted.
"""

from __future__ import annotations

import asyncio
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
