import uuid

import pytest

from evagg.gateway.refresh_store import InMemoryRefreshTokenStore, RefreshTokenError


@pytest.mark.asyncio
async def test_rotate_issues_new_token_and_invalidates_old():
    store = InMemoryRefreshTokenStore()
    tenant_id = uuid.uuid4()
    original = await store.issue(subject="driver-1", tenant_id=tenant_id)

    rotated = await store.rotate(original.token)

    assert rotated.token != original.token
    assert rotated.family_id == original.family_id
    # The old token must no longer work.
    with pytest.raises(RefreshTokenError):
        await store.rotate(original.token)


@pytest.mark.asyncio
async def test_reuse_of_retired_token_revokes_whole_family():
    store = InMemoryRefreshTokenStore()
    original = await store.issue(subject="driver-1", tenant_id=uuid.uuid4())
    rotated = await store.rotate(original.token)

    with pytest.raises(RefreshTokenError):
        await store.rotate(original.token)  # reuse of retired token

    # Family is now revoked entirely — even the legitimately-rotated token stops working.
    with pytest.raises(RefreshTokenError):
        await store.rotate(rotated.token)


@pytest.mark.asyncio
async def test_unknown_token_is_rejected():
    store = InMemoryRefreshTokenStore()
    with pytest.raises(RefreshTokenError):
        await store.rotate("not-a-real-token")
