"""Task 4.2 — join-code storage. `try_increment_used_count` is the piece
that must be race-safe: production uses
`UPDATE team_invite SET used_count = used_count + 1 WHERE code = :code AND
used_count < max_uses RETURNING used_count`, a single atomic statement so two
concurrent redeemers of the last slot can't both succeed. The in-memory
store models the same guarantee with a per-code lock — the point under test
is the outcome (no over-redemption), not the exact mechanism.
"""

from __future__ import annotations

import asyncio
import secrets
import string
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

INVITE_CODE_ALPHABET = string.ascii_uppercase + string.digits
INVITE_CODE_LENGTH = 8


def generate_invite_code() -> str:
    return "".join(secrets.choice(INVITE_CODE_ALPHABET) for _ in range(INVITE_CODE_LENGTH))


@dataclass
class TeamInvite:
    code: str
    team_id: uuid.UUID
    role: str
    max_uses: int
    used_count: int
    expires_at: datetime


class TeamInviteStore(Protocol):
    async def get(self, code: str) -> TeamInvite | None: ...

    async def try_increment_used_count(self, code: str) -> bool: ...


class InMemoryTeamInviteStore:
    def __init__(self) -> None:
        self._invites: dict[str, TeamInvite] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def add(self, invite: TeamInvite) -> None:
        self._invites[invite.code] = invite

    async def get(self, code: str) -> TeamInvite | None:
        return self._invites.get(code)

    async def try_increment_used_count(self, code: str) -> bool:
        lock = self._locks.setdefault(code, asyncio.Lock())
        async with lock:
            # Explicit yield point inside the critical section: without it,
            # two "concurrent" asyncio tasks with no real I/O never actually
            # interleave (one runs to completion before the other starts),
            # so a concurrency test against this store would pass trivially
            # regardless of whether the lock does anything. This forces a
            # genuine race for the lock to prove correct under.
            await asyncio.sleep(0)
            invite = self._invites.get(code)
            if invite is None:
                return False
            if invite.used_count >= invite.max_uses:
                return False
            invite.used_count += 1
            return True
