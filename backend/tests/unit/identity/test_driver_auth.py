import pytest

from evagg.identity.driver_auth import (
    EmailAlreadyRegisteredError,
    InMemoryDriverAccountStore,
    verify_password,
)


@pytest.mark.asyncio
async def test_created_account_hashes_the_password_rather_than_storing_it_plaintext():
    store = InMemoryDriverAccountStore()

    account = await store.create("driver@example.com", "Jane Driver", "hunter2")

    assert account.password_hash != "hunter2"
    assert verify_password(account, "hunter2")
    assert not verify_password(account, "wrong-password")


@pytest.mark.asyncio
async def test_find_by_email_is_case_and_whitespace_insensitive():
    store = InMemoryDriverAccountStore()
    created = await store.create("Driver@Example.com ".strip(), "Jane Driver", "hunter2")

    found = await store.find_by_email("  driver@example.com  ")

    assert found is not None
    assert found.id == created.id


@pytest.mark.asyncio
async def test_creating_a_second_account_with_the_same_email_is_rejected():
    store = InMemoryDriverAccountStore()
    await store.create("driver@example.com", "Jane Driver", "hunter2")

    with pytest.raises(EmailAlreadyRegisteredError):
        await store.create("driver@example.com", "Someone Else", "different-password")


@pytest.mark.asyncio
async def test_get_by_id_returns_none_for_unknown_driver():
    store = InMemoryDriverAccountStore()

    import uuid

    assert await store.get(uuid.uuid4()) is None
