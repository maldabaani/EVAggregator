from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from evagg.ocpi.charging_preferences import (
    ChargingPreferencesResultStatus,
    ChargingPreferencesService,
    InMemoryChargingPreferencesStore,
)
from evagg.ocpi.charging_profiles import InMemorySessionChargerMap, SessionChargerBinding

TENANT_ID = uuid.uuid4()
SESSION_ID = "SESSION-1"


def _build_service():
    session_map = InMemorySessionChargerMap()
    store = InMemoryChargingPreferencesStore()
    return ChargingPreferencesService(session_map, store), session_map, store


@pytest.mark.asyncio
async def test_unknown_session_is_not_possible():
    service, *_ = _build_service()

    result = await service.set_charging_preferences(SESSION_ID, "FAST")

    assert result == ChargingPreferencesResultStatus.NOT_POSSIBLE


@pytest.mark.asyncio
async def test_unsupported_profile_type_is_rejected():
    service, session_map, _ = _build_service()
    session_map.set_binding(SESSION_ID, SessionChargerBinding("CP-1", TENANT_ID, connector_id=1))

    result = await service.set_charging_preferences(SESSION_ID, "SOLAR_ONLY")

    assert result == ChargingPreferencesResultStatus.PROFILE_TYPE_NOT_SUPPORTED


@pytest.mark.asyncio
async def test_non_fast_profile_without_departure_time_requires_it():
    service, session_map, _ = _build_service()
    session_map.set_binding(SESSION_ID, SessionChargerBinding("CP-1", TENANT_ID, connector_id=1))

    result = await service.set_charging_preferences(SESSION_ID, "REGULAR")

    assert result == ChargingPreferencesResultStatus.DEPARTURE_REQUIRED


@pytest.mark.asyncio
async def test_fast_profile_does_not_require_departure_time():
    service, session_map, store = _build_service()
    session_map.set_binding(SESSION_ID, SessionChargerBinding("CP-1", TENANT_ID, connector_id=1))

    result = await service.set_charging_preferences(SESSION_ID, "FAST")

    assert result == ChargingPreferencesResultStatus.ACCEPTED
    stored = await store.get(SESSION_ID)
    assert stored is not None
    assert stored.profile_type == "FAST"


@pytest.mark.asyncio
async def test_cheap_profile_without_energy_need_requires_it():
    service, session_map, _ = _build_service()
    session_map.set_binding(SESSION_ID, SessionChargerBinding("CP-1", TENANT_ID, connector_id=1))
    departure = datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc)

    result = await service.set_charging_preferences(SESSION_ID, "CHEAP", departure_time=departure)

    assert result == ChargingPreferencesResultStatus.ENERGY_NEED_REQUIRED


@pytest.mark.asyncio
async def test_accepted_preference_is_stored_and_retrievable():
    service, session_map, _ = _build_service()
    session_map.set_binding(SESSION_ID, SessionChargerBinding("CP-1", TENANT_ID, connector_id=1))
    departure = datetime(2026, 7, 12, 18, 0, tzinfo=timezone.utc)

    result = await service.set_charging_preferences(
        SESSION_ID, "CHEAP", departure_time=departure, energy_need_kwh=20.0, discharge_allowed=False
    )

    assert result == ChargingPreferencesResultStatus.ACCEPTED
    stored = await service.get_charging_preferences(SESSION_ID)
    assert stored is not None
    assert stored.energy_need_kwh == 20.0
    assert stored.departure_time == departure
    assert stored.discharge_allowed is False


@pytest.mark.asyncio
async def test_get_charging_preferences_for_session_with_none_set_yet():
    service, session_map, _ = _build_service()
    session_map.set_binding(SESSION_ID, SessionChargerBinding("CP-1", TENANT_ID, connector_id=1))

    assert await service.get_charging_preferences(SESSION_ID) is None
