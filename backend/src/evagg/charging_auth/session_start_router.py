"""POST /charging/session/start/{qr,autocharge,plug-and-charge,app} — the
real HTTP entry point onto `SessionStartService` (Task 5.2): resolves *who*
is starting a session and *how they'll pay*, then actually dispatches the
OCPP `RemoteStartTransaction` command to the charge point (Task 2.3's
outbound command engine) and records the resulting session_id.

Sits behind `evagg.main`'s tenant-header trust boundary — `tenant_id` comes
from the gateway-signed header (via `require_current_tenant`), the same as
every other route here. For the `app` method specifically, the driver
reaches this through `evagg.driver_app.session_start_forwarder`, which
signs that header from the driver's own verified access token.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from evagg.charging_auth.autocharge import AutochargeMacStore
from evagg.charging_auth.plug_and_charge import PlugAndChargeValidator
from evagg.charging_auth.session_start import SessionStartError, SessionStartResult, SessionStartService
from evagg.core.tenancy import require_current_tenant


class QrStartRequest(BaseModel):
    token: str
    driver_id: str
    secret: str


class AutochargeStartRequest(BaseModel):
    mac_address: str
    charger_id: str


class PlugAndChargeStartRequest(BaseModel):
    cert_pem: str
    charger_id: str


class AppStartRequest(BaseModel):
    charger_id: str
    connector_id: int
    driver_id: str


def _result_dict(result: SessionStartResult) -> dict:
    return {
        "session_id": result.session_id,
        "driver_id": str(result.driver_id),
        "charger_id": result.charger_id,
        "connector_id": result.connector_id,
        "id_tag": result.id_tag,
        "auth_method": result.auth_method,
        "payment_method": (
            {"id": str(result.payment_method.id), "type": result.payment_method.type}
            if result.payment_method
            else None
        ),
    }


def build_session_start_router(
    service_dependency,
    mac_store_dependency,
    plug_and_charge_validator_dependency,
) -> APIRouter:
    router = APIRouter(prefix="/charging/session/start", tags=["charging-session"])

    @router.post("/qr")
    async def start_via_qr(
        body: QrStartRequest,
        service: SessionStartService = Depends(service_dependency),
        tenant_id: uuid.UUID = Depends(require_current_tenant),
    ) -> dict:
        try:
            result = await service.start_via_qr(body.token, uuid.UUID(body.driver_id), body.secret, tenant_id)
        except SessionStartError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _result_dict(result)

    @router.post("/autocharge")
    async def start_via_autocharge(
        body: AutochargeStartRequest,
        service: SessionStartService = Depends(service_dependency),
        mac_store: AutochargeMacStore = Depends(mac_store_dependency),
        tenant_id: uuid.UUID = Depends(require_current_tenant),
    ) -> dict:
        try:
            result = await service.start_via_autocharge(body.mac_address, body.charger_id, tenant_id, mac_store)
        except SessionStartError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _result_dict(result)

    @router.post("/plug-and-charge")
    async def start_via_plug_and_charge(
        body: PlugAndChargeStartRequest,
        service: SessionStartService = Depends(service_dependency),
        validator: PlugAndChargeValidator = Depends(plug_and_charge_validator_dependency),
        tenant_id: uuid.UUID = Depends(require_current_tenant),
    ) -> dict:
        try:
            result = await service.start_via_plug_and_charge(body.cert_pem, body.charger_id, tenant_id, validator)
        except SessionStartError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _result_dict(result)

    @router.post("/app")
    async def start_via_app(
        body: AppStartRequest,
        service: SessionStartService = Depends(service_dependency),
        tenant_id: uuid.UUID = Depends(require_current_tenant),
    ) -> dict:
        try:
            result = await service.start_via_app(
                body.charger_id, body.connector_id, uuid.UUID(body.driver_id), tenant_id
            )
        except SessionStartError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _result_dict(result)

    return router
