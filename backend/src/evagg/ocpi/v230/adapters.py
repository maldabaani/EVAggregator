"""Serializes/deserializes between the internal domain model and OCPI 2.3.0
wire schemas — a separate adapter from v221's, but both read/write the same
`OCPILocation` internal type, so Location business logic is written once.
"""

from __future__ import annotations

from evagg.ocpi.domain import OCPIGeoLocation, OCPILocation, OCPITariff
from evagg.ocpi.v230.models import (
    GeoLocationV230,
    LocationV230,
    PriceComponentV230,
    TariffElementV230,
    TariffV230,
)


def location_to_v230(location: OCPILocation) -> LocationV230:
    return LocationV230(
        id=location.id,
        party_id=location.party_id,
        country_code=location.country_code,
        publish=location.publish,
        name=location.name,
        address=location.address,
        city=location.city,
        postal_code=location.postal_code,
        country=location.country,
        coordinates=GeoLocationV230(
            latitude=location.coordinates.latitude, longitude=location.coordinates.longitude
        ),
        facilities=None,
        last_updated=location.last_updated,
    )


def location_from_v230(payload: LocationV230) -> OCPILocation:
    return OCPILocation(
        id=payload.id,
        party_id=payload.party_id,
        country_code=payload.country_code,
        publish=payload.publish,
        name=payload.name,
        address=payload.address,
        city=payload.city,
        postal_code=payload.postal_code,
        country=payload.country,
        coordinates=OCPIGeoLocation(latitude=payload.coordinates.latitude, longitude=payload.coordinates.longitude),
        last_updated=payload.last_updated,
    )


def tariff_to_v230(tariff: OCPITariff) -> TariffV230:
    return TariffV230(
        id=tariff.id,
        party_id=tariff.party_id,
        country_code=tariff.country_code,
        currency=tariff.currency,
        elements=[
            TariffElementV230(
                price_components=[
                    PriceComponentV230(type=pc.type, price=pc.price, step_size=pc.step_size)
                    for pc in element.price_components
                ]
            )
            for element in tariff.elements
        ],
        last_updated=tariff.last_updated,
    )
