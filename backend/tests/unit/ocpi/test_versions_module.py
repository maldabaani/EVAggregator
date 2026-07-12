import uuid

import pytest

from evagg.ocpi.errors import OcpiError, OcpiErrorCode
from evagg.ocpi.partner_store import InMemoryPartnerRegistry, Partner
from evagg.ocpi.versions import authenticate_partner, negotiate_credentials

TENANT_ID = uuid.uuid4()


def _partner(**overrides) -> Partner:
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        party_id="XYZ",
        country_code="AE",
        token_a="token-a-secret",
        token_c=None,
        negotiated_version=None,
        status="pending",
    )
    defaults.update(overrides)
    return Partner(**defaults)


@pytest.mark.asyncio
async def test_negotiate_credentials_rejects_unsupported_version():
    registry = InMemoryPartnerRegistry([_partner()])

    with pytest.raises(OcpiError) as exc_info:
        await negotiate_credentials(registry, "token-a-secret", "9.9.9")

    assert exc_info.value.status_code == OcpiErrorCode.UNSUPPORTED_VERSION
    assert exc_info.value.http_status == 406


@pytest.mark.asyncio
async def test_negotiate_credentials_rejects_unknown_token_a():
    registry = InMemoryPartnerRegistry()

    with pytest.raises(OcpiError) as exc_info:
        await negotiate_credentials(registry, "not-a-real-token", "2.2.1")

    assert exc_info.value.status_code == OcpiErrorCode.UNKNOWN_TOKEN


@pytest.mark.asyncio
async def test_authenticate_partner_returns_partner_id_for_valid_token_c():
    partner = _partner(token_c="token-c-value", status="connected", negotiated_version="2.2.1")
    registry = InMemoryPartnerRegistry([partner])

    partner_id = await authenticate_partner(registry, "token-c-value")

    assert partner_id == partner.id


@pytest.mark.asyncio
async def test_authenticate_partner_rejects_unknown_token_c():
    registry = InMemoryPartnerRegistry()

    with pytest.raises(OcpiError) as exc_info:
        await authenticate_partner(registry, "not-a-real-token")

    assert exc_info.value.status_code == OcpiErrorCode.UNKNOWN_TOKEN
