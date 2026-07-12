"""OCPI 2.3.0 wire schemas. Same representative-subset caveat as v221 — kept
alongside 2.2.1 for forward compatibility per Task 1.1. Illustrates a genuine
version divergence: `facilities` is new in this schema, and `publish`
defaults to `True` rather than being required, matching 2.3.0's looser
publishing model.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GeoLocationV230(BaseModel):
    latitude: str
    longitude: str


class LocationV230(BaseModel):
    id: str
    party_id: str
    country_code: str
    publish: bool = True
    name: str | None = None
    address: str
    city: str
    postal_code: str | None = None
    country: str
    coordinates: GeoLocationV230
    facilities: list[str] | None = None
    last_updated: datetime


class PriceComponentV230(BaseModel):
    type: str
    price: float
    step_size: int


class TariffElementV230(BaseModel):
    price_components: list[PriceComponentV230]


class TariffV230(BaseModel):
    id: str
    party_id: str
    country_code: str
    currency: str
    elements: list[TariffElementV230]
    last_updated: datetime
