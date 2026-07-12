"""POST /admin/chargers/{charger_id}/commands — the first HTTP entry point
onto `RemoteCommandService.send_command` (Task 2.3), which existed as a
tested service with no router mounting it anywhere.

Restricted to the standard OCPP 1.6 CSMS-initiated commands that make sense
as a generic "send arbitrary command" panel; `SetChargingProfile` and
`UpdateFirmware` already have their own specialized service methods
(capacity validation, firmware-tracking side effects) and their own routers
are a separate concern, not this generic passthrough.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from evagg.ocpp_gateway.commands import (
    ChargerOfflineError,
    CommandLogRecord,
    CommandLogStore,
    CommandResult,
    RemoteCommandService,
)

SUPPORTED_COMMAND_TYPES = frozenset(
    {
        "RemoteStartTransaction",
        "RemoteStopTransaction",
        "Reset",
        "UnlockConnector",
        "ChangeConfiguration",
        "GetConfiguration",
        "ClearCache",
        "TriggerMessage",
        "GetDiagnostics",
    }
)


class SendCommandRequest(BaseModel):
    tenant_id: uuid.UUID
    command_type: str
    payload: dict = {}
    timeout_seconds: float | None = None


def _result_dict(result: CommandResult) -> dict:
    return {"command_id": str(result.command_id), "status": result.status.value, "result": result.result}


def _record_dict(record: CommandLogRecord) -> dict:
    return {
        "command_id": str(record.id),
        "charger_id": record.charger_id,
        "tenant_id": str(record.tenant_id),
        "type": record.type,
        "status": record.status.value,
        "requested_at": record.requested_at.isoformat(),
        "responded_at": record.responded_at.isoformat() if record.responded_at else None,
        "result": record.result,
    }


def build_command_router(service_dependency, command_log_dependency) -> APIRouter:
    router = APIRouter(prefix="/admin/chargers/{charger_id}/commands", tags=["ocpp-commands"])

    @router.post("")
    async def send_command(
        charger_id: str,
        body: SendCommandRequest,
        service: RemoteCommandService = Depends(service_dependency),
    ) -> dict:
        if body.command_type not in SUPPORTED_COMMAND_TYPES:
            raise HTTPException(
                status_code=422,
                detail=f"command_type must be one of {sorted(SUPPORTED_COMMAND_TYPES)}",
            )
        try:
            result = await service.send_command(
                charger_id, body.tenant_id, body.command_type, body.payload, body.timeout_seconds
            )
        except ChargerOfflineError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return _result_dict(result)

    @router.get("")
    async def list_recent_commands(
        charger_id: str,
        limit: int = 20,
        command_log: CommandLogStore = Depends(command_log_dependency),
    ) -> list[dict]:
        records = await command_log.list_recent(charger_id, limit)
        return [_record_dict(record) for record in records]

    @router.get("/{command_id}")
    async def get_command(
        charger_id: str,
        command_id: uuid.UUID,
        command_log: CommandLogStore = Depends(command_log_dependency),
    ) -> dict:
        record = await command_log.get(command_id)
        if record is None or record.charger_id != charger_id:
            raise HTTPException(status_code=404, detail="command not found")
        return _record_dict(record)

    return router
