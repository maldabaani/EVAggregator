from __future__ import annotations

import uuid

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.ocpp_gateway.command_router import build_command_router
from evagg.ocpp_gateway.commands import (
    CommandOutcome,
    CommandStatus,
    FakeCommandTransport,
    InMemoryCommandLogStore,
    InMemoryFirmwareUpdateStore,
    RemoteCommandService,
)
from evagg.ocpp_gateway.presence import InMemoryPresenceRegistry

TENANT_ID = uuid.uuid4()
CHARGER_ID = "CP-001"


def _build_app():
    presence = InMemoryPresenceRegistry()
    command_log = InMemoryCommandLogStore()
    transport = FakeCommandTransport()
    firmware_store = InMemoryFirmwareUpdateStore()
    service = RemoteCommandService(presence, command_log, transport, firmware_store)

    async def get_service():
        return service

    async def get_command_log():
        return command_log

    app = FastAPI()
    app.include_router(build_command_router(get_service, get_command_log))
    return app, presence, command_log, transport


async def _mark_online(presence, node_id: str = "node-a") -> None:
    await presence.mark_online(CHARGER_ID, TENANT_ID, node_id=node_id, protocol_version="ocpp1.6", ttl_seconds=600)


def test_send_command_returns_the_outcome():
    app, presence, _, transport = _build_app()
    import asyncio

    asyncio.run(_mark_online(presence))
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {"status": "Accepted"}))
    client = TestClient(app)

    response = client.post(
        f"/admin/chargers/{CHARGER_ID}/commands",
        json={"tenant_id": str(TENANT_ID), "command_type": "Reset", "payload": {"type": "Soft"}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "accepted"
    assert body["result"] == {"status": "Accepted"}
    assert uuid.UUID(body["command_id"])


def test_send_command_rejects_unsupported_command_type():
    app, presence, _, _ = _build_app()
    import asyncio

    asyncio.run(_mark_online(presence))
    client = TestClient(app)

    response = client.post(
        f"/admin/chargers/{CHARGER_ID}/commands",
        json={"tenant_id": str(TENANT_ID), "command_type": "NotARealCommand"},
    )

    assert response.status_code == 422


def test_send_command_to_offline_charger_returns_409():
    app, _, _, _ = _build_app()
    client = TestClient(app)

    response = client.post(
        f"/admin/chargers/{CHARGER_ID}/commands",
        json={"tenant_id": str(TENANT_ID), "command_type": "Reset"},
    )

    assert response.status_code == 409


def test_list_recent_commands_returns_most_recent_first():
    app, presence, _, transport = _build_app()
    import asyncio

    asyncio.run(_mark_online(presence))
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {}))
    client = TestClient(app)

    client.post(f"/admin/chargers/{CHARGER_ID}/commands", json={"tenant_id": str(TENANT_ID), "command_type": "ClearCache"})
    client.post(f"/admin/chargers/{CHARGER_ID}/commands", json={"tenant_id": str(TENANT_ID), "command_type": "Reset"})

    response = client.get(f"/admin/chargers/{CHARGER_ID}/commands")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert body[0]["type"] == "Reset"
    assert body[1]["type"] == "ClearCache"


def test_get_command_by_id_returns_the_record():
    app, presence, _, transport = _build_app()
    import asyncio

    asyncio.run(_mark_online(presence))
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {"status": "Accepted"}))
    client = TestClient(app)

    sent = client.post(
        f"/admin/chargers/{CHARGER_ID}/commands", json={"tenant_id": str(TENANT_ID), "command_type": "Reset"}
    ).json()

    response = client.get(f"/admin/chargers/{CHARGER_ID}/commands/{sent['command_id']}")

    assert response.status_code == 200
    assert response.json()["status"] == "accepted"


def test_get_command_by_id_404s_for_unknown_id():
    app, _, _, _ = _build_app()
    client = TestClient(app)

    response = client.get(f"/admin/chargers/{CHARGER_ID}/commands/{uuid.uuid4()}")

    assert response.status_code == 404


def test_get_command_by_id_404s_when_charger_id_mismatches():
    app, presence, _, transport = _build_app()
    import asyncio

    asyncio.run(_mark_online(presence))
    transport.set_outcome(CHARGER_ID, CommandOutcome(CommandStatus.ACCEPTED, {}))
    client = TestClient(app)

    sent = client.post(
        f"/admin/chargers/{CHARGER_ID}/commands", json={"tenant_id": str(TENANT_ID), "command_type": "Reset"}
    ).json()

    response = client.get(f"/admin/chargers/some-other-charger/commands/{sent['command_id']}")

    assert response.status_code == 404
