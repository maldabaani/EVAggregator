"""POST/GET/DELETE /driver/reservations — the driver-facing reservation
API. Mounted directly on `evagg.edge_app`, no forwarder needed: unlike
`SessionStartService` (which reads `tenant_id` from
`evagg.main`'s `require_current_tenant`, tied to `TenantContextMiddleware`),
`DriverReservationService`/`OcpiCommandService` take `tenant_id` as a
plain argument, so it can come directly from the driver's verified JWT
(`require_driver_identity`) with no extra network hop.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from evagg.driver_app.reservations import DriverReservationService, Reservation, ReservationError, ReservationNotFoundError
from evagg.identity.driver_session import DriverIdentity, require_driver_identity


class CreateReservationRequest(BaseModel):
    charger_id: str
    connector_id: int = 1
    expires_at: datetime


def _reservation_dict(reservation: Reservation) -> dict:
    return {
        "id": reservation.id,
        "charger_id": reservation.charger_id,
        "connector_id": reservation.connector_id,
        "expires_at": reservation.expires_at.isoformat(),
    }


def build_reservation_router(service_dependency) -> APIRouter:
    router = APIRouter(prefix="/driver/reservations", tags=["driver-reservations"])

    @router.get("")
    async def list_reservations(
        identity: DriverIdentity = Depends(require_driver_identity),
        service: DriverReservationService = Depends(service_dependency),
    ) -> dict:
        reservations = await service.list_for_driver(identity.driver_id)
        return {"data": [_reservation_dict(r) for r in reservations]}

    @router.post("")
    async def create_reservation(
        body: CreateReservationRequest,
        identity: DriverIdentity = Depends(require_driver_identity),
        service: DriverReservationService = Depends(service_dependency),
    ) -> dict:
        try:
            reservation = await service.reserve(
                body.charger_id, body.connector_id, body.expires_at, identity.driver_id, identity.tenant_id
            )
        except ReservationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return _reservation_dict(reservation)

    @router.delete("/{reservation_id}")
    async def cancel_reservation(
        reservation_id: str,
        identity: DriverIdentity = Depends(require_driver_identity),
        service: DriverReservationService = Depends(service_dependency),
    ) -> Response:
        try:
            await service.cancel(reservation_id, identity.driver_id, identity.tenant_id)
        except ReservationNotFoundError as exc:
            raise HTTPException(status_code=404, detail="reservation not found") from exc
        except ReservationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return Response(status_code=204)

    return router
