import uuid

import pytest

from evagg.ocpp_gateway.bus_event_publisher import BusEventPublisher
from evagg.ocpp_gateway.event_bus import InMemoryEventBus

TENANT_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_publish_disconnected_uses_correct_subject_hierarchy():
    bus = InMemoryEventBus()
    publisher = BusEventPublisher(bus)

    await publisher.publish_disconnected(TENANT_ID, "CP-1")

    assert bus.published[0].subject == f"ocpp.{TENANT_ID}.CP-1.disconnected"
    assert bus.published[0].payload == {"charger_id": "CP-1"}


@pytest.mark.asyncio
async def test_publish_status_notification_uses_correct_subject_hierarchy():
    bus = InMemoryEventBus()
    publisher = BusEventPublisher(bus)

    await publisher.publish_status_notification(TENANT_ID, "CP-1", 1, "Faulted", "GroundFailure")

    assert bus.published[0].subject == f"ocpp.{TENANT_ID}.CP-1.status_notification"
    assert bus.published[0].payload["status"] == "Faulted"


@pytest.mark.asyncio
async def test_publish_stop_transaction_uses_correct_subject_hierarchy():
    bus = InMemoryEventBus()
    publisher = BusEventPublisher(bus)
    transaction_id = uuid.uuid4()

    await publisher.publish_stop_transaction(TENANT_ID, "CP-1", transaction_id)

    assert bus.published[0].subject == f"ocpp.{TENANT_ID}.CP-1.stop_transaction"
    assert bus.published[0].payload["transaction_id"] == str(transaction_id)
