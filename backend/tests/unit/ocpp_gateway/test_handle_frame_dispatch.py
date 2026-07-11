"""`handle_frame` is a thin adapter over the typed handler methods (Task 2.2's
LLD calls for a single dispatch entrypoint) — this covers the routing itself,
not the business logic already covered in test_message_handlers.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from evagg.ocpp_gateway.authorize import AuthStatus, Authorizer, InMemoryLocalIdTagStore, InMemoryRoamingTokenChecker
from evagg.ocpp_gateway.connectors import InMemoryConnectorStore
from evagg.ocpp_gateway.events import InMemoryEventPublisher
from evagg.ocpp_gateway.meter_values import InMemoryMeterValueSink, MeterValueBuffer
from evagg.ocpp_gateway.message_handlers import OcppMessageHandlers
from evagg.ocpp_gateway.registration import InMemoryChargerRegistry
from evagg.ocpp_gateway.transactions import InMemoryTransactionRepository

TENANT_ID = uuid.uuid4()
CHARGER_ID = "CP-001"


@pytest.fixture
def handlers():
    return OcppMessageHandlers(
        InMemoryChargerRegistry(),
        InMemoryConnectorStore(),
        Authorizer(InMemoryLocalIdTagStore(), InMemoryRoamingTokenChecker()),
        InMemoryTransactionRepository(),
        MeterValueBuffer(InMemoryMeterValueSink()),
        InMemoryEventPublisher(),
    )


@pytest.mark.asyncio
async def test_boot_notification_dispatches_to_correct_handler(handlers):
    response = await handlers.handle_frame(
        CHARGER_ID, TENANT_ID, "BootNotification", {"vendor": "Acme", "model": "X1", "firmware_version": "1.0"}
    )
    assert response["status"] == "Pending"
    assert "interval" in response


@pytest.mark.asyncio
async def test_status_notification_dispatches_to_correct_handler(handlers):
    response = await handlers.handle_frame(
        CHARGER_ID, TENANT_ID, "StatusNotification", {"connector_id": 1, "status": "Available", "error_code": None}
    )
    assert response == {}


@pytest.mark.asyncio
async def test_authorize_dispatches_to_correct_handler(handlers):
    response = await handlers.handle_frame(CHARGER_ID, TENANT_ID, "Authorize", {"id_tag": "TAG-1"})
    assert response == {"id_tag_status": "Invalid"}  # unknown tag, no roaming configured


@pytest.mark.asyncio
async def test_start_and_stop_transaction_dispatch_to_correct_handlers(handlers):
    handlers._authorizer._local_store.set_status("TAG-1", AuthStatus.ACCEPTED)

    start_response = await handlers.handle_frame(
        CHARGER_ID,
        TENANT_ID,
        "StartTransaction",
        {
            "connector_id": 1,
            "id_tag": "TAG-1",
            "meter_start": 0,
            "start_timestamp": datetime.now(timezone.utc),
        },
    )
    assert start_response["id_tag_status"] == "Accepted"

    stop_response = await handlers.handle_frame(
        CHARGER_ID,
        TENANT_ID,
        "StopTransaction",
        {
            "transaction_id": start_response["transaction_id"],
            "meter_stop": 100,
            "stop_timestamp": datetime.now(timezone.utc),
        },
    )
    assert stop_response["id_tag_status"] == "Accepted"


@pytest.mark.asyncio
async def test_meter_values_dispatches_to_correct_handler(handlers):
    response = await handlers.handle_frame(
        CHARGER_ID,
        TENANT_ID,
        "MeterValues",
        {
            "transaction_id": str(uuid.uuid4()),
            "ts": datetime.now(timezone.utc),
            "readings": [("Energy.Active.Import.Register", 1.0, "kWh")],
        },
    )
    assert response == {}


@pytest.mark.asyncio
async def test_unsupported_action_raises():
    handlers = OcppMessageHandlers(
        InMemoryChargerRegistry(),
        InMemoryConnectorStore(),
        Authorizer(InMemoryLocalIdTagStore(), InMemoryRoamingTokenChecker()),
        InMemoryTransactionRepository(),
        MeterValueBuffer(InMemoryMeterValueSink()),
        InMemoryEventPublisher(),
    )
    with pytest.raises(ValueError):
        await handlers.handle_frame(CHARGER_ID, TENANT_ID, "NotARealAction", {})
