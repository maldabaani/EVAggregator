"""Exercises the real httpx request/response/retry machinery via
`httpx.MockTransport` — no real network socket, but genuine httpx behavior
(status raising, JSON parsing) rather than a hand-rolled fake."""

from __future__ import annotations

import httpx
import pytest

from evagg.carbon.provider import CarbonProviderError, ElectricityMapsClient


@pytest.mark.asyncio
async def test_successful_response_returns_carbon_intensity():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["zone"] == "AE-DXB"
        assert request.headers["auth-token"] == "test-key"
        return httpx.Response(200, json={"carbonIntensity": 312.5})

    client = ElectricityMapsClient(
        api_key="test-key", http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    value = await client.fetch_intensity("AE-DXB")

    assert value == 312.5


@pytest.mark.asyncio
async def test_retries_transient_failures_before_succeeding():
    attempt_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempt_count["n"] += 1
        if attempt_count["n"] < 3:
            return httpx.Response(503)
        return httpx.Response(200, json={"carbonIntensity": 200.0})

    client = ElectricityMapsClient(
        api_key="test-key",
        max_attempts=3,
        backoff_base_seconds=0.001,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    value = await client.fetch_intensity("AE-DXB")

    assert value == 200.0
    assert attempt_count["n"] == 3


@pytest.mark.asyncio
async def test_exhausting_retries_raises_carbon_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = ElectricityMapsClient(
        api_key="test-key",
        max_attempts=2,
        backoff_base_seconds=0.001,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(CarbonProviderError):
        await client.fetch_intensity("AE-DXB")


@pytest.mark.asyncio
async def test_malformed_response_body_raises_carbon_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client = ElectricityMapsClient(
        api_key="test-key",
        max_attempts=1,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(CarbonProviderError):
        await client.fetch_intensity("AE-DXB")
