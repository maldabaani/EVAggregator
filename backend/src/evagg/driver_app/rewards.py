"""Driver rewards — a points ledger plus a small static redemption
catalog. Points are earned per completed charging session, a flat amount
rather than a per-kWh rate: there's no read-side query for meter values
anywhere in this codebase yet (see session_start.py's own docstring on
the same constraint), so there's no real energy figure to base a rate on.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

POINTS_PER_COMPLETED_SESSION = 50


@dataclass(frozen=True)
class RewardCatalogItem:
    id: str
    name: str
    points_cost: int


REWARD_CATALOG: tuple[RewardCatalogItem, ...] = (
    RewardCatalogItem(id="free-coffee", name="Free coffee voucher", points_cost=100),
    RewardCatalogItem(id="discount-5", name="5% off your next session", points_cost=200),
    RewardCatalogItem(id="discount-10", name="10% off your next session", points_cost=350),
)


class InsufficientPointsError(Exception):
    pass


class UnknownRewardError(Exception):
    pass


class RewardsStore(Protocol):
    async def get_balance(self, driver_id: uuid.UUID) -> int: ...

    async def add_points(self, driver_id: uuid.UUID, points: int) -> int: ...

    async def deduct_points(self, driver_id: uuid.UUID, points: int) -> int: ...


class InMemoryRewardsStore:
    def __init__(self) -> None:
        self._balances: dict[uuid.UUID, int] = {}

    async def get_balance(self, driver_id: uuid.UUID) -> int:
        return self._balances.get(driver_id, 0)

    async def add_points(self, driver_id: uuid.UUID, points: int) -> int:
        new_balance = self._balances.get(driver_id, 0) + points
        self._balances[driver_id] = new_balance
        return new_balance

    async def deduct_points(self, driver_id: uuid.UUID, points: int) -> int:
        new_balance = self._balances.get(driver_id, 0) - points
        self._balances[driver_id] = new_balance
        return new_balance


class RewardsService:
    def __init__(self, store: RewardsStore) -> None:
        self._store = store

    async def award_for_completed_session(self, driver_id: uuid.UUID) -> int:
        return await self._store.add_points(driver_id, POINTS_PER_COMPLETED_SESSION)

    async def get_balance(self, driver_id: uuid.UUID) -> int:
        return await self._store.get_balance(driver_id)

    async def redeem(self, driver_id: uuid.UUID, reward_id: str) -> int:
        reward = next((item for item in REWARD_CATALOG if item.id == reward_id), None)
        if reward is None:
            raise UnknownRewardError(reward_id)
        balance = await self._store.get_balance(driver_id)
        if balance < reward.points_cost:
            raise InsufficientPointsError(f"need {reward.points_cost} points, have {balance}")
        return await self._store.deduct_points(driver_id, reward.points_cost)
