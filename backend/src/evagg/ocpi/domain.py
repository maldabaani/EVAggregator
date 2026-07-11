"""Task 1.1 — the single internal domain model every OCPI version's adapter
serializes to/from. This is the module boundary that prevents 3x duplication
of business logic across ocpi/v221, ocpi/v230, ocpi/v211_shim: business code
elsewhere in the platform only ever touches these types, never a
version-specific Pydantic schema directly.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OCPIGeoLocation(BaseModel):
    latitude: str
    longitude: str


class OCPILocation(BaseModel):
    id: str
    party_id: str
    country_code: str
    publish: bool
    name: str | None = None
    address: str
    city: str
    postal_code: str | None = None
    country: str
    coordinates: OCPIGeoLocation
    last_updated: datetime


class OCPITariff(BaseModel):
    id: str
    party_id: str
    country_code: str
    currency: str
    last_updated: datetime


class OCPIToken(BaseModel):
    uid: str
    type: str  # 'RFID' | 'APP_USER' | 'OTHER'
    auth_id: str
    issuer: str
    valid: bool
    whitelist: str  # 'ALWAYS' | 'ALLOWED' | 'ALLOWED_OFFLINE' | 'NEVER'
    last_updated: datetime


class OCPISession(BaseModel):
    id: str
    start_datetime: datetime
    end_datetime: datetime | None = None
    kwh: float
    auth_method: str
    location_id: str
    currency: str
    status: str  # 'ACTIVE' | 'COMPLETED' | 'INVALID' | 'PENDING'
    last_updated: datetime


class OCPICdr(BaseModel):
    id: str
    start_date_time: datetime
    end_date_time: datetime
    cdr_token_uid: str
    auth_method: str
    currency: str
    total_cost: float
    total_energy: float
    last_updated: datetime
