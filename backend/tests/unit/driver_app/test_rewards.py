import uuid

import pytest

from evagg.driver_app.rewards import (
    InMemoryRewardsStore,
    InsufficientPointsError,
    RewardsService,
    UnknownRewardError,
)


@pytest.mark.asyncio
async def test_a_new_driver_starts_with_a_zero_balance():
    service = RewardsService(InMemoryRewardsStore())

    assert await service.get_balance(uuid.uuid4()) == 0


@pytest.mark.asyncio
async def test_awarding_for_a_completed_session_increases_the_balance():
    service = RewardsService(InMemoryRewardsStore())
    driver_id = uuid.uuid4()

    new_balance = await service.award_for_completed_session(driver_id)

    assert new_balance == 50
    assert await service.get_balance(driver_id) == 50


@pytest.mark.asyncio
async def test_awards_accumulate_across_multiple_sessions():
    service = RewardsService(InMemoryRewardsStore())
    driver_id = uuid.uuid4()

    await service.award_for_completed_session(driver_id)
    await service.award_for_completed_session(driver_id)

    assert await service.get_balance(driver_id) == 100


@pytest.mark.asyncio
async def test_redeeming_a_reward_deducts_its_points_cost():
    service = RewardsService(InMemoryRewardsStore())
    driver_id = uuid.uuid4()
    for _ in range(2):
        await service.award_for_completed_session(driver_id)  # 100 points

    new_balance = await service.redeem(driver_id, "free-coffee")  # costs 100

    assert new_balance == 0


@pytest.mark.asyncio
async def test_redeeming_with_insufficient_points_raises_and_does_not_deduct():
    service = RewardsService(InMemoryRewardsStore())
    driver_id = uuid.uuid4()
    await service.award_for_completed_session(driver_id)  # 50 points

    with pytest.raises(InsufficientPointsError):
        await service.redeem(driver_id, "free-coffee")  # costs 100

    assert await service.get_balance(driver_id) == 50


@pytest.mark.asyncio
async def test_redeeming_an_unknown_reward_raises():
    service = RewardsService(InMemoryRewardsStore())
    driver_id = uuid.uuid4()
    await service.award_for_completed_session(driver_id)

    with pytest.raises(UnknownRewardError):
        await service.redeem(driver_id, "not-a-real-reward")


@pytest.mark.asyncio
async def test_two_drivers_have_independent_balances():
    service = RewardsService(InMemoryRewardsStore())
    driver_a = uuid.uuid4()
    driver_b = uuid.uuid4()

    await service.award_for_completed_session(driver_a)

    assert await service.get_balance(driver_a) == 50
    assert await service.get_balance(driver_b) == 0
