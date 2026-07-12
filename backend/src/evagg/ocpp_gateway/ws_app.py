"""The OCPP-J WebSocket transport — the piece Task 2.1's own docstring flags
as untested end-to-end ("verification against a real OCPP charger simulator
is tracked separately... not covered by this module"). Everything this
module does is thin plumbing over already-tested logic
(`ConnectionManager`, `OcppMessageHandlers`): parse the OCPP-J array framing
(`[2, uniqueId, action, payload]` Call / `[3, uniqueId, payload]` CallResult /
`[4, uniqueId, errorCode, errorDescription, errorDetails]` CallError per the
OCPP-J spec), convert JSON-safe values (ISO timestamps, list-of-list meter
readings) into what the handlers expect, and dispatch.

`LiveConnectionRegistry` is what makes outbound commands (RemoteStart,
Reset, ...) possible at all: it's the per-process map of `charger_id -> the
actual open WebSocket`, so something that receives a command request (over
NATS — see `evagg.ocpp_gateway.nats_command_transport`) on *this* node can
find the live socket and push a server-initiated Call down it, then match
the charger's CallResult/CallError back to that specific pending request —
a plain request/reply pattern, keyed by the Call's own `uniqueId`, layered
on top of one shared WebSocket receive loop per connection.

Simplifications versus a real charge point integration (documented, not
hidden): `tenant_id` and the per-charger `credential` are read from query
parameters rather than HTTP Basic Auth in the WS upgrade request, since
that's what a plain `websockets` test client can set most easily; a real
OCPP charge point's upgrade request would carry Basic Auth instead, which a
production transport would need to parse from the handshake headers.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from evagg.ocpp_gateway.connection_manager import SUPPORTED_SUBPROTOCOLS, ConnectionManager
from evagg.ocpp_gateway.message_handlers import OcppMessageHandlers

CALL = 2
CALL_RESULT = 3
CALL_ERROR = 4


class RemoteCallTimeout(Exception):
    pass


class RemoteCallRejected(Exception):
    def __init__(self, error_code: str, description: str) -> None:
        super().__init__(f"{error_code}: {description}")
        self.error_code = error_code
        self.description = description


class LiveConnection:
    """One open WebSocket, plus whichever server-initiated Calls are
    currently awaiting a CallResult/CallError from this specific charger."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._pending: dict[str, asyncio.Future] = {}

    async def send_call(self, action: str, payload: dict, timeout_seconds: float) -> dict:
        unique_id = str(uuid.uuid4())
        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[unique_id] = future
        try:
            await self._websocket.send_json([CALL, unique_id, action, payload])
            return await asyncio.wait_for(future, timeout=timeout_seconds)
        except asyncio.TimeoutError as exc:
            raise RemoteCallTimeout(f"{action} timed out waiting for the charge point") from exc
        finally:
            self._pending.pop(unique_id, None)

    def resolve(self, unique_id: str, result: dict) -> bool:
        future = self._pending.get(unique_id)
        if future is None or future.done():
            return False
        future.set_result(result)
        return True

    def reject(self, unique_id: str, error_code: str, description: str) -> bool:
        future = self._pending.get(unique_id)
        if future is None or future.done():
            return False
        future.set_exception(RemoteCallRejected(error_code, description))
        return True


class LiveConnectionRegistry:
    """Per-process only, deliberately — a charger is connected to exactly
    one gateway node's WebSocket at a time, never shared across processes.
    Cross-node addressing (which node is *this* charger even connected to)
    is the presence registry's job (Task 2.1), not this registry's."""

    def __init__(self) -> None:
        self._connections: dict[str, LiveConnection] = {}

    def register(self, charger_id: str, connection: LiveConnection) -> None:
        self._connections[charger_id] = connection

    def unregister(self, charger_id: str, connection: LiveConnection) -> None:
        if self._connections.get(charger_id) is connection:
            del self._connections[charger_id]

    def get(self, charger_id: str) -> LiveConnection | None:
        return self._connections.get(charger_id)


