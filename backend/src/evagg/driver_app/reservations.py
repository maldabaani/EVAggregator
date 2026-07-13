"""Driver-facing reservations — the app's own "reserve a charger ahead of
time" feature (the standout differentiator in the competitor feature list
this backlog was compared against). Reuses `OcpiCommandService`'s already
-real `ReserveNow`/`CancelReservation` dispatch (built for OCPI roaming
partners in Task 1.2's Commands module) rather than duplicating it,
adding only the driver-ownership check OCPI's own trust model has no
equivalent for — there, a roaming partner *is* the trust boundary (its own
bearer token authorizes commands for its own sessions); here, an
individual driver additionally needs to be restricted to their own
reservation, so another driver can't cancel it.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from evagg.ocpi.commands import OcpiCommandResultStatus, OcpiCommandService


class ReservationError(Exception):
    pass


class ReservationNotFoundError(Exception):
    """Raised for an unknown reservation_id, or one belonging to a
    different driver — deliberately indistinguishable, so probing
    reservation ids can't reveal which ones exist."""


@dataclass(frozen=True)
class Reservation:
    id: str
    charger_id: str
    connector_id: int
    expires_at: datetime


class DriverReservationService:
    def __init__(self, ocpi_command_service: OcpiCommandService) -> None:
        self._ocpi_command_service = ocpi_command_service
        self._owner: dict[str, uuid.UUID] = {}
        self._reservations: dict[str, Reservation] = {}

    async def reserve(
        self,
        charger_id: str,
        connector_id: int,
        expires_at: datetime,
        driver_id: uuid.UUID,
        tenant_id: uuid.UUID,
    ) -> Reservation:
        reservation_id = str(uuid.uuid4())
        id_tag = f"DRIVER:{driver_id}"
        result = await self._ocpi_command_service.reserve_now(
            charger_id, tenant_id, id_tag, expires_at, reservation_id, connector_id
        )
        if result.result != OcpiCommandResultStatus.ACCEPTED:
            raise ReservationError(result.reason or "reservation rejected")

        reservation = Reservation(
            id=reservation_id, charger_id=charger_id, connector_id=connector_id, expires_at=expires_at
        )
        self._owner[reservation_id] = driver_id
        self._reservations[reservation_id] = reservation
        return reservation

    async def list_for_driver(self, driver_id: uuid.UUID) -> list[Reservation]:
        return [r for r in self._reservations.values() if self._owner.get(r.id) == driver_id]

    async def cancel(self, reservation_id: str, driver_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        if self._owner.get(reservation_id) != driver_id:
            raise ReservationNotFoundError(reservation_id)
        reservation = self._reservations.get(reservation_id)
        if reservation is None:
            raise ReservationNotFoundError(reservation_id)

        result = await self._ocpi_command_service.cancel_reservation(
            reservation.charger_id, tenant_id, reservation_id
        )
        if result.result != OcpiCommandResultStatus.ACCEPTED:
            raise ReservationError(result.reason or "cancellation rejected")

        del self._reservations[reservation_id]
        del self._owner[reservation_id]
