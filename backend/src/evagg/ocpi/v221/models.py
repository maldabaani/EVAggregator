"""OCPI 2.2.1 wire schemas — a representative subset (Location) sufficient to
prove the per-version adapter architecture, not full spec field coverage.
Extending to the remaining Location/Token/Session/CDR fields is incremental
work on top of this same pattern, not a redesign.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GeoLocationV221(BaseModel):
    latitude: str
    longitude: str


class LocationV221(BaseModel):
    id: str
    party_id: str
    country_code: str
    publish: bool
    name: str | None = None
    address: str
    city: str
    postal_code: str | None = None
    country: str
    coordinates: GeoLocationV221
    last_updated: datetime


class PriceComponentV221(BaseModel):
    type: str
    price: float
    step_size: int


class TariffElementV221(BaseModel):
    price_components: list[PriceComponentV221]


class TariffV221(BaseModel):
    id: str
    party_id: str
    country_code: str
    currency: str
    elements: list[TariffElementV221]
    last_updated: datetime
