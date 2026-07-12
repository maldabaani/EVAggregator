import uuid

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.ocpp_gateway.presence import InMemoryPresenceRegistry
from evagg.ocpp_gateway.presence_api import build_presence_router

TENANT_ID = uuid.uuid4()


def _build_app(registry: InMemoryPresenceRegistry) -> FastAPI:
    async def get_registry():
        return registry

    app = FastAPI()
    app.include_router(build_presence_router(get_registry))
    return app


def test_single_presence_endpoint_returns_state():
    import asyncio

    registry = InMemoryPresenceRegistry()
    asyncio.run(registry.mark_online("CP-1", TENANT_ID, node_id="node-a", protocol_version="ocpp1.6", ttl_seconds=600))
    client = TestClient(_build_app(registry))

    response = client.get("/internal/chargers/CP-1/presence")

    assert response.status_code == 200
    assert response.json()["node_id"] == "node-a"


def test_single_presence_endpoint_returns_null_for_unknown_charger():
    client = TestClient(_build_app(InMemoryPresenceRegistry()))

    response = client.get("/internal/chargers/unknown/presence")

    assert response.status_code == 200
    assert response.json() is None


def test_bulk_presence_endpoint_returns_multiple_states():
    import asyncio

    registry = InMemoryPresenceRegistry()
    asyncio.run(registry.mark_online("CP-1", TENANT_ID, node_id="node-a", protocol_version="ocpp1.6", ttl_seconds=600))
    client = TestClient(_build_app(registry))

    response = client.get("/internal/chargers/presence", params={"ids": ["CP-1", "CP-2"]})

    assert response.status_code == 200
    body = response.json()
    assert body["CP-1"]["node_id"] == "node-a"
    assert body["CP-2"] is None
