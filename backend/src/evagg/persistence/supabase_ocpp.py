"""Supabase (PostgREST)-backed implementations of the OCPP gateway's storage
Protocols — `ChargerRegistry`, `ConnectorStore`, `TransactionRepository`,
`CredentialVerifier`, `MeterValueSink` — against the `charger`, `connector`,
`transaction`, and `meter_value` tables `docs/supabase/schema.sql` creates.

Every OCPP handler identifies a charger by `charge_point_id` (a string — the
WS path segment/Basic Auth username a real charger connects as), not the
internal UUID `charger.id` every other table FKs against. Each repository
here resolves that string to the UUID once per call, the same trade-off a
stateless REST backend forces regardless: there's no persistent session to
cache the mapping in across requests the way a connection-pooled SQLAlchemy
session could.

Not verified against a real Supabase project from this session — see
`docs/supabase/schema.sql`'s header. Every class here is unit-tested against
`httpx.MockTransport` instead (see `tests/unit/persistence/`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from evagg.ocpp_gateway.connectors import ConnectorStatus
from evagg.ocpp_gateway.credentials import hash_credential, verify_credential
from evagg.ocpp_gateway.meter_values import MeterReading
from evagg.ocpp_gateway.registration import BootResult
from evagg.ocpp_gateway.transactions import ActiveTransaction, StopResult, UnknownTransactionError
from evagg.persistence.supabase_client import SupabaseRestClient


class SupabaseChargerRegistry:
    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    async def upsert_on_boot(
        self,
        charger_id: str,
        tenant_id: uuid.UUID,
        vendor: str | None,
        model: str | None,
        firmware_version: str | None,
    ) -> BootResult:
        existing = await self._client.select_one("charger", {"charge_point_id": charger_id})
        if existing is None:
            await self._client.insert(
                "charger",
                {
                    "charge_point_id": charger_id,
                    "tenant_id": str(tenant_id),
                    "vendor": vendor,
                    "model": model,
                    "firmware_version": firmware_version,
                    "status": "pending",
                    "last_boot_at": datetime.now().isoformat(),
                },
            )
            return BootResult(status="pending", is_new_charger=True)

        await self._client.update(
            "charger",
            {"charge_point_id": charger_id},
            {
                "vendor": vendor,
                "model": model,
                "firmware_version": firmware_version,
                "last_boot_at": datetime.now().isoformat(),
            },
        )
        return BootResult(status=existing["status"], is_new_charger=False)


class SupabaseConnectorStore:
    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    async def _charger_row(self, charge_point_id: str) -> dict | None:
        return await self._client.select_one("charger", {"charge_point_id": charge_point_id})

    async def update_status(self, charger_id: str, connector_id: int, status: str, error_code: str | None) -> None:
        charger_row = await self._charger_row(charger_id)
        if charger_row is None:
            return
        await self._client.upsert(
            "connector",
            {
                "charger_id": charger_row["id"],
                "connector_id": connector_id,
                "status": status,
                "error_code": error_code,
                "tenant_id": charger_row["tenant_id"],
            },
            on_conflict="charger_id,connector_id",
        )

    async def get_status(self, charger_id: str, connector_id: int) -> ConnectorStatus | None:
        charger_row = await self._charger_row(charger_id)
        if charger_row is None:
            return None
        row = await self._client.select_one(
            "connector", {"charger_id": charger_row["id"], "connector_id": connector_id}
        )
        if row is None:
            return None
        return ConnectorStatus(
            charger_id=charger_id, connector_id=connector_id, status=row["status"], error_code=row["error_code"]
        )


class SupabaseCredentialVerifier:
    """Hashes/verifies the same way `InMemoryCredentialVerifier` does
    (`evagg.ocpp_gateway.credentials`) — only where the hash is stored
    differs (the `charger.ws_credential_hash` column, not a dict)."""

    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    async def set_credential(self, charger_id: str, secret: str) -> None:
        await self._client.update(
            "charger", {"charge_point_id": charger_id}, {"ws_credential_hash": hash_credential(secret)}
        )

    async def verify(self, charger_id: str, credential: str) -> bool:
        row = await self._client.select_one("charger", {"charge_point_id": charger_id})
        if row is None or not row.get("ws_credential_hash"):
            return False
        return verify_credential(credential, row["ws_credential_hash"])


class SupabaseTransactionRepository:
    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    async def _charger_uuid(self, charge_point_id: str) -> str | None:
        row = await self._client.select_one("charger", {"charge_point_id": charge_point_id})
        return row["id"] if row else None

    async def get_active_transaction(self, charger_id: str) -> ActiveTransaction | None:
        charger_uuid = await self._charger_uuid(charger_id)
        if charger_uuid is None:
            return None
        row = await self._client.select_one(
            "transaction", {"charger_id": charger_uuid, "status": "active"}
        )
        if row is None:
            return None
        return ActiveTransaction(
            id=uuid.UUID(row["id"]), charger_id=charger_id, connector_id=row["connector_id"], id_tag=row["id_tag"],
            start_timestamp=datetime.fromisoformat(row["start_timestamp"]),
        )

    async def start_transaction(
        self,
        charger_id: str,
        tenant_id: uuid.UUID,
        connector_id: int,
        id_tag: str,
        meter_start: int,
        start_timestamp: datetime,
    ) -> ActiveTransaction:
        charger_uuid = await self._charger_uuid(charger_id)
        row = await self._client.insert(
            "transaction",
            {
                "tenant_id": str(tenant_id),
                "charger_id": charger_uuid,
                "connector_id": connector_id,
                "id_tag": id_tag,
                "meter_start": meter_start,
                "start_timestamp": start_timestamp.isoformat(),
                "status": "active",
            },
        )
        return ActiveTransaction(
            id=uuid.UUID(row["id"]), charger_id=charger_id, connector_id=connector_id, id_tag=id_tag,
            start_timestamp=start_timestamp,
        )

    async def stop_transaction(
        self,
        transaction_id: uuid.UUID,
        meter_stop: int,
        stop_timestamp: datetime,
        reason: str | None,
    ) -> StopResult:
        row = await self._client.select_one("transaction", {"id": str(transaction_id)})
        if row is None:
            raise UnknownTransactionError(f"unknown transaction_id: {transaction_id}")

        if row["status"] == "completed":
            charger_row = await self._client.select_one("charger", {"id": row["charger_id"]})
            return StopResult(
                already_stopped=True,
                tenant_id=uuid.UUID(row["tenant_id"]),
                charger_id=charger_row["charge_point_id"] if charger_row else None,
            )

        await self._client.update(
            "transaction",
            {"id": str(transaction_id)},
            {
                "status": "completed",
                "meter_stop": meter_stop,
                "stop_timestamp": stop_timestamp.isoformat(),
                "stop_reason": reason,
            },
        )
        charger_row = await self._client.select_one("charger", {"id": row["charger_id"]})
        return StopResult(
            already_stopped=False,
            tenant_id=uuid.UUID(row["tenant_id"]),
            charger_id=charger_row["charge_point_id"] if charger_row else None,
        )


class SupabaseMeterValueSink:
    def __init__(self, client: SupabaseRestClient) -> None:
        self._client = client

    async def _charger_uuid(self, charge_point_id: str) -> str | None:
        row = await self._client.select_one("charger", {"charge_point_id": charge_point_id})
        return row["id"] if row else None

    async def write_batch(self, rows: list[MeterReading]) -> None:
        for reading in rows:
            charger_uuid = await self._charger_uuid(reading.charger_id)
            await self._client.insert(
                "meter_value",
                {
                    "tenant_id": str(reading.tenant_id),
                    "transaction_id": str(reading.transaction_id),
                    "charger_id": charger_uuid,
                    "ts": reading.ts.isoformat(),
                    "measurand": reading.measurand,
                    "value": reading.value,
                    "unit": reading.unit,
                },
            )
