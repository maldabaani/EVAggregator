import uuid
from datetime import date, datetime, timezone

import pytest

from evagg.driver_app.session_history import CompletedSession, InMemorySessionHistoryStore

DRIVER_ID = uuid.uuid4()
OTHER_DRIVER_ID = uuid.uuid4()


def _session(charger_id: str, ended_at: datetime, driver_id: uuid.UUID = DRIVER_ID) -> CompletedSession:
    return CompletedSession(
        session_id=str(uuid.uuid4()), driver_id=driver_id, charger_id=charger_id,
        started_at=ended_at, ended_at=ended_at, energy_kwh=5.0, cost_minor_units=500, currency="AED",
    )


@pytest.mark.asyncio
async def test_a_driver_with_no_sessions_has_an_empty_history():
    store = InMemorySessionHistoryStore()

    history = await store.list_for_driver(DRIVER_ID, date.min, date.max)

    assert history == []


@pytest.mark.asyncio
async def test_a_recorded_session_is_returned_within_its_date_range():
    store = InMemorySessionHistoryStore()
    ended_at = datetime(2026, 1, 15, tzinfo=timezone.utc)
    await store.record(_session("CP-1", ended_at))

    history = await store.list_for_driver(DRIVER_ID, date(2026, 1, 1), date(2026, 1, 31))

    assert len(history) == 1
    assert history[0].charger_id == "CP-1"


@pytest.mark.asyncio
async def test_a_session_outside_the_date_range_is_excluded():
    store = InMemorySessionHistoryStore()
    await store.record(_session("CP-1", datetime(2026, 2, 1, tzinfo=timezone.utc)))

    history = await store.list_for_driver(DRIVER_ID, date(2026, 1, 1), date(2026, 1, 31))

    assert history == []


@pytest.mark.asyncio
async def test_another_drivers_sessions_are_not_included():
    store = InMemorySessionHistoryStore()
    ended_at = datetime(2026, 1, 15, tzinfo=timezone.utc)
    await store.record(_session("CP-1", ended_at, driver_id=OTHER_DRIVER_ID))

    history = await store.list_for_driver(DRIVER_ID, date.min, date.max)

    assert history == []
