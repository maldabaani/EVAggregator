import json

import httpx
import pytest

from evagg.persistence.supabase_client import SupabaseError, SupabaseRestClient

BASE_URL = "https://project.supabase.co"
API_KEY = "sb_publishable_test"


def _client(handler) -> SupabaseRestClient:
    transport = httpx.MockTransport(handler)
    http_client = httpx.AsyncClient(transport=transport)
    return SupabaseRestClient(BASE_URL, API_KEY, http_client=http_client)


@pytest.mark.asyncio
async def test_select_sends_eq_filters_and_auth_headers():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json=[{"id": "1", "name": "Standard"}])

    client = _client(handler)
    rows = await client.select("tariff", filters={"tenant_id": "abc", "name": "Standard"})

    assert rows == [{"id": "1", "name": "Standard"}]
    assert "tenant_id=eq.abc" in captured["url"]
    assert "name=eq.Standard" in captured["url"]
    assert captured["headers"]["apikey"] == API_KEY
    assert captured["headers"]["authorization"] == f"Bearer {API_KEY}"


@pytest.mark.asyncio
async def test_select_one_returns_first_row_or_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": "1"}])

    client = _client(handler)
    assert await client.select_one("tariff", {"id": "1"}) == {"id": "1"}

    def empty_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    client2 = _client(empty_handler)
    assert await client2.select_one("tariff", {"id": "missing"}) is None


@pytest.mark.asyncio
async def test_insert_sends_representation_preference_and_body():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["prefer"] = request.headers.get("prefer")
        captured["body"] = json.loads(request.content)
        return httpx.Response(201, json=[{"id": "new-1", "name": "Standard"}])

    client = _client(handler)
    row = await client.insert("tariff", {"name": "Standard"})

    assert row == {"id": "new-1", "name": "Standard"}
    assert captured["method"] == "POST"
    assert captured["prefer"] == "return=representation"
    assert captured["body"] == {"name": "Standard"}


@pytest.mark.asyncio
async def test_update_sends_patch_with_filters_and_body():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=[{"id": "1", "balance_minor_units": 500}])

    client = _client(handler)
    rows = await client.update("wallet", {"id": "1"}, {"balance_minor_units": 500})

    assert rows == [{"id": "1", "balance_minor_units": 500}]
    assert captured["method"] == "PATCH"
    assert "id=eq.1" in captured["url"]
    assert captured["body"] == {"balance_minor_units": 500}


@pytest.mark.asyncio
async def test_delete_sends_filters_no_body_expected():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["method"] = request.method
        captured["url"] = str(request.url)
        return httpx.Response(204)

    client = _client(handler)
    await client.delete("tariff", {"id": "1"})

    assert captured["method"] == "DELETE"
    assert "id=eq.1" in captured["url"]


@pytest.mark.asyncio
async def test_upsert_sends_merge_duplicates_preference_and_on_conflict_param():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["prefer"] = request.headers.get("prefer")
        captured["url"] = str(request.url)
        return httpx.Response(201, json=[{"id": "1"}])

    client = _client(handler)
    row = await client.upsert("charger", {"charge_point_id": "c-1"}, on_conflict="charge_point_id")

    assert row == {"id": "1"}
    assert "merge-duplicates" in captured["prefer"]
    assert "on_conflict=charge_point_id" in captured["url"]


@pytest.mark.asyncio
async def test_error_response_raises_supabase_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "bad filter"})

    client = _client(handler)
    with pytest.raises(SupabaseError, match="GET tariff failed"):
        await client.select("tariff")
