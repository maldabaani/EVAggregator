"""GET /driver/rewards, POST /driver/rewards/redeem — mounted on
`evagg.main` (same as `session_start_router.py`), reached by the driver
through `evagg.driver_app.rewards_forwarder`. `driver_id` is a plain
request field, always overwritten by that forwarder with the caller's
verified identity, rather than read via `require_current_tenant`-style
middleware — the same convention `AppStartRequest`/`StopSessionRequest`
already use.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from evagg.driver_app.rewards import REWARD_CATALOG, InsufficientPointsError, RewardsService, UnknownRewardError


class RedeemRequest(BaseModel):
    driver_id: str
    reward_id: str


def _catalog_dict() -> list[dict]:
    return [{"id": item.id, "name": item.name, "points_cost": item.points_cost} for item in REWARD_CATALOG]


def build_rewards_router(service_dependency) -> APIRouter:
    router = APIRouter(prefix="/driver/rewards", tags=["driver-rewards"])

    @router.get("")
    async def get_rewards(driver_id: uuid.UUID, service: RewardsService = Depends(service_dependency)) -> dict:
        balance = await service.get_balance(driver_id)
        return {"balance": balance, "catalog": _catalog_dict()}

    @router.post("/redeem")
    async def redeem(body: RedeemRequest, service: RewardsService = Depends(service_dependency)) -> dict:
        try:
            new_balance = await service.redeem(uuid.UUID(body.driver_id), body.reward_id)
        except UnknownRewardError as exc:
            raise HTTPException(status_code=404, detail="unknown reward") from exc
        except InsufficientPointsError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return {"balance": new_balance}

    return router
