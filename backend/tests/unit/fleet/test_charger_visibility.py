"""Task 4.3 unit tests — all isolated (in-memory charger/team-access
repositories and membership store)."""

from __future__ import annotations

import uuid

import pytest

from evagg.fleet.charger_visibility import (
    PUBLIC,
    TEAM_ONLY,
    BoundingBox,
    ChargerSummary,
    InMemoryChargerAccessRepository,
    MapChargerQueryService,
)
from evagg.fleet.team_membership import InMemoryMembershipStore, MEMBER

TEAM_ID = uuid.uuid4()
OTHER_TEAM_ID = uuid.uuid4()


def _build_service():
    charger_repo = InMemoryChargerAccessRepository()
    membership_store = InMemoryMembershipStore()
    service = MapChargerQueryService(charger_repo, membership_store)
    return service, charger_repo, membership_store


@pytest.mark.asyncio
async def test_team_only_charger_excluded_from_response_for_non_member():
    service, charger_repo, membership_store = _build_service()
    charger = ChargerSummary(id=uuid.uuid4(), visibility=TEAM_ONLY, latitude=25.2, longitude=55.3)
    charger_repo.add_charger(charger)
    charger_repo.grant_team_access(charger.id, TEAM_ID)
    driver_id = uuid.uuid4()  # not a member of any team

    results = await service.query_visible_chargers(driver_id)

    assert results == []


@pytest.mark.asyncio
async def test_team_only_charger_included_for_authorized_member():
    service, charger_repo, membership_store = _build_service()
    charger = ChargerSummary(id=uuid.uuid4(), visibility=TEAM_ONLY, latitude=25.2, longitude=55.3)
    charger_repo.add_charger(charger)
    charger_repo.grant_team_access(charger.id, TEAM_ID)
    driver_id = uuid.uuid4()
    await membership_store.create(driver_id, TEAM_ID, MEMBER)

    results = await service.query_visible_chargers(driver_id)

    assert results == [charger]


@pytest.mark.asyncio
async def test_team_only_charger_excluded_for_member_of_a_different_team():
    service, charger_repo, membership_store = _build_service()
    charger = ChargerSummary(id=uuid.uuid4(), visibility=TEAM_ONLY, latitude=25.2, longitude=55.3)
    charger_repo.add_charger(charger)
    charger_repo.grant_team_access(charger.id, TEAM_ID)
    driver_id = uuid.uuid4()
    await membership_store.create(driver_id, OTHER_TEAM_ID, MEMBER)  # wrong team

    results = await service.query_visible_chargers(driver_id)

    assert results == []


@pytest.mark.asyncio
async def test_public_charger_visible_to_all():
    service, charger_repo, membership_store = _build_service()
    public_charger = ChargerSummary(id=uuid.uuid4(), visibility=PUBLIC, latitude=25.2, longitude=55.3)
    charger_repo.add_charger(public_charger)
    driver_with_no_teams = uuid.uuid4()

    results = await service.query_visible_chargers(driver_with_no_teams)

    assert results == [public_charger]


@pytest.mark.asyncio
async def test_public_and_team_only_chargers_both_appear_for_authorized_member():
    service, charger_repo, membership_store = _build_service()
    public_charger = ChargerSummary(id=uuid.uuid4(), visibility=PUBLIC, latitude=25.2, longitude=55.3)
    team_charger = ChargerSummary(id=uuid.uuid4(), visibility=TEAM_ONLY, latitude=25.2, longitude=55.3)
    charger_repo.add_charger(public_charger)
    charger_repo.add_charger(team_charger)
    charger_repo.grant_team_access(team_charger.id, TEAM_ID)
    driver_id = uuid.uuid4()
    await membership_store.create(driver_id, TEAM_ID, MEMBER)

    results = await service.query_visible_chargers(driver_id)

    assert set(r.id for r in results) == {public_charger.id, team_charger.id}


@pytest.mark.asyncio
async def test_map_query_respects_bbox_and_visibility_together():
    service, charger_repo, membership_store = _build_service()
    in_bbox_public = ChargerSummary(id=uuid.uuid4(), visibility=PUBLIC, latitude=25.0, longitude=55.0)
    out_of_bbox_public = ChargerSummary(id=uuid.uuid4(), visibility=PUBLIC, latitude=40.0, longitude=90.0)
    in_bbox_team_only_unauthorized = ChargerSummary(id=uuid.uuid4(), visibility=TEAM_ONLY, latitude=25.0, longitude=55.0)
    charger_repo.add_charger(in_bbox_public)
    charger_repo.add_charger(out_of_bbox_public)
    charger_repo.add_charger(in_bbox_team_only_unauthorized)
    charger_repo.grant_team_access(in_bbox_team_only_unauthorized.id, TEAM_ID)
    driver_id = uuid.uuid4()  # not a member of TEAM_ID

    bbox = BoundingBox(min_lat=24.0, min_lng=54.0, max_lat=26.0, max_lng=56.0)
    results = await service.query_visible_chargers(driver_id, bbox=bbox)

    # out_of_bbox_public excluded by bbox; in_bbox_team_only excluded by visibility;
    # only in_bbox_public satisfies both filters.
    assert results == [in_bbox_public]
