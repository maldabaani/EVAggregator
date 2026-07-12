"""A thin PostgREST client — the transport every `evagg.persistence.supabase_*`
repository is built on. Not tested against a real Supabase project from this
session (see `docs/supabase/schema.sql`'s header for why); every test here
uses `httpx.MockTransport`, the same pattern `StripePaymentProvider`'s and
`ElectricityMapsClient`'s tests already use for a real third-party HTTP API.

PostgREST's request shape (https://postgrest.org/en/stable/references/api.html):
  GET    /<table>?<column>=eq.<value>&select=...   — read, filtered
  POST   /<table>                                   — insert (Prefer: return=representation to get the row back)
  PATCH  /<table>?<column>=eq.<value>                — update matching rows
  DELETE /<table>?<column>=eq.<value>                — delete matching rows

Every method takes `filters` as a dict of column -> exact value, rendered as
`column=eq.value` query params — this app's repositories only ever need
equality filters (by id, by tenant_id, by charger_id, ...), never PostgREST's
richer operators, so nothing more general was built.
"""

from __future__ import annotations

from typing import Any

import httpx


class SupabaseError(Exception):
    pass


class SupabaseRestClient:
    def __init__(self, base_url: str, api_key: str, http_client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._headers = {
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }
        self._http_client = http_client

    def _client(self) -> httpx.AsyncClient:
        return self._http_client or httpx.AsyncClient()

    def _table_url(self, table: str) -> str:
        return f"{self._base_url}/rest/v1/{table}"

    @staticmethod
    def _filter_params(filters: dict[str, Any] | None) -> dict[str, str]:
        if not filters:
            return {}
        return {column: f"eq.{value}" for column, value in filters.items()}

    async def select(
        self, table: str, filters: dict[str, Any] | None = None, order: str | None = None
    ) -> list[dict]:
        params = self._filter_params(filters)
        if order:
            params["order"] = order
        response = await self._client().get(self._table_url(table), params=params, headers=self._headers)
        if response.status_code >= 400:
            raise SupabaseError(f"GET {table} failed (status {response.status_code}): {response.text}")
        return response.json()

    async def select_one(self, table: str, filters: dict[str, Any]) -> dict | None:
        rows = await self.select(table, filters)
        return rows[0] if rows else None

    async def insert(self, table: str, row: dict[str, Any]) -> dict:
        headers = {**self._headers, "Prefer": "return=representation"}
        response = await self._client().post(self._table_url(table), json=row, headers=headers)
        if response.status_code >= 400:
            raise SupabaseError(f"POST {table} failed (status {response.status_code}): {response.text}")
        data = response.json()
        return data[0] if isinstance(data, list) else data

    async def update(self, table: str, filters: dict[str, Any], patch: dict[str, Any]) -> list[dict]:
        headers = {**self._headers, "Prefer": "return=representation"}
        params = self._filter_params(filters)
        response = await self._client().patch(
            self._table_url(table), params=params, json=patch, headers=headers
        )
        if response.status_code >= 400:
            raise SupabaseError(f"PATCH {table} failed (status {response.status_code}): {response.text}")
        return response.json()

    async def delete(self, table: str, filters: dict[str, Any]) -> None:
        params = self._filter_params(filters)
        response = await self._client().delete(self._table_url(table), params=params, headers=self._headers)
        if response.status_code >= 400:
            raise SupabaseError(f"DELETE {table} failed (status {response.status_code}): {response.text}")

    async def upsert(self, table: str, row: dict[str, Any], on_conflict: str) -> dict:
        headers = {
            **self._headers,
            "Prefer": "return=representation,resolution=merge-duplicates",
        }
        response = await self._client().post(
            self._table_url(table), params={"on_conflict": on_conflict}, json=row, headers=headers
        )
        if response.status_code >= 400:
            raise SupabaseError(f"UPSERT {table} failed (status {response.status_code}): {response.text}")
        data = response.json()
        return data[0] if isinstance(data, list) else data
