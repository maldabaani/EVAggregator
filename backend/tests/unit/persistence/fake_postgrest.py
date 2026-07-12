"""A tiny in-memory PostgREST simulator for testing `evagg.persistence.
supabase_*` repositories against something more realistic than a single
scripted response per call — these repositories make several sequential
requests per operation (resolve a charger's UUID, then act on it), and a
fake with real per-table storage catches sequencing bugs a single canned
response would hide.

Deliberately minimal: only `eq` filters, only what `SupabaseRestClient`
actually sends. Not a PostgREST reimplementation.
"""

from __future__ import annotations

import uuid
from urllib.parse import parse_qs, urlparse

import httpx


class FakePostgrest:
    def __init__(self) -> None:
        self.tables: dict[str, list[dict]] = {}

    def seed(self, table: str, row: dict) -> dict:
        row = dict(row)
        row.setdefault("id", str(uuid.uuid4()))
        self.tables.setdefault(table, []).append(row)
        return row

    def _match(self, row: dict, filters: dict[str, str]) -> bool:
        for column, value in filters.items():
            if not value.startswith("eq."):
                continue
            expected = value[len("eq."):]
            if str(row.get(column)) != expected:
                return False
        return True

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = urlparse(str(request.url))
        table = url.path.rsplit("/", 1)[-1]
        query = {k: v[0] for k, v in parse_qs(url.query).items()}
        filters = {k: v for k, v in query.items() if k not in ("order", "on_conflict", "select")}
        rows = self.tables.setdefault(table, [])

        if request.method == "GET":
            matched = [r for r in rows if self._match(r, filters)]
            return httpx.Response(200, json=matched)

        if request.method == "POST":
            import json as _json

            payload = _json.loads(request.content)
            on_conflict = query.get("on_conflict")
            if on_conflict:
                conflict_cols = on_conflict.split(",")
                existing = next(
                    (r for r in rows if all(str(r.get(c)) == str(payload.get(c)) for c in conflict_cols)), None
                )
                if existing is not None:
                    existing.update(payload)
                    return httpx.Response(200, json=[existing])
            new_row = dict(payload)
            new_row.setdefault("id", str(uuid.uuid4()))
            rows.append(new_row)
            return httpx.Response(201, json=[new_row])

        if request.method == "PATCH":
            import json as _json

            patch = _json.loads(request.content)
            matched = [r for r in rows if self._match(r, filters)]
            for r in matched:
                r.update(patch)
            return httpx.Response(200, json=matched)

        if request.method == "DELETE":
            remaining = [r for r in rows if not self._match(r, filters)]
            removed = [r for r in rows if self._match(r, filters)]
            self.tables[table] = remaining
            return httpx.Response(200, json=removed)

        return httpx.Response(405)


def build_client_with_fake(SupabaseRestClient, fake: FakePostgrest | None = None):
    fake = fake or FakePostgrest()
    transport = httpx.MockTransport(fake.handler)
    http_client = httpx.AsyncClient(transport=transport)
    client = SupabaseRestClient("https://project.supabase.co", "sb_publishable_test", http_client=http_client)
    return client, fake
