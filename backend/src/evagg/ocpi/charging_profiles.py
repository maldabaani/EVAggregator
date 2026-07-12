"""OCPI ChargingProfiles module (2.2.1+ only — the module doesn't exist in
2.1.1, consistent with `versions.py`'s note that 2.1.1 is Locations+Tariffs
GET only). A roaming partner's driver app calls `PUT .../chargingprofiles/
{session_id}` to request smart charging on an active session; this bridges
that straight onto the existing OCPP `SetChargingProfile` remote command
(Task 2.3) rather than adding a second command pathway.

Two simplifications, both documented rather than hidden:

- The real spec is async — CPO acks immediately, then pushes the actual
  result later to the eMSP's `response_url`. There's no push-callback
  infrastructure for this module yet (unlike Locations'/Sessions'
  `PartnerPushClient`/`SessionPushClient`), so this dispatches to the
  charge point synchronously and returns the real outcome inline. A
  `response_url` in the request is accepted but never called.
- `charging_rate_unit` must be `W` (watts) — the internal command engine's
  capacity check (`ConnectorCapacityProvider`) already speaks watts
  (Task 2.3), and OCPP 1.6's own `chargingSchedule.chargingRateUnit` is
  the same enum. Amp-based (`A`) profiles are rejected rather than
  silently guessed at without a voltage to convert with.

`SessionChargerMap` has the same "constructed, not yet wired to live event
consumption" gap as `location_sync.py`'s `ChargerLocationMap`: nothing
today pushes a session_id -> charger/connector binding into it
automatically when a transaction starts, even though `start_transaction`
already mints a transaction_id that could serve as the session_id. Until
that live wiring exists, `admin_router.py`'s `POST /admin/ocpi/sessions/
{session_id}/binding` is the way a binding gets in.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol

from evagg.ocpp_gateway.commands import (
    ChargerOfflineError,
    ChargingProfileExceedsCapacityError,
    CommandStatus,
    ConnectorCapacityProvider,
    RemoteCommandService,
)


@dataclass
class SessionChargerBinding:
    charger_id: str
    tenant_id: uuid.UUID
    connector_id: int


class SessionChargerMap(Protocol):
    """Resolves an OCPI session (an in-progress OCPP transaction, from the
    roaming partner's point of view) back to which charger/connector it's
    actually running on — there's no reverse transaction_id -> charger_id
    index anywhere yet (Task 2.1's `TransactionRepository` only looks up
    the other way, by charger_id), so this is its own small map rather than
    a repurposed one."""

    async def get_charger_for_session(self, session_id: str) -> SessionChargerBinding | None: ...


class InMemorySessionChargerMap:
    def __init__(self, bindings: dict[str, SessionChargerBinding] | None = None) -> None:
        self._bindings: dict[str, SessionChargerBinding] = dict(bindings or {})

    def set_binding(self, session_id: str, binding: SessionChargerBinding) -> None:
        self._bindings[session_id] = binding

    async def get_charger_for_session(self, session_id: str) -> SessionChargerBinding | None:
        return self._bindings.get(session_id)


@dataclass
class ChargingProfilePeriod:
    start_period: int  # seconds from the start of the schedule
    limit: float  # watts


@dataclass
class ActiveChargingProfile:
    session_id: str
    charging_rate_unit: str
    periods: list[ChargingProfilePeriod]
    duration: int | None = None
    min_charging_rate: float | None = None
    start_date_time: datetime | None = None


class ActiveChargingProfileStore(Protocol):
    async def get(self, session_id: str) -> ActiveChargingProfile | None: ...

    async def set(self, session_id: str, profile: ActiveChargingProfile) -> None: ...


@dataclass
class InMemoryActiveChargingProfileStore:
    profiles: dict[str, ActiveChargingProfile] = field(default_factory=dict)

    async def get(self, session_id: str) -> ActiveChargingProfile | None:
        return self.profiles.get(session_id)

    async def set(self, session_id: str, profile: ActiveChargingProfile) -> None:
        self.profiles[session_id] = profile


class ChargingProfileResultStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN_SESSION = "UNKNOWN_SESSION"


@dataclass
class ChargingProfileResult:
    result: ChargingProfileResultStatus
    reason: str | None = None


def _to_ocpp_set_charging_profile_payload(
    connector_id: int,
    charging_rate_unit: str,
    periods: list[ChargingProfilePeriod],
    duration: int | None,
    min_charging_rate: float | None,
) -> dict:
    return {
        "connectorId": connector_id,
        "csChargingProfile": {
            "chargingProfileId": 1,
            "stackLevel": 0,
            "chargingProfilePurpose": "TxProfile",
            "chargingProfileKind": "Relative",
            "chargingSchedule": {
                "chargingRateUnit": charging_rate_unit,
                "duration": duration,
                "minChargingRate": min_charging_rate,
                "chargingSchedulePeriod": [
                    {"startPeriod": p.start_period, "limit": p.limit} for p in periods
                ],
            },
        },
    }


class ChargingProfileService:
    def __init__(
        self,
        session_charger_map: SessionChargerMap,
        active_profile_store: ActiveChargingProfileStore,
        command_service: RemoteCommandService,
        capacity_provider: ConnectorCapacityProvider,
    ) -> None:
        self._session_charger_map = session_charger_map
        self._active_profile_store = active_profile_store
        self._command_service = command_service
        self._capacity_provider = capacity_provider

    async def set_charging_profile(
        self,
        session_id: str,
        charging_rate_unit: str,
        periods: list[ChargingProfilePeriod],
        duration: int | None = None,
        min_charging_rate: float | None = None,
        start_date_time: datetime | None = None,
    ) -> ChargingProfileResult:
        binding = await self._session_charger_map.get_charger_for_session(session_id)
        if binding is None:
            return ChargingProfileResult(ChargingProfileResultStatus.UNKNOWN_SESSION)

        if charging_rate_unit != "W":
            return ChargingProfileResult(
                ChargingProfileResultStatus.REJECTED, "only charging_rate_unit=W is supported"
            )

        requested_watts = int(max((p.limit for p in periods), default=0))
        ocpp_payload = _to_ocpp_set_charging_profile_payload(
            binding.connector_id, charging_rate_unit, periods, duration, min_charging_rate
        )

        try:
            result = await self._command_service.send_set_charging_profile(
                binding.charger_id,
                binding.tenant_id,
                binding.connector_id,
                requested_watts,
                self._capacity_provider,
                ocpp_payload,
            )
        except ChargingProfileExceedsCapacityError as exc:
            return ChargingProfileResult(ChargingProfileResultStatus.REJECTED, str(exc))
        except ChargerOfflineError as exc:
            return ChargingProfileResult(ChargingProfileResultStatus.REJECTED, str(exc))

        if result.status != CommandStatus.ACCEPTED:
            return ChargingProfileResult(
                ChargingProfileResultStatus.REJECTED, f"charge point responded {result.status.value}"
            )

        await self._active_profile_store.set(
            session_id,
            ActiveChargingProfile(
                session_id=session_id,
                charging_rate_unit=charging_rate_unit,
                periods=periods,
                duration=duration,
                min_charging_rate=min_charging_rate,
                start_date_time=start_date_time,
            ),
        )
        return ChargingProfileResult(ChargingProfileResultStatus.ACCEPTED)

    async def get_active_profile(
        self, session_id: str
    ) -> tuple[ChargingProfileResultStatus, ActiveChargingProfile | None]:
        binding = await self._session_charger_map.get_charger_for_session(session_id)
        if binding is None:
            return ChargingProfileResultStatus.UNKNOWN_SESSION, None
        profile = await self._active_profile_store.get(session_id)
        return ChargingProfileResultStatus.ACCEPTED, profile
