from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from evagg.billing.tariff_versioning import InMemoryTariffVersionStore

TARIFF_ID = uuid.uuid4()


@pytest.mark.asyncio
async def test_session_billed_against_tariff_version_active_at_start_time():
    store = InMemoryTariffVersionStore()
    v1_effective = datetime(2026, 1, 1, tzinfo=timezone.utc)
    v2_effective = datetime(2026, 6, 1, tzinfo=timezone.utc)
    v1 = await store.add_version(TARIFF_ID, version_no=1, effective_from=v1_effective, effective_to=v2_effective)
    await store.add_version(TARIFF_ID, version_no=2, effective_from=v2_effective, effective_to=None)

    session_start = datetime(2026, 3, 15, tzinfo=timezone.utc)  # under v1
    active = await store.get_active_version(TARIFF_ID, at=session_start)

    assert active.id == v1.id
    assert active.version_no == 1


@pytest.mark.asyncio
async def test_tariff_update_after_session_start_does_not_change_its_billed_version():
    store = InMemoryTariffVersionStore()
    v1_effective = datetime(2026, 1, 1, tzinfo=timezone.utc)
    v1 = await store.add_version(TARIFF_ID, version_no=1, effective_from=v1_effective, effective_to=None)

    session_start = datetime(2026, 3, 1, tzinfo=timezone.utc)
    resolved_at_start = await store.get_active_version(TARIFF_ID, at=session_start)
    assert resolved_at_start.id == v1.id

    # Tariff is updated (v2) *after* the session already started.
    v2_effective = datetime(2026, 4, 1, tzinfo=timezone.utc)
    await store.add_version(TARIFF_ID, version_no=2, effective_from=v2_effective, effective_to=None)
    # v1 must now have an effective_to boundary in a real system; this store
    # models the append-only version log directly, so we re-resolve as of
    # the *original* session_start to prove it still lands on v1.
    resolved_again = await store.get_active_version(TARIFF_ID, at=session_start)

    assert resolved_again.id == v1.id  # unaffected by the later v2 addition


@pytest.mark.asyncio
async def test_no_active_version_before_any_effective_from():
    store = InMemoryTariffVersionStore()
    await store.add_version(TARIFF_ID, version_no=1, effective_from=datetime(2026, 6, 1, tzinfo=timezone.utc))

    result = await store.get_active_version(TARIFF_ID, at=datetime(2026, 1, 1, tzinfo=timezone.utc))

    assert result is None


@pytest.mark.asyncio
async def test_version_with_no_effective_to_remains_active_indefinitely():
    store = InMemoryTariffVersionStore()
    await store.add_version(TARIFF_ID, version_no=1, effective_from=datetime(2026, 1, 1, tzinfo=timezone.utc))

    far_future = datetime(2099, 1, 1, tzinfo=timezone.utc)
    result = await store.get_active_version(TARIFF_ID, at=far_future)

    assert result is not None
    assert result.version_no == 1
