"""Task 3.1 — tariff persistence + the service tying validation, the
tenant's locked currency, and the pure calculator together."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from evagg.billing.tariff_calculator import TariffComponentInput, calculate_session_cost
from evagg.billing.tariff_validation import validate_tariff_components


@dataclass
class Tariff:
    id: uuid.UUID
    tenant_id: uuid.UUID
    name: str
    currency: str
    components: list[TariffComponentInput]


class TariffNotFoundError(Exception):
    pass


class TariffStore(Protocol):
    async def create(
        self, tenant_id: uuid.UUID, name: str, currency: str, components: list[TariffComponentInput]
    ) -> Tariff: ...

    async def update(self, tariff_id: uuid.UUID, name: str, components: list[TariffComponentInput]) -> Tariff: ...

    async def get(self, tariff_id: uuid.UUID) -> Tariff | None: ...


class InMemoryTariffStore:
    def __init__(self) -> None:
        self._tariffs: dict[uuid.UUID, Tariff] = {}

    async def create(
        self, tenant_id: uuid.UUID, name: str, currency: str, components: list[TariffComponentInput]
    ) -> Tariff:
        tariff = Tariff(id=uuid.uuid4(), tenant_id=tenant_id, name=name, currency=currency, components=components)
        self._tariffs[tariff.id] = tariff
        return tariff

    async def update(self, tariff_id: uuid.UUID, name: str, components: list[TariffComponentInput]) -> Tariff:
        existing = self._tariffs.get(tariff_id)
        if existing is None:
            raise TariffNotFoundError(str(tariff_id))
        updated = Tariff(id=tariff_id, tenant_id=existing.tenant_id, name=name, currency=existing.currency, components=components)
        self._tariffs[tariff_id] = updated
        return updated

    async def get(self, tariff_id: uuid.UUID) -> Tariff | None:
        return self._tariffs.get(tariff_id)


class TenantCurrencyProvider(Protocol):
    async def get_currency(self, tenant_id: uuid.UUID) -> str: ...


class InMemoryTenantCurrencyProvider:
    def __init__(self, currencies: dict[uuid.UUID, str] | None = None, default_currency: str = "USD") -> None:
        self._currencies: dict[uuid.UUID, str] = dict(currencies or {})
        self._default_currency = default_currency

    def set_currency(self, tenant_id: uuid.UUID, currency: str) -> None:
        self._currencies[tenant_id] = currency

    async def get_currency(self, tenant_id: uuid.UUID) -> str:
        return self._currencies.get(tenant_id, self._default_currency)


class TariffService:
    def __init__(self, store: TariffStore, currency_provider: TenantCurrencyProvider) -> None:
        self._store = store
        self._currency_provider = currency_provider

    async def create_tariff(self, tenant_id: uuid.UUID, name: str, components: list[TariffComponentInput]) -> Tariff:
        validate_tariff_components(components)
        currency = await self._currency_provider.get_currency(tenant_id)
        return await self._store.create(tenant_id, name, currency, components)

    async def update_tariff(self, tariff_id: uuid.UUID, name: str, components: list[TariffComponentInput]) -> Tariff:
        validate_tariff_components(components)
        return await self._store.update(tariff_id, name, components)

    async def preview(
        self, tariff_id: uuid.UUID, duration_minutes: float, kwh: float, idle_minutes: float = 0.0
    ) -> int:
        tariff = await self._store.get(tariff_id)
        if tariff is None:
            raise TariffNotFoundError(str(tariff_id))
        return calculate_session_cost(tariff.components, duration_minutes, kwh, idle_minutes)
