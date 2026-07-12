"""Task 2.1 — WebSocket Connection Manager.

Ties together subprotocol negotiation, credential verification, the presence
registry, boot-notification idempotency, and session recovery. This is the
highest-risk task in the backlog per the doc's own flag — the logic here is
unit-tested in isolation (mocked presence/credentials/transactions/events);
end-to-end verification against a real OCPP charger simulator is tracked
separately as an integration test, not covered by this module.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from evagg.ocpp_gateway.credentials import CredentialVerifier
from evagg.ocpp_gateway.events import EventPublisher
from evagg.ocpp_gateway.presence import PresenceRegistry
from evagg.ocpp_gateway.registration import BootResult, ChargerRegistry
from evagg.ocpp_gateway.transactions import ActiveTransaction, TransactionRepository

SUPPORTED_SUBPROTOCOLS = ("ocpp1.6", "ocpp2.0.1")


@dataclass
class HandshakeResult:
    accepted: bool
    protocol_version: str | None = None
    reason: str | None = None


@dataclass
class ReconnectResult:
    handshake: HandshakeResult
    resumed_transaction: ActiveTransaction | None = None


def resolve_handler_codepath(subprotocol: str | None) -> str | None:
    """Maps the negotiated `Sec-WebSocket-Protocol` value to the message
    handler codepath (Task 2.2) that should process frames on this
    connection. Returns None for anything unsupported."""
    if subprotocol in SUPPORTED_SUBPROTOCOLS:
        return subprotocol
    return None


class ConnectionManager:
    def __init__(
        self,
        presence: PresenceRegistry,
        credentials: CredentialVerifier,
        transactions: TransactionRepository,
        charger_registry: ChargerRegistry,
        events: EventPublisher,
        node_id: str,
        default_heartbeat_interval_seconds: int = 300,
    ) -> None:
        self._presence = presence
        self._credentials = credentials
        self._transactions = transactions
        self._charger_registry = charger_registry
        self._events = events
        self._node_id = node_id
        self._default_heartbeat_interval_seconds = default_heartbeat_interval_seconds

    async def handle_handshake(
        self, charger_id: str, tenant_id: uuid.UUID, credential: str, subprotocol: str | None
    ) -> HandshakeResult:
        protocol_version = resolve_handler_codepath(subprotocol)
        if protocol_version is None:
            return HandshakeResult(accepted=False, reason="unsupported subprotocol")

        if not await self._credentials.verify(charger_id, credential):
            return HandshakeResult(accepted=False, reason="invalid credentials")

        await self._presence.mark_online(
            charger_id,
            tenant_id=tenant_id,
            node_id=self._node_id,
            protocol_version=protocol_version,
            ttl_seconds=self._default_heartbeat_interval_seconds * 2,
        )
        return HandshakeResult(accepted=True, protocol_version=protocol_version)

    async def handle_reconnect(
        self, charger_id: str, tenant_id: uuid.UUID, credential: str, subprotocol: str | None
    ) -> ReconnectResult:
        """Like `handle_handshake`, but also decides whether an in-flight
        transaction should resume. Recovery eligibility is read from presence
        *before* this reconnect overwrites it — a stale/offline/missing entry
        means the reconnect happened after the heartbeat TTL window, and the
        transaction must not be silently resumed."""
        resumed_transaction: ActiveTransaction | None = None
        prior_state = await self._presence.get(charger_id)
        eligible_for_recovery = prior_state is not None and prior_state.status == "online"

        handshake = await self.handle_handshake(charger_id, tenant_id, credential, subprotocol)
        if handshake.accepted and eligible_for_recovery:
            resumed_transaction = await self._transactions.get_active_transaction(charger_id)

        return ReconnectResult(handshake=handshake, resumed_transaction=resumed_transaction)

    async def handle_inbound_frame(self, charger_id: str, heartbeat_interval_seconds: int | None = None) -> None:
        ttl = (heartbeat_interval_seconds or self._default_heartbeat_interval_seconds) * 2
        await self._presence.refresh(charger_id, ttl_seconds=ttl)

    async def handle_disconnect(self, charger_id: str) -> None:
        """A clean WebSocket close (as opposed to `check_and_expire_heartbeats`
        sweeping a silently-vanished connection) — marks offline and
        publishes the disconnect event immediately rather than waiting for
        the next heartbeat-expiry sweep."""
        state = await self._presence.get(charger_id)
        if state is None or state.status != "online":
            return
        await self._presence.mark_offline(charger_id)
        await self._events.publish_disconnected(tenant_id=uuid.UUID(state.tenant_id), charger_id=charger_id)

    async def check_and_expire_heartbeats(
        self, charger_ids: list[str], heartbeat_interval_seconds: int, now: float | None = None
    ) -> list[str]:
        """Sweep for missed heartbeats. Returns the charger_ids newly marked
        offline this pass (already published as disconnect events)."""
        now = now if now is not None else time.time()
        newly_offline: list[str] = []
        for charger_id in charger_ids:
            state = await self._presence.get(charger_id)
            if state is None or state.status != "online":
                continue
            if now - state.last_seen > heartbeat_interval_seconds * 2:
                await self._presence.mark_offline(charger_id)
                await self._events.publish_disconnected(tenant_id=uuid.UUID(state.tenant_id), charger_id=charger_id)
                newly_offline.append(charger_id)
        return newly_offline

    async def handle_boot_notification(
        self,
        charger_id: str,
        tenant_id: uuid.UUID,
        vendor: str | None,
        model: str | None,
        firmware_version: str | None,
    ) -> BootResult:
        return await self._charger_registry.upsert_on_boot(charger_id, tenant_id, vendor, model, firmware_version)
