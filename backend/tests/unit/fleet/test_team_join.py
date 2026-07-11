"""Task 4.2 unit tests — all isolated (in-memory invite/membership stores,
in-memory rate limiter). The concurrency test genuinely runs two redemption
attempts in parallel via asyncio.gather rather than simulating the race."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from evagg.fleet.team_invites import InMemoryTeamInviteStore, TeamInvite
from evagg.fleet.team_join import InviteRedemptionError, TeamJoinService
from evagg.fleet.team_membership import ADMIN, InMemoryMembershipStore, MEMBER
from evagg.gateway.rate_limit import InMemoryRateLimiter

TEAM_ID = uuid.uuid4()
NOW = datetime(2026, 6, 1, tzinfo=timezone.utc)


def _build_service(max_attempts: int = 5):
    invite_store = InMemoryTeamInviteStore()
    membership_store = InMemoryMembershipStore()
    rate_limiter = InMemoryRateLimiter()
    service = TeamJoinService(invite_store, membership_store, rate_limiter, max_attempts_per_window=max_attempts)
    return service, invite_store, membership_store, rate_limiter


@pytest.mark.asyncio
async def test_valid_code_redemption_creates_membership_with_correct_role():
    service, invite_store, membership_store, _ = _build_service()
    invite_store.add(TeamInvite(code="ABCD1234", team_id=TEAM_ID, role=ADMIN, max_uses=5, used_count=0, expires_at=NOW + timedelta(days=7)))
    driver_id = uuid.uuid4()

    membership = await service.redeem(driver_id, "ABCD1234", requester_key="driver-1", now=NOW)

    assert membership.team_id == TEAM_ID
    assert membership.role == ADMIN
    assert membership.driver_id == driver_id
    assert (await membership_store.list_for_team(TEAM_ID))[0].driver_id == driver_id


@pytest.mark.asyncio
async def test_expired_code_rejected():
    service, invite_store, *_ = _build_service()
    invite_store.add(TeamInvite(code="EXPIRED1", team_id=TEAM_ID, role=MEMBER, max_uses=5, used_count=0, expires_at=NOW - timedelta(days=1)))

    with pytest.raises(InviteRedemptionError):
        await service.redeem(uuid.uuid4(), "EXPIRED1", requester_key="driver-1", now=NOW)


@pytest.mark.asyncio
async def test_exhausted_code_rejected():
    service, invite_store, *_ = _build_service()
    invite_store.add(TeamInvite(code="FULL0001", team_id=TEAM_ID, role=MEMBER, max_uses=1, used_count=1, expires_at=NOW + timedelta(days=7)))

    with pytest.raises(InviteRedemptionError):
        await service.redeem(uuid.uuid4(), "FULL0001", requester_key="driver-1", now=NOW)


@pytest.mark.asyncio
async def test_unknown_code_rejected():
    service, *_ = _build_service()

    with pytest.raises(InviteRedemptionError):
        await service.redeem(uuid.uuid4(), "NOTREAL1", requester_key="driver-1", now=NOW)


@pytest.mark.asyncio
async def test_concurrent_redemption_of_last_slot_only_one_succeeds():
    service, invite_store, membership_store, rate_limiter = _build_service(max_attempts=10)
    invite_store.add(TeamInvite(code="LASTSLOT", team_id=TEAM_ID, role=MEMBER, max_uses=1, used_count=0, expires_at=NOW + timedelta(days=7)))
    driver_a, driver_b = uuid.uuid4(), uuid.uuid4()

    results = await asyncio.gather(
        service.redeem(driver_a, "LASTSLOT", requester_key="driver-a", now=NOW),
        service.redeem(driver_b, "LASTSLOT", requester_key="driver-b", now=NOW),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, InviteRedemptionError)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert len(await membership_store.list_for_team(TEAM_ID)) == 1  # no over-redemption


@pytest.mark.asyncio
async def test_excessive_failed_attempts_rate_limited():
    service, invite_store, *_ = _build_service(max_attempts=3)

    for _ in range(3):
        with pytest.raises(InviteRedemptionError):
            await service.redeem(uuid.uuid4(), "WRONGCOD", requester_key="attacker-1", now=NOW)

    # 4th attempt from the same requester is blocked by the rate limiter,
    # not just "invalid code" -- even a newly-added valid code must not help.
    invite_store.add(TeamInvite(code="WRONGCOD", team_id=TEAM_ID, role=MEMBER, max_uses=5, used_count=0, expires_at=NOW + timedelta(days=7)))
    with pytest.raises(InviteRedemptionError, match="too many"):
        await service.redeem(uuid.uuid4(), "WRONGCOD", requester_key="attacker-1", now=NOW)


@pytest.mark.asyncio
async def test_rate_limit_is_isolated_per_requester():
    service, invite_store, *_ = _build_service(max_attempts=1)
    invite_store.add(TeamInvite(code="GOODCODE", team_id=TEAM_ID, role=MEMBER, max_uses=5, used_count=0, expires_at=NOW + timedelta(days=7)))

    await service.redeem(uuid.uuid4(), "GOODCODE", requester_key="driver-a", now=NOW)
    # A different requester's own attempt budget is unaffected.
    membership = await service.redeem(uuid.uuid4(), "GOODCODE", requester_key="driver-b", now=NOW)

    assert membership.team_id == TEAM_ID
