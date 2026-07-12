"""OCPI Commands module (2.2.1+ only, same as ChargingProfiles — the module
doesn't exist in 2.1.1). A roaming partner's driver app asks the CPO to
remotely control a charge point on their behalf: START_SESSION,
STOP_SESSION, RESERVE_NOW, UNLOCK_CONNECTOR, CANCEL_RESERVATION. Each
bridges straight onto `RemoteCommandService` (Task 2.3) — the same engine
`command_router.py` (Task 42) exposes to the portal — rather than adding a
second command pathway.

Same documented simplification as `charging_profiles.py`: dispatch is
synchronous and the real outcome is returned inline, since there's no
`response_url` push-callback infrastructure for this module either.
`location_id` is treated as the charger_id directly, reusing
`OCPILocation`'s own documented "single-EVSE-per-location" simplification
(domain.py) rather than inventing a separate EVSE-uid index.

STOP_SESSION only carries a `session_id` in the real spec — no charger
reference — so it resolves session_id -> charger via `SessionChargerMap`
(same map ChargingProfiles uses), then looks up that charger's *current*
active transaction via `TransactionRepository` to get the real OCPP
transaction_id `RemoteStopTransaction` needs. That's deliberately not the
`session_id` START_SESSION mints here: this session_id is a roaming-side
identifier assigned before the charge point has even accepted the start
request, while OCPP's own transaction_id is assigned later, from the
charger's own `StartTransaction.req` — the two are never the same value.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from evagg.ocpi.charging_profiles import InMemorySessionChargerMap, SessionChargerBinding
from evagg.ocpp_gateway.commands import ChargerOfflineError, CommandStatus, RemoteCommandService
from evagg.ocpp_gateway.transactions import TransactionRepository


class OcpiCommandResultStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN_SESSION = "UNKNOWN_SESSION"


@dataclass
class OcpiCommandResult:
    result: OcpiCommandResultStatus
    session_id: str | None = None
    reason: str | None = None


class OcpiCommandService:
    def __init__(
        self,
        session_charger_map: InMemorySessionChargerMap,
        transaction_repository: TransactionRepository,
        command_service: RemoteCommandService,
    ) -> None:
        self._session_charger_map = session_charger_map
        self._transaction_repository = transaction_repository
        self._command_service = command_service

    async def start_session(
        self, location_id: str, tenant_id: uuid.UUID, token_uid: str, connector_id: int = 1
    ) -> OcpiCommandResult:
        charger_id = location_id
        try:
            result = await self._command_service.send_command(
                charger_id, tenant_id, "RemoteStartTransaction", {"idTag": token_uid, "connectorId": connector_id}
            )
        except ChargerOfflineError as exc:
            return OcpiCommandResult(OcpiCommandResultStatus.REJECTED, reason=str(exc))

        if result.status != CommandStatus.ACCEPTED:
            return OcpiCommandResult(
                OcpiCommandResultStatus.REJECTED, reason=f"charge point responded {result.status.value}"
            )

        session_id = str(uuid.uuid4())
        self._session_charger_map.set_binding(
            session_id, SessionChargerBinding(charger_id, tenant_id, connector_id)
        )
        return OcpiCommandResult(OcpiCommandResultStatus.ACCEPTED, session_id=session_id)

    async def stop_session(self, session_id: str, tenant_id: uuid.UUID) -> OcpiCommandResult:
        binding = await self._session_charger_map.get_charger_for_session(session_id)
        if binding is None:
            return OcpiCommandResult(OcpiCommandResultStatus.UNKNOWN_SESSION)

        active_transaction = await self._transaction_repository.get_active_transaction(binding.charger_id)
        if active_transaction is None:
            return OcpiCommandResult(
                OcpiCommandResultStatus.REJECTED, session_id=session_id,
                reason="no active transaction on this charger",
            )

        try:
            result = await self._command_service.send_command(
                binding.charger_id, tenant_id, "RemoteStopTransaction",
                {"transactionId": str(active_transaction.id)},
            )
        except ChargerOfflineError as exc:
            return OcpiCommandResult(OcpiCommandResultStatus.REJECTED, session_id=session_id, reason=str(exc))

        status = (
            OcpiCommandResultStatus.ACCEPTED
            if result.status == CommandStatus.ACCEPTED
            else OcpiCommandResultStatus.REJECTED
        )
        return OcpiCommandResult(status, session_id=session_id)

    async def reserve_now(
        self,
        location_id: str,
        tenant_id: uuid.UUID,
        token_uid: str,
        expiry_date: datetime,
        reservation_id: str,
        connector_id: int = 1,
    ) -> OcpiCommandResult:
        return await self._dispatch(
            location_id,
            tenant_id,
            "ReserveNow",
            {
                "connectorId": connector_id,
                "expiryDate": expiry_date.isoformat(),
                "idTag": token_uid,
                "reservationId": reservation_id,
            },
        )

    async def unlock_connector(
        self, location_id: str, tenant_id: uuid.UUID, connector_id: int = 1
    ) -> OcpiCommandResult:
        return await self._dispatch(location_id, tenant_id, "UnlockConnector", {"connectorId": connector_id})

    async def cancel_reservation(
        self, location_id: str, tenant_id: uuid.UUID, reservation_id: str
    ) -> OcpiCommandResult:
        return await self._dispatch(
            location_id, tenant_id, "CancelReservation", {"reservationId": reservation_id}
        )

    async def _dispatch(
        self, charger_id: str, tenant_id: uuid.UUID, command_type: str, payload: dict
    ) -> OcpiCommandResult:
        try:
            result = await self._command_service.send_command(charger_id, tenant_id, command_type, payload)
        except ChargerOfflineError as exc:
            return OcpiCommandResult(OcpiCommandResultStatus.REJECTED, reason=str(exc))
        status = (
            OcpiCommandResultStatus.ACCEPTED
            if result.status == CommandStatus.ACCEPTED
            else OcpiCommandResultStatus.REJECTED
        )
        return OcpiCommandResult(status)
