"""Task 1.4 unit tests — all isolated (in-memory zone map/cache, a fake
provider standing in for the real Electricity Maps HTTP client)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from evagg.carbon.cache import InMemoryCarbonCache
from evagg.carbon.provider import CarbonProviderError
from evagg.carbon.service import CarbonIntensityService, ZoneNotSupportedError
from evagg.carbon.zone_map import InMemoryCarbonZoneMap


class _FakeProvider:
    def __init__(self) -> None:
        self.calls: list[str] = []
        self._responses: dict[str, float] = {}
        self._failing: set[str] = set()

    def set_response(self, provider_zone_id: str, value: float) -> None:
        self._responses[provider_zone_id] = value

    def set_failing(self, provider_zone_id: str, failing: bool = True) -> None:
        if failing:
            self._failing.add(provider_zone_id)
        else:
            self._failing.discard(provider_zone_id)

    async def fetch_intensity(self, provider_zone_id: str) -> float:
        self.calls.append(provider_zone_id)
        if provider_zone_id in self._failing:
            raise CarbonProviderError(f"provider down for {provider_zone_id}")
        return self._responses[provider_zone_id]


class _FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kwargs) -> None:
        self.now += timedelta(**kwargs)


def _build_service(clock: _FakeClock):
    zone_map = InMemoryCarbonZoneMap({("AE", "DXB"): "AE-DXB"})
    provider = _FakeProvider()
    cache = InMemoryCarbonCache()
    service = CarbonIntensityService(zone_map, provider, cache, ttl_seconds=900, clock=clock)
    return service, zone_map, provider, cache


@pytest.mark.asyncio
async def test_carbon_intensity_returned_from_cache_within_ttl():
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    service, _, provider, cache = _build_service(clock)
    provider.set_response("AE-DXB", 250.0)
    await service.get_intensity("AE", "DXB")  # primes the cache
    provider.calls.clear()

    clock.advance(minutes=5)  # well within the 15-minute TTL
    result = await service.get_intensity("AE", "DXB")

    assert result.value == 250.0
    assert result.stale is False
    assert provider.calls == []  # served from cache, provider never called again


@pytest.mark.asyncio
async def test_provider_failure_falls_back_to_stale_cache():
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    service, _, provider, cache = _build_service(clock)
    provider.set_response("AE-DXB", 250.0)
    await service.get_intensity("AE", "DXB")

    clock.advance(minutes=20)  # past the 15-minute TTL
    provider.set_failing("AE-DXB", True)
    result = await service.get_intensity("AE", "DXB")

    assert result.value == 250.0  # last-known value
    assert result.stale is True


@pytest.mark.asyncio
async def test_unmapped_zone_returns_zone_not_supported_not_provider_error():
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    service, _, provider, _ = _build_service(clock)

    with pytest.raises(ZoneNotSupportedError):
        await service.get_intensity("US", "CA")

    assert provider.calls == []  # never reaches the provider at all


@pytest.mark.asyncio
async def test_cache_refreshed_after_ttl_expiry():
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    service, _, provider, cache = _build_service(clock)
    provider.set_response("AE-DXB", 250.0)
    await service.get_intensity("AE", "DXB")

    clock.advance(minutes=16)  # past the 15-minute TTL
    provider.set_response("AE-DXB", 275.0)  # provider has a newer reading now
    result = await service.get_intensity("AE", "DXB")

    assert result.value == 275.0
    assert result.stale is False
    cached = await cache.get("AE", "DXB")
    assert cached.value == 275.0
    assert cached.fetched_at == clock.now


@pytest.mark.asyncio
async def test_provider_failure_with_no_prior_cache_reraises():
    clock = _FakeClock(datetime(2026, 1, 1, tzinfo=timezone.utc))
    service, _, provider, _ = _build_service(clock)
    provider.set_failing("AE-DXB", True)

    with pytest.raises(CarbonProviderError):
        await service.get_intensity("AE", "DXB")
