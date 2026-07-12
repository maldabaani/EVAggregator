"""Task 2.4 unit tests — fan-out, per-consumer isolation, backpressure
alerting, and idempotent redelivery, all against `InMemoryEventBus` (no real
NATS server; the standards call for mocking the transport in unit tests)."""

from __future__ import annotations

import pytest

from evagg.ocpp_gateway.event_bus import (
    Event,
    EventConsumer,
    InMemoryAlertSink,
    InMemoryEventBus,
    InMemorySeenEventStore,
)


def _make_consumer(name: str, seen_store, alert_sink, handler=None, lag_threshold: int = 3) -> EventConsumer:
    calls: list[Event] = []

    async def default_handler(event: Event) -> None:
        calls.append(event)

    consumer = EventConsumer(name, handler or default_handler, seen_store, alert_sink, lag_threshold=lag_threshold)
    consumer.calls = calls  # type: ignore[attr-defined]  (test convenience)
    return consumer


@pytest.mark.asyncio
async def test_event_published_reaches_all_registered_consumers():
    bus = InMemoryEventBus()
    seen_store = InMemorySeenEventStore()
    alert_sink = InMemoryAlertSink()
    consumers = [_make_consumer(name, seen_store, alert_sink) for name in ("ocpi-sync", "billing-cdr", "portal-live-feed", "notification-dispatch")]
    for consumer in consumers:
        bus.register_consumer(consumer)

    event = await bus.publish("ocpp.tenant-1.CP-1.status_notification", {"status": "Available"})

    for consumer in consumers:
        assert consumer.calls == [event]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_one_consumer_failure_does_not_block_others():
    bus = InMemoryEventBus()
    seen_store = InMemorySeenEventStore()
    alert_sink = InMemoryAlertSink()

    async def failing_handler(event: Event) -> None:
        raise RuntimeError("downstream service unavailable")

    failing_consumer = _make_consumer("billing-cdr", seen_store, alert_sink, handler=failing_handler)
    healthy_consumer = _make_consumer("portal-live-feed", seen_store, alert_sink)
    bus.register_consumer(failing_consumer)
    bus.register_consumer(healthy_consumer)

    event = await bus.publish("ocpp.tenant-1.CP-1.stop_transaction", {"transaction_id": "abc"})

    assert healthy_consumer.calls == [event]  # type: ignore[attr-defined]
    assert failing_consumer.handled_event_ids == []  # never marked processed since it failed
    assert healthy_consumer.handled_event_ids == [event.id]


@pytest.mark.asyncio
async def test_consumer_lag_above_threshold_triggers_alert():
    bus = InMemoryEventBus()
    seen_store = InMemorySeenEventStore()
    alert_sink = InMemoryAlertSink()

    async def always_fails(event: Event) -> None:
        raise RuntimeError("stuck")

    consumer = _make_consumer("notification-dispatch", seen_store, alert_sink, handler=always_fails, lag_threshold=3)
    bus.register_consumer(consumer)

    for _ in range(2):
        await bus.publish("ocpp.tenant-1.CP-1.status_notification", {})
    assert alert_sink.alerts == []  # below threshold

    await bus.publish("ocpp.tenant-1.CP-1.status_notification", {})

    assert alert_sink.alerts == [("notification-dispatch", 3)]


@pytest.mark.asyncio
async def test_redelivered_event_does_not_cause_duplicate_side_effect():
    bus = InMemoryEventBus()
    seen_store = InMemorySeenEventStore()
    alert_sink = InMemoryAlertSink()
    consumer = _make_consumer("ocpi-sync", seen_store, alert_sink)
    bus.register_consumer(consumer)

    event = await bus.publish("ocpp.tenant-1.CP-1.stop_transaction", {"transaction_id": "abc"})
    # Simulate NATS's at-least-once redelivery of the same message.
    await bus.redeliver(event)
    await bus.redeliver(event)

    assert consumer.calls == [event]  # type: ignore[attr-defined]  # handled exactly once


@pytest.mark.asyncio
async def test_redelivery_after_failure_does_retry_the_handler():
    """Distinguishes "duplicate delivery of an already-succeeded event"
    (must be a no-op) from "redelivery after a failed attempt" (must retry) —
    at-least-once only guarantees the former is safe to dedup."""
    bus = InMemoryEventBus()
    seen_store = InMemorySeenEventStore()
    alert_sink = InMemoryAlertSink()

    attempts = {"count": 0}

    async def fails_once_then_succeeds(event: Event) -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("transient failure")

    consumer = _make_consumer("billing-cdr", seen_store, alert_sink, handler=fails_once_then_succeeds)
    bus.register_consumer(consumer)

    event = await bus.publish("ocpp.tenant-1.CP-1.stop_transaction", {})
    assert consumer.handled_event_ids == []  # first attempt failed

    await bus.redeliver(event)

    assert consumer.handled_event_ids == [event.id]  # retry succeeded
    assert attempts["count"] == 2
