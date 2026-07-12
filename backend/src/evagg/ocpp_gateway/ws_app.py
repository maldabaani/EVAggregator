"""The OCPP-J WebSocket transport — the piece Task 2.1's own docstring flags
as untested end-to-end ("verification against a real OCPP charger simulator
is tracked separately... not covered by this module"). Everything this
module does is thin plumbing over already-tested logic
(`ConnectionManager`, `OcppMessageHandlers`): parse the OCPP-J array framing
(`[2, uniqueId, action, payload]` Call / `[3, uniqueId, payload]` CallResult /
`[4, uniqueId, errorCode, errorDescription, errorDetails]` CallError per the
OCPP-J spec), convert JSON-safe values (ISO timestamps, list-of-list meter
readings) into what the handlers expect, and dispatch.

Simplifications versus a real charge point integration (documented, not
hidden): `tenant_id` and the per-charger `credential` are read from query
parameters rather than HTTP Basic Auth in the WS upgrade request, since
that's what a plain `websockets` test client can set most easily; a real
OCPP charge point's upgrade request would carry Basic Auth instead, which a
production transport would need to parse from the handshake headers.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from evagg.ocpp_gateway.connection_manager import SUPPORTED_SUBPROTOCOLS, ConnectionManager
from evagg.ocpp_gateway.message_handlers import OcppMessageHandlers

CALL = 2
CALL_RESULT = 3
CALL_ERROR = 4


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


def build_ocpp_ws_router(connection_manager: ConnectionManager, message_handlers: OcppMessageHandlers) -> APIRouter:
    router = APIRouter()

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

        try:
            while True:
                frame = await websocket.receive_json()
                if not isinstance(frame, list) or len(frame) < 3 or frame[0] != CALL:
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
            await connection_manager.handle_disconnect(charger_id)

    return router
