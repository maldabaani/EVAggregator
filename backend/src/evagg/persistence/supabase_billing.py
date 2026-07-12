"""Supabase (PostgREST)-backed `TariffStore` and `WalletLedgerStore` against
the `tariff`/`tariff_component` and `wallet`/`wallet_ledger` tables
`docs/supabase/schema.sql` creates.

Not verified against a real Supabase project from this session — see that
file's header. Unit-tested against the in-memory PostgREST simulator in
`tests/unit/persistence/fake_postgrest.py` instead.
"""

from __future__ import annotations

import uuid

from evagg.billing.tariff_calculator import TariffComponentInput
from evagg.billing.tariffs import Tariff, TariffNotFoundError
from evagg.persistence.supabase_client import SupabaseRestClient


class SupabaseTariffStore:
    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    async def create(
        self, tenant_id: uuid.UUID, name: str, currency: str, components: list[TariffComponentInput]
    ) -> Tariff:
        row = await self._client.insert(
            "tariff", {"tenant_id": str(tenant_id), "name": name, "currency": currency}
        )
        tariff_id = uuid.UUID(row["id"])
        await self._insert_components(tenant_id, tariff_id, components)
        return Tariff(id=tariff_id, tenant_id=tenant_id, name=name, currency=currency, components=components)

    async def update(self, tariff_id: uuid.UUID, name: str, components: list[TariffComponentInput]) -> Tariff:
        rows = await self._client.update("tariff", {"id": str(tariff_id)}, {"name": name})
        if not rows:
            raise TariffNotFoundError(str(tariff_id))
        existing = rows[0]
        await self._client.delete("tariff_component", {"tariff_id": str(tariff_id)})
        await self._insert_components(uuid.UUID(existing["tenant_id"]), tariff_id, components)
        return Tariff(
            id=tariff_id, tenant_id=uuid.UUID(existing["tenant_id"]), name=name,
            currency=existing["currency"], components=components,
        )

    async def get(self, tariff_id: uuid.UUID) -> Tariff | None:
        row = await self._client.select_one("tariff", {"id": str(tariff_id)})
        if row is None:
            return None
        return await self._hydrate(row)

    async def list_all(self) -> list[Tariff]:
        rows = await self._client.select("tariff")
        return [await self._hydrate(row) for row in rows]

    async def _hydrate(self, row: dict) -> Tariff:
        tariff_id = uuid.UUID(row["id"])
        component_rows = await self._client.select("tariff_component", {"tariff_id": str(tariff_id)})
        components = [
            TariffComponentInput(
                type=c["type"], price_minor_units=c["price_minor_units"],
                step_size=c["step_size"], applies_after_minutes=c.get("applies_after_minutes"),
            )
            for c in component_rows
        ]
        return Tariff(
            id=tariff_id, tenant_id=uuid.UUID(row["tenant_id"]), name=row["name"],
            currency=row["currency"], components=components,
        )

    async def _insert_components(
        self, tenant_id: uuid.UUID, tariff_id: uuid.UUID, components: list[TariffComponentInput]
    ) -> None:
        for component in components:
            await self._client.insert(
                "tariff_component",
                {
                    "tenant_id": str(tenant_id),
                    "tariff_id": str(tariff_id),
                    "type": component.type,
                    "price_minor_units": component.price_minor_units,
                    "step_size": component.step_size,
                    "applies_after_minutes": component.applies_after_minutes,
                },
            )


class SupabaseWalletLedgerStore:
    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    async def _tenant_id_for_wallet(self, wallet_id: uuid.UUID) -> str | None:
        row = await self._client.select_one("wallet", {"id": str(wallet_id)})
        return row["tenant_id"] if row else None

    async def append(self, wallet_id: uuid.UUID, amount_minor_units: int, entry_type: str, reference_id: str) -> None:
        tenant_id = await self._tenant_id_for_wallet(wallet_id)
        await self._client.insert(
            "wallet_ledger",
            {
                "tenant_id": tenant_id,
                "wallet_id": str(wallet_id),
                "amount_minor_units": amount_minor_units,
                "type": entry_type,
                "reference_id": reference_id,
            },
        )

    async def sum_for_wallet(self, wallet_id: uuid.UUID) -> int:
        rows = await self._client.select("wallet_ledger", {"wallet_id": str(wallet_id)})
        return sum(r["amount_minor_units"] for r in rows)

    async def has_reference(self, wallet_id: uuid.UUID, reference_id: str) -> bool:
        rows = await self._client.select(
            "wallet_ledger", {"wallet_id": str(wallet_id), "reference_id": reference_id}
        )
        return len(rows) > 0
