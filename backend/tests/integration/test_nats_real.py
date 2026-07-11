"""Real-NATS integration coverage for `NatsEventBus` (Task 2.4). The unit
tests for the event bus (tests/unit/ocpp_gateway/test_event_bus.py) exercise
`InMemoryEventBus` — deliberately, per the module's own docstring, since the
fan-out/dedup/backpressure invariants are what's worth testing
deterministically. This instead runs the thin `NatsEventBus` adapter against
a real NATS JetStream server, checking the two things only a real server can
prove: the stream actually gets created, and JetStream's own `Nats-Msg-Id`
header dedup actually suppresses a duplicate publish.
"""

from __future__ import annotations

import uuid

import pytest

from evagg.core.config import settings
from evagg.ocpp_gateway.event_bus import STREAM_NAME, NatsEventBus, event_subject
from tests.integration.conftest import requires_nats


@requires_nats
@pytest.mark.asyncio
async def test_nats_event_bus_publishes_onto_the_ocpp_events_stream():
    bus = NatsEventBus(settings.nats_url)
    await bus.connect()
    try:
        subject = event_subject(uuid.uuid4(), "CP-001", "StatusNotification")

        await bus.publish(subject, {"status": "Available"})

        info = await bus._js.stream_info(STREAM_NAME)
        assert info.state.messages >= 1
    finally:
        await bus.close()


@requires_nats
@pytest.mark.asyncio
async def test_nats_event_bus_dedupes_republish_of_the_same_event_id():
    bus = NatsEventBus(settings.nats_url)
    await bus.connect()
    try:
        subject = event_subject(uuid.uuid4(), "CP-002", "StatusNotification")
        event_id = uuid.uuid4()

        before = await bus._js.stream_info(STREAM_NAME)
        await bus.publish(subject, {"status": "Available"}, event_id=event_id)
        await bus.publish(subject, {"status": "Available"}, event_id=event_id)  # same Nats-Msg-Id
        after = await bus._js.stream_info(STREAM_NAME)

        # JetStream's own dedup means the second publish adds no new message
        # to the stream, even though `publish()` reports success either way
        # (from the publisher's point of view, both calls succeeded — the
        # dedup happens server-side, invisibly to this client code).
        assert after.state.messages - before.state.messages == 1
    finally:
        await bus.close()
