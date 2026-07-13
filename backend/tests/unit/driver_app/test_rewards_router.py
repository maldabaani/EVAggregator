import asyncio
import uuid

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.driver_app.rewards import InMemoryRewardsStore, RewardsService
from evagg.driver_app.rewards_router import build_rewards_router

DRIVER_ID = uuid.uuid4()


def _build_app():
    service = RewardsService(InMemoryRewardsStore())

    async def get_service():
        return service

    app = FastAPI()
    app.include_router(build_rewards_router(get_service))
    return app, service


def test_get_rewards_returns_balance_and_catalog():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.get("/driver/rewards", params={"driver_id": str(DRIVER_ID)})

    assert response.status_code == 200
    body = response.json()
    assert body["balance"] == 0
    assert any(item["id"] == "free-coffee" for item in body["catalog"])


def test_redeem_deducts_points_on_success():
    app, service = _build_app()
    client = TestClient(app)

    asyncio.run(service.award_for_completed_session(DRIVER_ID))
    asyncio.run(service.award_for_completed_session(DRIVER_ID))

    response = client.post("/driver/rewards/redeem", json={"driver_id": str(DRIVER_ID), "reward_id": "free-coffee"})

    assert response.status_code == 200
    assert response.json()["balance"] == 0


def test_redeem_with_insufficient_points_returns_400():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.post("/driver/rewards/redeem", json={"driver_id": str(DRIVER_ID), "reward_id": "free-coffee"})

    assert response.status_code == 400


def test_redeem_of_an_unknown_reward_returns_404():
    app, _ = _build_app()
    client = TestClient(app)

    response = client.post("/driver/rewards/redeem", json={"driver_id": str(DRIVER_ID), "reward_id": "bogus"})

    assert response.status_code == 404
