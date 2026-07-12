"""OCPI 2.1.1 wire schemas — legacy, read-only shim. 2.1.1 predates the
`publish` flag introduced in later versions, so it's intentionally absent
here rather than defaulted, to keep the version boundary honest.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class GeoLocationV211(BaseModel):
    latitude: str
    longitude: str


class LocationV211(BaseModel):
    id: str
    type: str = "ON_STREET"
    name: str | None = None
    address: str
    city: str
    postal_code: str | None = None
    country: str
    coordinates: GeoLocationV211
    last_updated: datetime


class TariffV211(BaseModel):
    id: str
    currency: str
    last_updated: datetime
