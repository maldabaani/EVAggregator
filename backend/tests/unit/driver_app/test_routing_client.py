"""OsrmRoutingClient tested against `httpx.MockTransport` — same approach
as `tests/unit/billing/test_payment_provider.py`."""

import httpx
import pytest

from evagg.driver_app.routing_client import FakeRoutingClient, OsrmRoutingClient, RoutingError

DUBAI = (25.2048, 55.2708)
ABU_DHABI = (24.4539, 54.3773)


@pytest.mark.asyncio
async def test_fake_routing_client_returns_a_haversine_based_estimate():
    client = FakeRoutingClient(average_speed_kmh=60.0)

    estimate = await client.get_route(DUBAI, ABU_DHABI)

    assert 110 < estimate.distance_km < 140
    assert estimate.duration_minutes == pytest.approx(estimate.distance_km / 60.0 * 60, rel=1e-6)


@pytest.mark.asyncio
async def test_osrm_client_parses_a_successful_route():
    def handler(request: httpx.Request) -> httpx.Response:
        assert "route/v1/driving" in str(request.url)
        return httpx.Response(200, json={"code": "Ok", "routes": [{"distance": 132000.0, "duration": 5400.0}]})

    client = OsrmRoutingClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    estimate = await client.get_route(DUBAI, ABU_DHABI)

    assert estimate.distance_km == 132.0
    assert estimate.duration_minutes == 90.0


@pytest.mark.asyncio
async def test_osrm_client_retries_on_server_error_then_succeeds():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] < 2:
            return httpx.Response(503)
        return httpx.Response(200, json={"code": "Ok", "routes": [{"distance": 1000.0, "duration": 60.0}]})

    client = OsrmRoutingClient(
        backoff_base_seconds=0.001,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    estimate = await client.get_route(DUBAI, ABU_DHABI)

    assert attempts["count"] == 2
    assert estimate.distance_km == 1.0


@pytest.mark.asyncio
async def test_osrm_client_raises_after_exhausting_retries_on_repeated_server_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = OsrmRoutingClient(
        max_attempts=2,
        backoff_base_seconds=0.001,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(RoutingError):
        await client.get_route(DUBAI, ABU_DHABI)


@pytest.mark.asyncio
async def test_osrm_client_raises_on_malformed_response_body():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not json")

    client = OsrmRoutingClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    with pytest.raises(RoutingError):
        await client.get_route(DUBAI, ABU_DHABI)


@pytest.mark.asyncio
async def test_osrm_client_raises_when_no_route_is_found():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": "NoRoute", "routes": []})

    client = OsrmRoutingClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    with pytest.raises(RoutingError):
        await client.get_route(DUBAI, ABU_DHABI)


@pytest.mark.asyncio
async def test_osrm_client_raises_on_a_4xx_without_retrying():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        return httpx.Response(400, json={"message": "invalid coordinates"})

    client = OsrmRoutingClient(http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))

    with pytest.raises(RoutingError):
        await client.get_route(DUBAI, ABU_DHABI)

    assert attempts["count"] == 1
