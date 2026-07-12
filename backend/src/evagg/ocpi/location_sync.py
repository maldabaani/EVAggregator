"""Task 1.2 — Locations sync: reacts to OCPP `StatusNotification` events
(Epic 2 Task 2.4's `ocpp.{tenant}.{charger}.status_notification` subject) by
updating the materialized Location read model and pushing the change to
every connected CPO partner, so roaming partners are never served by
querying live OCPP state directly.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Protocol

import httpx

from evagg.ocpi.domain import OCPILocation
from evagg.ocpi.locations import LocationRepository


class ChargerLocationMap(Protocol):
    async def get_location_id_for_charger(self, charger_id: str) -> str | None: ...


class InMemoryChargerLocationMap:
    def __init__(self, mapping: dict[str, str] | None = None) -> None:
        self._mapping: dict[str, str] = dict(mapping or {})

    def set_mapping(self, charger_id: str, location_id: str) -> None:
        self._mapping[charger_id] = location_id

    async def get_location_id_for_charger(self, charger_id: str) -> str | None:
        return self._mapping.get(charger_id)


class PartnerPushClient(Protocol):
    async def push_location_update(self, partner_id: uuid.UUID, location: OCPILocation) -> None: ...


class InMemoryPartnerPushClient:
    """The `app_mode=testing` default — records pushes for assertions
    instead of calling out to a real partner network."""

    def __init__(self) -> None:
        self.location_pushes: list[tuple[uuid.UUID, OCPILocation]] = []

    async def push_location_update(self, partner_id: uuid.UUID, location: OCPILocation) -> None:
        self.location_pushes.append((partner_id, location))


class PartnerPushError(Exception):
    pass


class HttpPartnerPushClient:
    """Real OCPI `PATCH /locations/{country_code}/{party_id}/{location_id}`
    push — the `app_mode=production` implementation, pending real per-partner
    base URLs and tokens.

    OCPI's actual spec has each partner publish its own base URL during
    credentials negotiation (Task 1.1's `versions`/`credentials` exchange),
    which would mean looking one up per `partner_id` here rather than using
    one shared `base_url`/`token` for every partner. That per-partner
    endpoint store doesn't exist yet — this demonstrates the real transport
    shape against a single configured endpoint (`settings.
    ocpi_partner_push_base_url`/`ocpi_partner_push_token`) until it does.
    """

    def __init__(self, base_url: str, token: str, http_client: httpx.AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._http_client = http_client

    async def push_location_update(self, partner_id: uuid.UUID, location: OCPILocation) -> None:
        client = self._http_client or httpx.AsyncClient()
        url = f"{self._base_url}/locations/{location.country_code}/{location.party_id}/{location.id}"
        try:
            response = await client.patch(
                url,
                json=location.model_dump(mode="json"),
                headers={"Authorization": f"Token {self._token}"},
            )
        except httpx.HTTPError as exc:
            raise PartnerPushError(f"partner {partner_id} unreachable: {exc}") from exc

        if response.status_code >= 400:
            raise PartnerPushError(f"partner {partner_id} rejected location push (status {response.status_code})")


class LocationSyncService:
    def __init__(
        self,
        charger_location_map: ChargerLocationMap,
        location_repo: LocationRepository,
        push_client: PartnerPushClient,
    ) -> None:
        self._charger_location_map = charger_location_map
        self._location_repo = location_repo
        self._push_client = push_client

    async def handle_status_notification(
        self, charger_id: str, status: str, connected_partner_ids: list[uuid.UUID]
    ) -> OCPILocation | None:
        location_id = await self._charger_location_map.get_location_id_for_charger(charger_id)
        if location_id is None:
            return None

        location = await self._location_repo.get(location_id)
        if location is None:
            return None

        updated = location.model_copy(update={"evse_status": status, "last_updated": datetime.now(timezone.utc)})
        await self._location_repo.upsert(updated)

        for partner_id in connected_partner_ids:
            await self._push_client.push_location_update(partner_id, updated)

        return updated
