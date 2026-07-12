"""Real-NATS integration coverage for the outbound remote-command wiring
(Task 2.3's docstring, finally implemented): `NatsCommandTransport` (the
sender, wherever `RemoteCommandService` runs) and `serve_commands` (the
receiver, running alongside the OCPP gateway node's live WebSocket
connections). Both halves are exercised against a real local NATS server —
this is what only a real broker can prove: that a request published from
one client actually reaches a subscriber running as a separate connection,
round-trips through a live (faked) WebSocket, and the reply comes back
correctly on the other side.
"""

from __future__ import annotations

import uuid

import pytest

from evagg.core.config import settings
from evagg.ocpp_gateway.commands import CommandStatus
from evagg.ocpp_gateway.nats_command_transport import NatsCommandTransport, serve_commands
from evagg.ocpp_gateway.ws_app import LiveConnection, LiveConnectionRegistry
from conftest import requires_nats

NODE_ID = "test-node"


class _AutoAcceptingWebSocket:
    """Stands in for the charge point's side of the WebSocket — replies
    Accepted to whatever Call it receives, immediately."""

    def __init__(self) -> None:
        self.sent: list[list] = []

    async def send_json(self, frame: list) -> None:
        self.sent.append(frame)


@requires_nats
@pytest.mark.asyncio
async def test_command_reaches_a_connected_charger_and_returns_accepted():
    live_connections = LiveConnectionRegistry()
    ws = _AutoAcceptingWebSocket()
    connection = LiveConnection(ws)
    live_connections.register("CP-cmd-1", connection)

    server_nc = await serve_commands(settings.nats_url, NODE_ID, live_connections)

    async def _charger_replies_to_whatever_it_receives():
        # The receiver's send_call already wrote the Call frame to `ws.sent`
        # synchronously before awaiting the reply — poll for it, then
        # resolve it exactly like the real WS receive loop would on a
        # CallResult frame.
        import asyncio

        for _ in range(50):
            if ws.sent:
                unique_id = ws.sent[-1][1]
                connection.resolve(unique_id, {"status": "Accepted"})
                return
            await asyncio.sleep(0.02)
        raise AssertionError("charger never received the Call")

    transport = NatsCommandTransport(settings.nats_url)
    await transport.connect()
    try:
        import asyncio

        replier_task = asyncio.create_task(_charger_replies_to_whatever_it_receives())
        outcome = await transport.send(
            node_id=NODE_ID,
            charger_id="CP-cmd-1",
            command_id=uuid.uuid4(),
            command_type="Reset",
            payload={"type": "Soft"},
            timeout_seconds=5.0,
        )
        await replier_task

        assert outcome.status == CommandStatus.ACCEPTED
        assert outcome.result == {"status": "Accepted"}
        assert ws.sent[0][2] == "Reset"
        assert ws.sent[0][3] == {"type": "Soft"}
    finally:
        await transport.close()
        await server_nc.close()


@requires_nats
@pytest.mark.asyncio
async def test_command_to_a_charger_not_connected_on_this_node_is_rejected():
    live_connections = LiveConnectionRegistry()  # nothing registered
    server_nc = await serve_commands(settings.nats_url, NODE_ID, live_connections)

    transport = NatsCommandTransport(settings.nats_url)
    await transport.connect()
    try:
        outcome = await transport.send(
            node_id=NODE_ID,
            charger_id="CP-not-connected",
            command_id=uuid.uuid4(),
            command_type="Reset",
            payload={},
            timeout_seconds=5.0,
        )
        assert outcome.status == CommandStatus.REJECTED
        assert "not connected" in outcome.result["reason"]
    finally:
        await transport.close()
        await server_nc.close()


@requires_nats
@pytest.mark.asyncio
async def test_command_to_a_node_with_no_listener_times_out_or_is_rejected():
    """No `serve_commands` subscriber is running for this node at all —
    NATS core pub/sub has no durable queue to hold the request, so this
    should fail fast (no responders) rather than hang for the full timeout."""
    transport = NatsCommandTransport(settings.nats_url)
    await transport.connect()
    try:
        outcome = await transport.send(
            node_id="node-with-nobody-listening",
            charger_id="CP-x",
            command_id=uuid.uuid4(),
            command_type="Reset",
            payload={},
            timeout_seconds=2.0,
        )
        assert outcome.status in (CommandStatus.TIMED_OUT, CommandStatus.REJECTED)
    finally:
        await transport.close()
