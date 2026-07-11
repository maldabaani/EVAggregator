"""Read-only mapping from the internal domain model to OCPI 2.1.1 wire
schemas. There is deliberately no `*_from_v211` direction — the shim never
accepts writes, so there's nothing to deserialize from a partner.
"""

from __future__ import annotations

from evagg.ocpi.domain import OCPILocation, OCPITariff
from evagg.ocpi.v211_shim.models import GeoLocationV211, LocationV211, TariffV211


def location_to_v211(location: OCPILocation) -> LocationV211:
    return LocationV211(
        id=location.id,
        name=location.name,
        address=location.address,
        city=location.city,
        postal_code=location.postal_code,
        country=location.country,
        coordinates=GeoLocationV211(latitude=location.coordinates.latitude, longitude=location.coordinates.longitude),
        last_updated=location.last_updated,
    )


def tariff_to_v211(tariff: OCPITariff) -> TariffV211:
    return TariffV211(id=tariff.id, currency=tariff.currency, last_updated=tariff.last_updated)
