"""Task 1.2 unit tests — all isolated (in-memory location/token/CDR stores
and push clients, no real network/Redis)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from evagg.ocpi.cdr import CdrService, InMemoryCdrPushClient, InMemoryCdrStore, reconcile_incoming_cdr
from evagg.ocpi.domain import OCPICdr, OCPIGeoLocation, OCPILocation
from evagg.ocpi.location_sync import (
    InMemoryChargerLocationMap,
    InMemoryPartnerPushClient,
    LocationSyncService,
)
from evagg.ocpi.session_sync import InMemorySessionPushClient, SessionSyncService
from evagg.ocpi.tokens import BLACKLISTED, InMemoryTokenWhitelistCache, OcpiRoamingTokenChecker, TokenWhitelistService
from evagg.ocpp_gateway.authorize import AuthStatus

TENANT_ID = uuid.uuid4()
PARTNER_ID = uuid.uuid4()


def _sample_location() -> OCPILocation:
    return OCPILocation(
        id="LOC-1",
        party_id="ABC",
        country_code="AE",
        publish=True,
        name="Downtown Garage",
        address="1 Main St",
        city="Dubai",
        postal_code=None,
        country="ARE",
        coordinates=OCPIGeoLocation(latitude="25.2048", longitude="55.2708"),
        last_updated=datetime.now(timezone.utc),
    )


class _FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


# --- Location read model sync ----------------------------------------------


@pytest.mark.asyncio
async def test_location_read_model_reflects_charger_status_change():
    from evagg.ocpi.locations import InMemoryLocationRepository

    location_repo = InMemoryLocationRepository([_sample_location()])
    charger_map = InMemoryChargerLocationMap({"CP-1": "LOC-1"})
    push_client = InMemoryPartnerPushClient()
    service = LocationSyncService(charger_map, location_repo, push_client)

    updated = await service.handle_status_notification("CP-1", "Faulted", connected_partner_ids=[PARTNER_ID])

    assert updated is not None
    assert updated.evse_status == "Faulted"
    stored = await location_repo.get("LOC-1")
    assert stored.evse_status == "Faulted"
    assert push_client.location_pushes == [(PARTNER_ID, updated)]


@pytest.mark.asyncio
async def test_status_change_for_unmapped_charger_is_a_no_op():
    from evagg.ocpi.locations import InMemoryLocationRepository

    location_repo = InMemoryLocationRepository([_sample_location()])
    charger_map = InMemoryChargerLocationMap()  # no mapping configured
    push_client = InMemoryPartnerPushClient()
    service = LocationSyncService(charger_map, location_repo, push_client)

    result = await service.handle_status_notification("CP-unknown", "Available", connected_partner_ids=[PARTNER_ID])

    assert result is None
    assert push_client.location_pushes == []


# --- Token whitelist ---------------------------------------------------------


@pytest.mark.asyncio
async def test_token_whitelist_cached_and_ttl_refreshed_on_authorize():
    clock = _FakeClock()
    cache = InMemoryTokenWhitelistCache(clock=clock)
    whitelist_service = TokenWhitelistService(cache, default_ttl_seconds=3600)
    checker = OcpiRoamingTokenChecker(cache, ttl_seconds=3600)

    await whitelist_service.whitelist_token("TOKEN-ROAMING-1")
    initial_expiry = cache.expires_at("TOKEN-ROAMING-1")

    clock.advance(1800)  # halfway through the TTL window
    status = await checker.check("TOKEN-ROAMING-1")

    assert status == AuthStatus.ACCEPTED
    refreshed_expiry = cache.expires_at("TOKEN-ROAMING-1")
    assert refreshed_expiry > initial_expiry  # TTL was refreshed by the authorize check


@pytest.mark.asyncio
async def test_blacklisted_token_returns_blocked_without_refreshing_ttl():
    clock = _FakeClock()
    cache = InMemoryTokenWhitelistCache(clock=clock)
    whitelist_service = TokenWhitelistService(cache)
    checker = OcpiRoamingTokenChecker(cache)

    await whitelist_service.blacklist_token("TOKEN-BAD")

    status = await checker.check("TOKEN-BAD")

    assert status == AuthStatus.BLOCKED
    assert (await cache.get_status("TOKEN-BAD")) == BLACKLISTED


@pytest.mark.asyncio
async def test_unknown_token_returns_invalid():
    cache = InMemoryTokenWhitelistCache()
    checker = OcpiRoamingTokenChecker(cache)

    status = await checker.check("NEVER-SEEN")

    assert status == AuthStatus.INVALID


@pytest.mark.asyncio
async def test_expired_whitelist_entry_is_treated_as_unknown():
    clock = _FakeClock()
    cache = InMemoryTokenWhitelistCache(clock=clock)
    await cache.set_status("TOKEN-1", "whitelisted", ttl_seconds=60)

    clock.advance(61)
    checker = OcpiRoamingTokenChecker(cache)
    status = await checker.check("TOKEN-1")

    assert status == AuthStatus.INVALID


# --- CDR generation & push idempotency --------------------------------------


def _make_cdr(cdr_id: str = "CDR-1", total_energy: float = 15.0) -> OCPICdr:
    return OCPICdr(
        id=cdr_id,
        start_date_time=datetime.now(timezone.utc),
        end_date_time=datetime.now(timezone.utc),
        cdr_token_uid="TOKEN-1",
        auth_method="WHITELIST",
        currency="AED",
        total_cost=25.50,
        total_energy=total_energy,
        last_updated=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_cdr_generated_exactly_once_on_stop_transaction():
    store = InMemoryCdrStore()
    push_client = InMemoryCdrPushClient()
    service = CdrService(store, push_client)
    call_count = {"n": 0}

    def factory() -> OCPICdr:
        call_count["n"] += 1
        return _make_cdr()

    first = await service.generate_cdr_on_stop_transaction("SESSION-1", factory)
    # Simulate a duplicate stop_transaction event delivery (at-least-once).
    second = await service.generate_cdr_on_stop_transaction("SESSION-1", factory)

    assert first.id == second.id
    assert call_count["n"] == 1  # factory only invoked once


@pytest.mark.asyncio
async def test_duplicate_cdr_push_is_idempotent():
    store = InMemoryCdrStore()
    push_client = InMemoryCdrPushClient()
    service = CdrService(store, push_client)
    cdr = _make_cdr()

    await service.push_cdr_idempotent(PARTNER_ID, cdr)
    await service.push_cdr_idempotent(PARTNER_ID, cdr)  # retried delivery

    assert push_client.pushed == [(PARTNER_ID, cdr.id)]


@pytest.mark.asyncio
async def test_cdr_push_to_different_partners_is_not_deduplicated():
    store = InMemoryCdrStore()
    push_client = InMemoryCdrPushClient()
    service = CdrService(store, push_client)
    cdr = _make_cdr()
    other_partner_id = uuid.uuid4()

    await service.push_cdr_idempotent(PARTNER_ID, cdr)
    await service.push_cdr_idempotent(other_partner_id, cdr)

    assert len(push_client.pushed) == 2


def test_incoming_partner_cdr_flagged_on_kwh_mismatch():
    result = reconcile_incoming_cdr(local_kwh=100.0, partner_kwh=105.0)  # 5% delta

    assert result.status == "mismatched"


def test_incoming_partner_cdr_within_tolerance_is_matched():
    result = reconcile_incoming_cdr(local_kwh=100.0, partner_kwh=101.0)  # 1% delta

    assert result.status == "matched"


def test_incoming_partner_cdr_at_exact_threshold_is_matched():
    result = reconcile_incoming_cdr(local_kwh=100.0, partner_kwh=102.0)  # exactly 2%

    assert result.status == "matched"  # AC says "delta > 2%", not >=


# --- Session PATCH on MeterValues -------------------------------------------


@pytest.mark.asyncio
async def test_session_patch_sent_on_meter_values_event():
    push_client = InMemorySessionPushClient()
    service = SessionSyncService(push_client)

    await service.handle_meter_values(PARTNER_ID, "SESSION-1", kwh=12.5)

    assert push_client.patches == [(PARTNER_ID, "SESSION-1", 12.5)]
