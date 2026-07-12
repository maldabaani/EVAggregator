from __future__ import annotations

import uuid

import pytest

from evagg.charging_auth.autocharge import InMemoryAutochargeMacStore, synthesize_id_tag_for_mac


@pytest.mark.asyncio
async def test_autocharge_mac_maps_to_correct_driver_id_tag():
    store = InMemoryAutochargeMacStore()
    driver_id = uuid.uuid4()
    store.register("AA:BB:CC:DD:EE:FF", driver_id)

    resolved_driver_id = await store.get_driver_id_for_mac("aa:bb:cc:dd:ee:ff")  # different case

    assert resolved_driver_id == driver_id
    assert synthesize_id_tag_for_mac("aa:bb:cc:dd:ee:ff") == "AUTOCHARGE:AA:BB:CC:DD:EE:FF"


@pytest.mark.asyncio
async def test_unregistered_mac_resolves_to_no_driver():
    store = InMemoryAutochargeMacStore()

    resolved_driver_id = await store.get_driver_id_for_mac("00:00:00:00:00:00")

    assert resolved_driver_id is None
