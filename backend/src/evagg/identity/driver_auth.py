"""Driver-facing signup/login — the auth boundary the mobile app actually
authenticates through, as opposed to the gateway's portal-oriented
OAuth2/PKCE/SSO flow (`evagg.gateway.app`) or an OCPI partner's bearer token.

Password hashing reuses the same PBKDF2-HMAC scheme already used for OCPP
charger credentials (`evagg.ocpp_gateway.credentials`) rather than
introducing a second hashing primitive.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol

from evagg.ocpp_gateway.credentials import hash_credential, verify_credential

# Direct-to-consumer drivers (not part of any B2B fleet) are tenant-scoped
# to this reserved id, matching the convention documented on
# `evagg.models.identity.Driver`.
PLATFORM_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


@dataclass
class DriverAccount:
    id: uuid.UUID
    tenant_id: uuid.UUID
    email: str
    full_name: str
    password_hash: str


class EmailAlreadyRegisteredError(Exception):
    pass


class DriverAccountStore(Protocol):
    async def create(
        self, email: str, full_name: str, password: str, tenant_id: uuid.UUID = PLATFORM_TENANT_ID
    ) -> DriverAccount: ...

    async def find_by_email(self, email: str) -> DriverAccount | None: ...

    async def get(self, driver_id: uuid.UUID) -> DriverAccount | None: ...


class InMemoryDriverAccountStore:
    def __init__(self) -> None:
        self._by_id: dict[uuid.UUID, DriverAccount] = {}
        self._id_by_email: dict[str, uuid.UUID] = {}

    async def create(
        self, email: str, full_name: str, password: str, tenant_id: uuid.UUID = PLATFORM_TENANT_ID
    ) -> DriverAccount:
        normalized_email = email.strip().lower()
        if normalized_email in self._id_by_email:
            raise EmailAlreadyRegisteredError(email)
        account = DriverAccount(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            email=normalized_email,
            full_name=full_name,
            password_hash=hash_credential(password),
        )
        self._by_id[account.id] = account
        self._id_by_email[normalized_email] = account.id
        return account

    async def find_by_email(self, email: str) -> DriverAccount | None:
        driver_id = self._id_by_email.get(email.strip().lower())
        return self._by_id.get(driver_id) if driver_id is not None else None

    async def get(self, driver_id: uuid.UUID) -> DriverAccount | None:
        return self._by_id.get(driver_id)


def verify_password(account: DriverAccount, password: str) -> bool:
    return verify_credential(password, account.password_hash)
