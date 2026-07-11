"""Task 2.1/2.4 — Redis-backed live presence registry.

Key pattern `presence:{charger_id}` -> `{status, tenant_id, node_id,
protocol_version, connected_at, last_seen}`, TTL = 2x the charger's OCPP
`HeartbeatInterval`, refreshed on every inbound frame (per engineering
standards). `tenant_id` rides along so a heartbeat sweep can publish
`ocpp.{tenant}.{charger}.disconnected` without a separate lookup.

The registry stores an explicit `status` field rather than relying on Redis's
own key-expiry-as-offline-signal: a background sweep (see `ConnectionManager.
check_and_expire_heartbeats`) compares `last_seen` against now and writes
`status: offline` itself, because marking offline also needs to trigger that
NATS publish — a side effect a bare Redis TTL expiry can't drive.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass
class PresenceState:
    charger_id: str
    tenant_id: str
    status: str  # 'online' | 'offline'
    node_id: str
    protocol_version: str
    connected_at: float
    last_seen: float


def presence_key(charger_id: str) -> str:
    return f"presence:{charger_id}"


class PresenceRegistry(Protocol):
    async def mark_online(
        self, charger_id: str, tenant_id: uuid.UUID, node_id: str, protocol_version: str, ttl_seconds: int
    ) -> None: ...

    async def refresh(self, charger_id: str, ttl_seconds: int) -> None: ...

    async def mark_offline(self, charger_id: str, grace_ttl_seconds: int = 60) -> None: ...

    async def get(self, charger_id: str) -> PresenceState | None: ...


class RedisPresenceRegistry:
    def __init__(self, redis_client) -> None:
        self._redis = redis_client

    async def mark_online(
        self, charger_id: str, tenant_id: uuid.UUID, node_id: str, protocol_version: str, ttl_seconds: int
    ) -> None:
        now = time.time()
        state = PresenceState(
            charger_id=charger_id,
            tenant_id=str(tenant_id),
            status="online",
            node_id=node_id,
            protocol_version=protocol_version,
            connected_at=now,
            last_seen=now,
        )
        await self._redis.set(presence_key(charger_id), json.dumps(asdict(state)), ex=ttl_seconds)

    async def refresh(self, charger_id: str, ttl_seconds: int) -> None:
        existing = await self.get(charger_id)
        if existing is None:
            return
        existing.last_seen = time.time()
        existing.status = "online"
        await self._redis.set(presence_key(charger_id), json.dumps(asdict(existing)), ex=ttl_seconds)

    async def mark_offline(self, charger_id: str, grace_ttl_seconds: int = 60) -> None:
        existing = await self.get(charger_id)
        if existing is None:
            return
        existing.status = "offline"
        await self._redis.set(presence_key(charger_id), json.dumps(asdict(existing)), ex=grace_ttl_seconds)

    async def get(self, charger_id: str) -> PresenceState | None:
        raw = await self._redis.get(presence_key(charger_id))
        if raw is None:
            return None
        payload = json.loads(raw)
        return PresenceState(**payload)


class InMemoryPresenceRegistry:
    """Reference implementation for unit tests — same interface as the Redis
    one, no network involved."""

    def __init__(self) -> None:
        self._states: dict[str, PresenceState] = {}

    async def mark_online(
        self, charger_id: str, tenant_id: uuid.UUID, node_id: str, protocol_version: str, ttl_seconds: int
    ) -> None:
        now = time.time()
        self._states[charger_id] = PresenceState(charger_id, str(tenant_id), "online", node_id, protocol_version, now, now)

    async def refresh(self, charger_id: str, ttl_seconds: int) -> None:
        existing = self._states.get(charger_id)
        if existing is None:
            return
        existing.last_seen = time.time()
        existing.status = "online"

    async def mark_offline(self, charger_id: str, grace_ttl_seconds: int = 60) -> None:
        existing = self._states.get(charger_id)
        if existing is None:
            return
        existing.status = "offline"

    async def get(self, charger_id: str) -> PresenceState | None:
        return self._states.get(charger_id)
