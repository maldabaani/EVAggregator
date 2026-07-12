"""Unit tests for `LiveConnection`/`LiveConnectionRegistry` — the
server-initiated Call/CallResult pairing that makes outbound commands
possible. The actual WebSocket accept/receive loop in `build_ocpp_ws_router`
is exercised end-to-end via a real `websockets` client instead (see the
module's own docstring on why — same rationale as Task 2.1's connection
manager), not re-tested here with fakes standing in for the transport.
"""

from __future__ import annotations

import asyncio

import pytest

from evagg.ocpp_gateway.ws_app import (
    LiveConnection,
    LiveConnectionRegistry,
    RemoteCallRejected,
    RemoteCallTimeout,
)


class _FakeWebSocket:
    def __init__(self) -> None:
        self.sent: list[list] = []

    async def send_json(self, frame: list) -> None:
        self.sent.append(frame)


@pytest.mark.asyncio
async def test_send_call_resolves_on_matching_call_result():
    ws = _FakeWebSocket()
    connection = LiveConnection(ws)

    async def charger_replies():
        await asyncio.sleep(0.01)
        unique_id = ws.sent[0][1]
        connection.resolve(unique_id, {"status": "Accepted"})

    task = asyncio.create_task(charger_replies())
    result = await connection.send_call("Reset", {"type": "Soft"}, timeout_seconds=1.0)
    await task

    assert result == {"status": "Accepted"}
    assert ws.sent[0][0] == 2  # CALL
    assert ws.sent[0][2] == "Reset"
    assert ws.sent[0][3] == {"type": "Soft"}


@pytest.mark.asyncio
async def test_send_call_raises_on_call_error():
    ws = _FakeWebSocket()
    connection = LiveConnection(ws)

    async def charger_rejects():
        await asyncio.sleep(0.01)
        unique_id = ws.sent[0][1]
        connection.reject(unique_id, "NotSupported", "unknown command")

    task = asyncio.create_task(charger_rejects())
    with pytest.raises(RemoteCallRejected, match="NotSupported"):
        await connection.send_call("UnlockConnector", {"connector_id": 1}, timeout_seconds=1.0)
    await task


@pytest.mark.asyncio
async def test_send_call_times_out_if_charger_never_replies():
    ws = _FakeWebSocket()
    connection = LiveConnection(ws)

    with pytest.raises(RemoteCallTimeout):
        await connection.send_call("Reset", {"type": "Hard"}, timeout_seconds=0.05)


@pytest.mark.asyncio
async def test_resolve_and_reject_ignore_unknown_or_already_done_unique_ids():
    ws = _FakeWebSocket()
    connection = LiveConnection(ws)

    assert connection.resolve("no-such-id", {}) is False
    assert connection.reject("no-such-id", "Err", "desc") is False


@pytest.mark.asyncio
async def test_a_stray_call_result_after_timeout_does_not_crash():
    ws = _FakeWebSocket()
    connection = LiveConnection(ws)

    with pytest.raises(RemoteCallTimeout):
        await connection.send_call("Reset", {}, timeout_seconds=0.02)

    # The pending entry is cleaned up on timeout — a late reply arriving
    # after the caller has given up must be a no-op, not an exception.
    assert connection.resolve("whatever-arrived-late", {}) is False


def test_registry_register_get_unregister():
    registry = LiveConnectionRegistry()
    ws = _FakeWebSocket()
    connection = LiveConnection(ws)

    assert registry.get("CP-1") is None
    registry.register("CP-1", connection)
    assert registry.get("CP-1") is connection

    registry.unregister("CP-1", connection)
    assert registry.get("CP-1") is None


def test_registry_unregister_ignores_stale_connection_after_reconnect():
    """A slow-to-close old connection's `finally` block must not unregister
    a newer connection that already replaced it in the registry."""
    registry = LiveConnectionRegistry()
    old_connection = LiveConnection(_FakeWebSocket())
    new_connection = LiveConnection(_FakeWebSocket())

    registry.register("CP-1", old_connection)
    registry.register("CP-1", new_connection)  # reconnect races ahead
    registry.unregister("CP-1", old_connection)  # old connection's cleanup runs late

    assert registry.get("CP-1") is new_connection
