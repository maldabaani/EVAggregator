"""Task 1.4 — ties the zone map, cache, and provider together: fresh cache
hit within TTL short-circuits the provider entirely; a cache miss/expiry
triggers a live fetch; a provider failure falls back to the last cached
value (flagged `stale: true`) rather than erroring the caller; an unmapped
zone is rejected before ever touching the provider.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from evagg.carbon.cache import CarbonCache
from evagg.carbon.provider import CarbonProvider, CarbonProviderError
from evagg.carbon.zone_map import CarbonZoneMap

DEFAULT_TTL_SECONDS = 15 * 60


class ZoneNotSupportedError(Exception):
    pass


@dataclass(frozen=True)
class CarbonIntensityResult:
    value: float
    stale: bool


class CarbonIntensityService:
    def __init__(
        self,
        zone_map: CarbonZoneMap,
        provider: CarbonProvider,
        cache: CarbonCache,
        ttl_seconds: int = DEFAULT_TTL_SECONDS,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._zone_map = zone_map
        self._provider = provider
        self._cache = cache
        self._ttl_seconds = ttl_seconds
        self._clock = clock

    async def get_intensity(self, country_code: str, area_code: str) -> CarbonIntensityResult:
        provider_zone_id = await self._zone_map.get_provider_zone_id(country_code, area_code)
        if provider_zone_id is None:
            raise ZoneNotSupportedError(f"zone not supported: {country_code}/{area_code}")

        cached = await self._cache.get(country_code, area_code)
        now = self._clock()

        if cached is not None and (now - cached.fetched_at).total_seconds() < self._ttl_seconds:
            return CarbonIntensityResult(value=cached.value, stale=False)

        try:
            value = await self._provider.fetch_intensity(provider_zone_id)
        except CarbonProviderError:
            if cached is not None:
                return CarbonIntensityResult(value=cached.value, stale=True)
            raise

        await self._cache.set(country_code, area_code, value, now)
        return CarbonIntensityResult(value=value, stale=False)