def _prepare_payload(action: str, payload: dict) -> dict:
    """OCPP-J carries timestamps as ISO-8601 strings; the handlers expect
    `datetime` objects (see `handle_start_transaction`/`handle_meter_values`).
    """
    prepared = dict(payload)
    if action == "StartTransaction" and "start_timestamp" in prepared:
        prepared["start_timestamp"] = datetime.fromisoformat(prepared["start_timestamp"])
    if action == "StopTransaction" and "stop_timestamp" in prepared:
        prepared["stop_timestamp"] = datetime.fromisoformat(prepared["stop_timestamp"])
    if action == "MeterValues":
        if "ts" in prepared:
            prepared["ts"] = datetime.fromisoformat(prepared["ts"])
        if "readings" in prepared:
            prepared["readings"] = [tuple(r) for r in prepared["readings"]]
    return prepared


def build_ocpp_ws_router(
    connection_manager: ConnectionManager,
    message_handlers: OcppMessageHandlers,
    live_connections: LiveConnectionRegistry | None = None,
) -> APIRouter:
    router = APIRouter()
    live_connections = live_connections if live_connections is not None else LiveConnectionRegistry()

    @router.websocket("/ocpp/{charger_id}")
    async def ocpp_endpoint(websocket: WebSocket, charger_id: str) -> None:
        tenant_raw = websocket.query_params.get("tenant_id")
        credential = websocket.query_params.get("credential", "")
        requested_protocols = websocket.headers.get("sec-websocket-protocol", "")
        subprotocol = next(
            (p.strip() for p in requested_protocols.split(",") if p.strip() in SUPPORTED_SUBPROTOCOLS), None
        )

        if tenant_raw is None:
            await websocket.close(code=4001, reason="tenant_id query parameter required")
            return
        try:
            tenant_id = uuid.UUID(tenant_raw)
        except ValueError:
            await websocket.close(code=4001, reason="tenant_id must be a UUID")
            return

        handshake = await connection_manager.handle_handshake(charger_id, tenant_id, credential, subprotocol)
        if not handshake.accepted:
            await websocket.close(code=4003, reason=handshake.reason or "handshake rejected")
            return

        await websocket.accept(subprotocol=subprotocol)
        connection = LiveConnection(websocket)
        live_connections.register(charger_id, connection)

        try:
            while True:
                frame = await websocket.receive_json()
                if not isinstance(frame, list) or len(frame) < 2:
                    await websocket.send_json([CALL_ERROR, "unknown", "ProtocolError", "malformed OCPP-J frame", {}])
                    continue

                frame_type = frame[0]

                if frame_type == CALL_RESULT:
                    # A reply to a Call *we* sent (an outbound command) —
                    # route it to that pending request, not through the
                    # inbound-action dispatch below.
                    connection.resolve(frame[1], frame[2] if len(frame) > 2 else {})
                    continue

                if frame_type == CALL_ERROR:
                    connection.reject(
                        frame[1], frame[2] if len(frame) > 2 else "GenericError",
                        frame[3] if len(frame) > 3 else "",
                    )
                    continue

                if frame_type != CALL or len(frame) < 3:
                    await websocket.send_json([CALL_ERROR, "unknown", "ProtocolError", "expected an OCPP Call frame", {}])
                    continue

                unique_id, action = frame[1], frame[2]
                payload = frame[3] if len(frame) > 3 else {}

                await connection_manager.handle_inbound_frame(charger_id)

                try:
                    if action == "Heartbeat":
                        result = {"current_time": datetime.now().isoformat()}
                    else:
                        result = await message_handlers.handle_frame(
                            charger_id, tenant_id, action, _prepare_payload(action, payload)
                        )
                except ValueError as exc:
                    await websocket.send_json([CALL_ERROR, unique_id, "NotSupported", str(exc), {}])
                    continue
                except (KeyError, TypeError) as exc:
                    await websocket.send_json([CALL_ERROR, unique_id, "FormationViolation", str(exc), {}])
                    continue

                await websocket.send_json([CALL_RESULT, unique_id, result])
        except WebSocketDisconnect:
            pass
        finally:
            live_connections.unregister(charger_id, connection)
            await connection_manager.handle_disconnect(charger_id)

    return router
