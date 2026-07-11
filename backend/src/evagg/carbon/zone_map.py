"""Task 1.4 — carbon zone mapping (backed by the `carbon_zone` table, Task
6.1: global reference data, no tenant_id — shared across all tenants)."""

from __future__ import annotations

from typing import Protocol


class CarbonZoneMap(Protocol):
    async def get_provider_zone_id(self, country_code: str, area_code: str) -> str | None: ...


class InMemoryCarbonZoneMap:
    def __init__(self, mapping: dict[tuple[str, str], str] | None = None) -> None:
        self._mapping: dict[tuple[str, str], str] = dict(mapping or {})

    def set_mapping(self, country_code: str, area_code: str, provider_zone_id: str) -> None:
        self._mapping[(country_code, area_code)] = provider_zone_id

    async def get_provider_zone_id(self, country_code: str, area_code: str) -> str | None:
        return self._mapping.get((country_code, area_code))
