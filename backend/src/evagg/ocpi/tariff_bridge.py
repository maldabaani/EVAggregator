"""OCPI Tariffs module — exposes the internal tariff catalog (Task 3.1's
`TariffService`) read-only over `GET /ocpi/{version}/tariffs`, bilateral
only (Task 1.3's chosen roaming topology: no hub-forwarding, so one CPO
party identity is enough).

Unlike Locations (Task 1.2), there's no separate materialized/synced store
here: tariffs only change when a portal admin edits one, not in reaction to
a high-volume OCPP event stream, so converting on every read straight from
`TariffService` is simpler and can never go stale.

`last_updated` is synthesized as "now" at read time — the internal `Tariff`
model (Task 3.1) has no created/updated timestamp to report instead. A
partner doing incremental sync off this field would see every tariff as
freshly changed on every poll; real change-tracking would need a timestamp
added to the internal model, which is a persistence-layer change outside
this task's scope.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from evagg.billing.tariffs import Tariff, TariffService
from evagg.ocpi.domain import OCPIPriceComponent, OCPITariff, OCPITariffElement

_COMPONENT_TYPE_TO_OCPI = {
    "energy": "ENERGY",
    "time": "TIME",
    "flat": "FLAT",
    "idle": "PARKING_TIME",
}


def to_ocpi_tariff(tariff: Tariff, party_id: str, country_code: str) -> OCPITariff:
    price_components = [
        OCPIPriceComponent(
            type=_COMPONENT_TYPE_TO_OCPI.get(component.type, component.type.upper()),
            price=component.price_minor_units / 100,
            step_size=component.step_size,
        )
        for component in tariff.components
    ]
    return OCPITariff(
        id=str(tariff.id),
        party_id=party_id,
        country_code=country_code,
        currency=tariff.currency,
        elements=[OCPITariffElement(price_components=price_components)],
        last_updated=datetime.now(timezone.utc),
    )


class OcpiTariffCatalog:
    """The read-through view the OCPI router calls — wraps `TariffService`
    with this CPO's own party identity so the router never has to know it."""

    def __init__(self, tariff_service: TariffService, party_id: str, country_code: str) -> None:
        self._tariff_service = tariff_service
        self._party_id = party_id
        self._country_code = country_code

    async def list_all(self) -> list[OCPITariff]:
        tariffs = await self._tariff_service.list_all_tariffs()
        return [to_ocpi_tariff(tariff, self._party_id, self._country_code) for tariff in tariffs]

    async def get(self, tariff_id: str) -> OCPITariff | None:
        try:
            parsed_id = uuid.UUID(tariff_id)
        except ValueError:
            return None
        tariff = await self._tariff_service.get_tariff(parsed_id)
        return to_ocpi_tariff(tariff, self._party_id, self._country_code) if tariff is not None else None
