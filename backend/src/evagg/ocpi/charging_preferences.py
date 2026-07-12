"""OCPI Charging Preferences module (2.2.1+ only, same as ChargingProfiles
and Commands — the module doesn't exist in 2.1.1). A driver states how
they want an active session charged — by a departure time, an energy
target, or just "as fast as possible" — via `PUT /ocpi/{version}/sessions/
{session_id}/charging_preferences`.

Unlike ChargingProfiles/Commands, this one isn't bridged onto an OCPP
remote command: turning "I need 20kWh by 6pm" into an actual charging
schedule is a smart-charging optimization problem (balancing site
capacity, tariffs, grid signals) this platform doesn't have yet — building
that optimizer is its own project, not a natural extension of the command
engine the way SetChargingProfile/RemoteStart were. This module is
therefore the honest scope: record the driver's stated preference and
validate it against the real OCPI result enum, so a future optimizer has
something to read. `session_id` resolution reuses the same
`SessionChargerMap` as ChargingProfiles/Commands (Task 45/46) rather than
introducing a third mapping.

Direction, simplified and documented: the real spec has the *CPO* push
preferences collected on-site (e.g. a charge point's own PIN pad) to the
eMSP. Everything else this platform exposes under `/ocpi/{version}/...`
is the opposite direction — a partner calling *into* this CPO (Locations/
Tariffs GET, ChargingProfiles/Commands PUT-or-POST) — and a bare PIN-pad
flow doesn't fit a mostly app-driven aggregator. This module follows that
same established inbound-receiver shape instead: a partner PUTs a
preference for one of their driver's active roaming sessions here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol

from evagg.ocpi.charging_profiles import SessionChargerMap

PROFILE_TYPES = frozenset({"CHEAP", "FAST", "GREEN", "REGULAR"})


class ChargingPreferencesResultStatus(str, Enum):
    ACCEPTED = "ACCEPTED"
    DEPARTURE_REQUIRED = "DEPARTURE_REQUIRED"
    ENERGY_NEED_REQUIRED = "ENERGY_NEED_REQUIRED"
    NOT_POSSIBLE = "NOT_POSSIBLE"
    PROFILE_TYPE_NOT_SUPPORTED = "PROFILE_TYPE_NOT_SUPPORTED"


@dataclass
class ChargingPreferences:
    session_id: str
    profile_type: str
    departure_time: datetime | None = None
    energy_need_kwh: float | None = None
    discharge_allowed: bool | None = None


class ChargingPreferencesStore(Protocol):
    async def get(self, session_id: str) -> ChargingPreferences | None: ...

    async def set(self, session_id: str, preferences: ChargingPreferences) -> None: ...


@dataclass
class InMemoryChargingPreferencesStore:
    preferences: dict[str, ChargingPreferences] = field(default_factory=dict)

    async def get(self, session_id: str) -> ChargingPreferences | None:
        return self.preferences.get(session_id)

    async def set(self, session_id: str, preferences: ChargingPreferences) -> None:
        self.preferences[session_id] = preferences


class ChargingPreferencesService:
    def __init__(self, session_charger_map: SessionChargerMap, store: ChargingPreferencesStore) -> None:
        self._session_charger_map = session_charger_map
        self._store = store

    async def set_charging_preferences(
        self,
        session_id: str,
        profile_type: str,
        departure_time: datetime | None = None,
        energy_need_kwh: float | None = None,
        discharge_allowed: bool | None = None,
    ) -> ChargingPreferencesResultStatus:
        binding = await self._session_charger_map.get_charger_for_session(session_id)
        if binding is None:
            # The real ChargingPreferencesResponse.result enum has no
            # "unknown session" value — NOT_POSSIBLE is the closest honest
            # fit for "there's nothing here to apply a preference to".
            return ChargingPreferencesResultStatus.NOT_POSSIBLE

        if profile_type not in PROFILE_TYPES:
            return ChargingPreferencesResultStatus.PROFILE_TYPE_NOT_SUPPORTED

        # FAST means "charge at maximum rate regardless of when I leave" —
        # every other profile type needs a departure time to plan against.
        if profile_type != "FAST" and departure_time is None:
            return ChargingPreferencesResultStatus.DEPARTURE_REQUIRED

        if profile_type == "CHEAP" and energy_need_kwh is None:
            # Without a target, "cheap" has no window to optimize over —
            # it would just mean "never charge," which isn't a preference.
            return ChargingPreferencesResultStatus.ENERGY_NEED_REQUIRED

        await self._store.set(
            session_id,
            ChargingPreferences(
                session_id=session_id,
                profile_type=profile_type,
                departure_time=departure_time,
                energy_need_kwh=energy_need_kwh,
                discharge_allowed=discharge_allowed,
            ),
        )
        return ChargingPreferencesResultStatus.ACCEPTED

    async def get_charging_preferences(self, session_id: str) -> ChargingPreferences | None:
        return await self._store.get(session_id)
