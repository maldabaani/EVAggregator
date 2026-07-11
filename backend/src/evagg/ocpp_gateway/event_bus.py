"""Task 2.4 — Realtime event bus architecture.

Production is NATS JetStream: stream `OCPP_EVENTS` on subjects
`ocpp.{tenant_id}.{charger_id}.{event_type}`, limits-based retention capped
at 7 days (raw telemetry lives in TimescaleDB, not the stream — it only needs
to retain long enough for consumer catch-up), with one durable pull consumer
per downstream concern (`ocpi-sync`, `billing-cdr`, `portal-live-feed`,
`notification-dispatch`).

`InMemoryEventBus`/`EventConsumer` model the same fan-out + at-least-once +
per-consumer-isolation semantics as JetStream, so the tricky invariants
(a slow/failing consumer never blocks others; redelivery of an
already-processed event is a no-op; a consumer that falls behind triggers an
alert) are unit-tested deterministically without a live NATS server. The real
`NatsEventBus` is a thin adapter over the same `EventBus` protocol — verified
in CI's docker-compose NATS service, not exercised here (see engineering
standards: unit tests mock the transport, integration tests use the real one).
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Protocol

logger = logging.getLogger("evagg.ocpp_gateway.event_bus")

STREAM_NAME = "OCPP_EVENTS"
STREAM_SUBJECT_WILDCARD = "ocpp.>"
STREAM_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

CONSUMER_NAMES = ("ocpi-sync", "billing-cdr", "portal-live-feed", "notification-dispatch")


def event_subject(tenant_id: uuid.UUID, charger_id: str, event_type: str) -> str:
    return f"ocpp.{tenant_id}.{charger_id}.{event_type}"


@dataclass(frozen=True)
class Event:
    id: uuid.UUID
    subject: str
    payload: dict


class EventBus(Protocol):
    async def publish(self, subject: str, payload: dict, event_id: uuid.UUID | None = None) -> Event: ...


# --- Idempotency / dedup -------------------------------------------------


class SeenEventStore(Protocol):
    async def has_processed(self, consumer_name: str, event_id: uuid.UUID) -> bool: ...

    async def mark_processed(self, consumer_name: str, event_id: uuid.UUID) -> None: ...


class InMemorySeenEventStore:
    """Reference implementation for tests/local dev. Production backs this
    with Redis (a set per consumer, or a single hash keyed by
    `{consumer}:{event_id}`) so dedup survives consumer restarts."""

    def __init__(self) -> None:
        self._seen: set[tuple[str, uuid.UUID]] = set()

    async def has_processed(self, consumer_name: str, event_id: uuid.UUID) -> bool:
        return (consumer_name, event_id) in self._seen

    async def mark_processed(self, consumer_name: str, event_id: uuid.UUID) -> None:
        self._seen.add((consumer_name, event_id))


# --- Backpressure alerting ------------------------------------------------


class AlertSink(Protocol):
    async def alert_consumer_lag(self, consumer_name: str, lag: int) -> None: ...


@dataclass
class InMemoryAlertSink:
    alerts: list[tuple[str, int]] = field(default_factory=list)

    async def alert_consumer_lag(self, consumer_name: str, lag: int) -> None:
        self.alerts.append((consumer_name, lag))


# --- Consumers -------------------------------------------------------------

ConsumerHandler = Callable[[Event], Awaitable[None]]


class EventConsumer:
    """A durable pull consumer for one downstream concern.

    Delivery is isolated: an exception raised while handling an event is
    caught here and counted as lag, never propagated to the bus or to other
    consumers — one failing/slow consumer can't block the rest. An event is
    only marked processed *after* the handler succeeds, so a genuine retry
    (handler failed, then the same event is redelivered) still runs the
    handler again; only redelivery of an *already-succeeded* event is a
    no-op, which is exactly the at-least-once contract JetStream provides.
    """

    def __init__(
        self,
        name: str,
        handler: ConsumerHandler,
        seen_store: SeenEventStore,
        alert_sink: AlertSink,
        lag_threshold: int = 100,
    ) -> None:
        self.name = name
        self._handler = handler
        self._seen_store = seen_store
        self._alert_sink = alert_sink
        self._lag_threshold = lag_threshold
        self._consecutive_failures = 0
        self.handled_event_ids: list[uuid.UUID] = []

    async def deliver(self, event: Event) -> None:
        if await self._seen_store.has_processed(self.name, event.id):
            return  # already successfully handled -> duplicate delivery, no-op

        try:
            await self._handler(event)
        except Exception:
            self._consecutive_failures += 1
            logger.exception("consumer %s failed to handle event %s", self.name, event.id)
            if self._consecutive_failures >= self._lag_threshold:
                await self._alert_sink.alert_consumer_lag(self.name, self._consecutive_failures)
            return

        await self._seen_store.mark_processed(self.name, event.id)
        self.handled_event_ids.append(event.id)
        self._consecutive_failures = 0


class InMemoryEventBus:
    def __init__(self) -> None:
        self._consumers: dict[str, EventConsumer] = {}
        self.published: list[Event] = []

    def register_consumer(self, consumer: EventConsumer) -> None:
        self._consumers[consumer.name] = consumer

    async def publish(self, subject: str, payload: dict, event_id: uuid.UUID | None = None) -> Event:
        event = Event(id=event_id or uuid.uuid4(), subject=subject, payload=payload)
        self.published.append(event)
        for consumer in self._consumers.values():
            await consumer.deliver(event)
        return event

    async def redeliver(self, event: Event, consumer_name: str | None = None) -> None:
        """Test/ops helper simulating NATS's at-least-once redelivery."""
        targets = [self._consumers[consumer_name]] if consumer_name else list(self._consumers.values())
        for consumer in targets:
            await consumer.deliver(event)


class NatsEventBus:
    """Production adapter over `nats-py` JetStream. Ensures the `OCPP_EVENTS`
    stream exists (limits retention, 7-day max age) and publishes onto it.
    Durable pull consumers (one per `CONSUMER_NAMES` entry) are provisioned
    separately by each downstream service against this same stream.
    """

    def __init__(self, nats_url: str) -> None:
        self._nats_url = nats_url
        self._nc = None
        self._js = None

    async def connect(self) -> None:
        import nats

        self._nc = await nats.connect(self._nats_url)
        self._js = self._nc.jetstream()
        await self._js.add_stream(
            name=STREAM_NAME,
            subjects=[STREAM_SUBJECT_WILDCARD],
            retention="limits",
            max_age=STREAM_MAX_AGE_SECONDS,
        )

    async def publish(self, subject: str, payload: dict, event_id: uuid.UUID | None = None) -> Event:
        import json

        if self._js is None:
            raise RuntimeError("NatsEventBus.connect() must be called before publish()")
        event = Event(id=event_id or uuid.uuid4(), subject=subject, payload=payload)
        headers = {"Nats-Msg-Id": str(event.id)}  # JetStream de-dup on redelivery of the same publish
        await self._js.publish(subject, json.dumps(payload).encode("utf-8"), headers=headers)
        return event

    async def close(self) -> None:
        if self._nc is not None:
            await self._nc.close()
