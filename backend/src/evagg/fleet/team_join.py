"""Task 4.2 — POST /teams/join redemption flow: rate-limited per requester
(IP/account) to blunt brute-forcing, then validated (exists, not expired),
then redeemed via the race-safe atomic increment.

Reuses `evagg.gateway.rate_limit.RateLimiter` (Task 6.3) rather than a new
rate-limiting implementation — same fixed-window semantics, same interface.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from evagg.fleet.team_invites import TeamInviteStore
from evagg.fleet.team_membership import DriverTeamMembership, MembershipStore
from evagg.gateway.rate_limit import RateLimiter


class InviteRedemptionError(Exception):
    pass


class TeamJoinService:
    def __init__(
        self,
        invite_store: TeamInviteStore,
        membership_store: MembershipStore,
        rate_limiter: RateLimiter,
        max_attempts_per_window: int = 5,
        window_seconds: int = 60,
    ) -> None:
        self._invite_store = invite_store
        self._membership_store = membership_store
        self._rate_limiter = rate_limiter
        self._max_attempts_per_window = max_attempts_per_window
        self._window_seconds = window_seconds

    async def redeem(
        self, driver_id: uuid.UUID, code: str, requester_key: str, now: datetime
    ) -> DriverTeamMembership:
        allowed = await self._rate_limiter.allow(
            key=f"team-join:{requester_key}",
            limit=self._max_attempts_per_window,
            window_seconds=self._window_seconds,
        )
        if not allowed:
            raise InviteRedemptionError("too many redemption attempts; try again later")

        invite = await self._invite_store.get(code)
        if invite is None:
            raise InviteRedemptionError("invalid invite code")

        if invite.expires_at <= now:
            raise InviteRedemptionError("invite code has expired")

        won_slot = await self._invite_store.try_increment_used_count(code)
        if not won_slot:
            raise InviteRedemptionError("invite code has been fully redeemed")

        return await self._membership_store.create(driver_id, invite.team_id, invite.role)
