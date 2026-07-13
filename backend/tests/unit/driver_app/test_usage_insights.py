import uuid
from datetime import date, datetime, timezone

import pytest

from evagg.driver_app.session_history import CompletedSession, InMemorySessionHistoryStore
from evagg.driver_app.usage_insights import UsageInsightsService
from evagg.ocpi.domain import OCPIGeoLocation, OCPILocation
from evagg.ocpi.locations import InMemoryLocationRepository

DRIVER_ID = uuid.uuid4()


def _location(loc_id: str, name: str) -> OCPILocation:
    return OCPILocation(
        id=loc_id, party_id="ABC", country_code="AE", publish=True, name=name, address="1 Main St",
        city="Dubai", country="ARE", coordinates=OCPIGeoLocation(latitude="25.2", longitude="55.3"),
        last_updated=datetime.now(timezone.utc), evse_status="AVAILABLE",
    )


def _session(charger_id: str, ended_at: datetime, energy_kwh: float, cost_minor_units: int) -> CompletedSession:
    return CompletedSession(
        session_id=str(uuid.uuid4()), driver_id=DRIVER_ID, charger_id=charger_id,
        started_at=ended_at, ended_at=ended_at, energy_kwh=energy_kwh,
        cost_minor_units=cost_minor_units, currency="AED",
    )


@pytest.mark.asyncio
async def test_an_empty_period_returns_no_points():
    service = UsageInsightsService(InMemorySessionHistoryStore(), InMemoryLocationRepository())

    points = await service.get_daily_usage(DRIVER_ID, date(2026, 1, 1), date(2026, 1, 31))

    assert points == []


@pytest.mark.asyncio
async def test_sessions_on_the_same_day_are_grouped_into_one_point():
    history = InMemorySessionHistoryStore()
    day = datetime(2026, 1, 10, 9, tzinfo=timezone.utc)
    await history.record(_session("CP-1", day, 5.0, 500))
    await history.record(_session("CP-1", day.replace(hour=14), 3.0, 300))
    service = UsageInsightsService(history, InMemoryLocationRepository())

    points = await service.get_daily_usage(DRIVER_ID, date(2026, 1, 1), date(2026, 1, 31))

    assert len(points) == 1
    assert points[0].usage_date == date(2026, 1, 10)
    assert points[0].session_count == 2
    assert points[0].kwh_total == 8.0
    assert points[0].cost_total_minor_units == 800


@pytest.mark.asyncio
async def test_sessions_on_different_days_produce_separate_points_in_date_order():
    history = InMemorySessionHistoryStore()
    await history.record(_session("CP-1", datetime(2026, 1, 20, tzinfo=timezone.utc), 1.0, 100))
    await history.record(_session("CP-1", datetime(2026, 1, 5, tzinfo=timezone.utc), 2.0, 200))
    service = UsageInsightsService(history, InMemoryLocationRepository())

    points = await service.get_daily_usage(DRIVER_ID, date(2026, 1, 1), date(2026, 1, 31))

    assert [p.usage_date for p in points] == [date(2026, 1, 5), date(2026, 1, 20)]


@pytest.mark.asyncio
async def test_top_site_resolves_the_chargers_published_location_name():
    history = InMemorySessionHistoryStore()
    day = datetime(2026, 1, 10, tzinfo=timezone.utc)
    await history.record(_session("CP-1", day, 10.0, 1000))
    locations = InMemoryLocationRepository()
    locations.add(_location("CP-1", "Downtown Mall"))
    service = UsageInsightsService(history, locations)

    points = await service.get_daily_usage(DRIVER_ID, date(2026, 1, 1), date(2026, 1, 31))

    assert points[0].top_site_name == "Downtown Mall"


@pytest.mark.asyncio
async def test_top_site_is_the_charger_with_the_most_energy_that_day():
    history = InMemorySessionHistoryStore()
    day = datetime(2026, 1, 10, tzinfo=timezone.utc)
    await history.record(_session("CP-1", day, 2.0, 200))
    await history.record(_session("CP-2", day.replace(hour=15), 9.0, 900))
    locations = InMemoryLocationRepository()
    locations.add(_location("CP-1", "Small Stop"))
    locations.add(_location("CP-2", "Big Hub"))
    service = UsageInsightsService(history, locations)

    points = await service.get_daily_usage(DRIVER_ID, date(2026, 1, 1), date(2026, 1, 31))

    assert points[0].top_site_name == "Big Hub"


@pytest.mark.asyncio
async def test_top_site_falls_back_to_the_charger_id_when_unpublished():
    history = InMemorySessionHistoryStore()
    await history.record(_session("CP-1", datetime(2026, 1, 10, tzinfo=timezone.utc), 1.0, 100))
    service = UsageInsightsService(history, InMemoryLocationRepository())

    points = await service.get_daily_usage(DRIVER_ID, date(2026, 1, 1), date(2026, 1, 31))

    assert points[0].top_site_name == "CP-1"
