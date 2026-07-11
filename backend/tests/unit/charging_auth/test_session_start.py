from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from evagg.billing.payment_methods import DIRECT_CARD, InMemoryPaymentMethodStore, PaymentMethod
from evagg.charging_auth.autocharge import InMemoryAutochargeMacStore
from evagg.charging_auth.plug_and_charge import InMemoryEmaidDriverMap, PlugAndChargeValidator
from evagg.charging_auth.qr_token import sign_qr_token
from evagg.charging_auth.session_start import SessionStartService

SECRET = "shared-gateway-secret"
TRUSTED_ISSUER = "https://oem-ca.example.com"


def _pem(key, private: bool) -> str:
    if private:
        return key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
    return key.public_bytes(
        encoding=serialization.Encoding.PEM, format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()


@pytest.mark.asyncio
async def test_all_three_methods_correctly_hook_up_default_payment_method():
    qr_driver_id = uuid.uuid4()
    autocharge_driver_id = uuid.uuid4()
    plug_and_charge_driver_id = uuid.uuid4()

    wallet_ids = {
        qr_driver_id: uuid.uuid4(),
        autocharge_driver_id: uuid.uuid4(),
        plug_and_charge_driver_id: uuid.uuid4(),
    }
    payment_methods = InMemoryPaymentMethodStore()
    expected_methods = {}
    for driver_id, wallet_id in wallet_ids.items():
        method = PaymentMethod(id=uuid.uuid4(), wallet_id=wallet_id, type=DIRECT_CARD, psp_token=f"tok-{driver_id}", is_default=True)
        payment_methods.add(method)
        expected_methods[driver_id] = method

    service = SessionStartService(payment_methods, wallet_id_for_driver=lambda driver_id: wallet_ids[driver_id])

    # QR
    qr_token = sign_qr_token("CP-001", 1, SECRET, issued_at=1_000_000.0)
    qr_result = await service.start_via_qr(qr_token, qr_driver_id, SECRET, now=1_000_010.0)
    assert qr_result.payment_method == expected_methods[qr_driver_id]

    # Autocharge
    mac_store = InMemoryAutochargeMacStore()
    mac_store.register("AA:BB:CC:DD:EE:FF", autocharge_driver_id)
    autocharge_result = await service.start_via_autocharge("AA:BB:CC:DD:EE:FF", "CP-002", mac_store)
    assert autocharge_result.payment_method == expected_methods[autocharge_driver_id]

    # Plug & Charge
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    emaid_map = InMemoryEmaidDriverMap()
    emaid_map.register("EMAID-XYZ", plug_and_charge_driver_id)
    validator = PlugAndChargeValidator({TRUSTED_ISSUER: _pem(private_key.public_key(), private=False)}, emaid_map)
    cert = jwt.encode(
        {"iss": TRUSTED_ISSUER, "emaid": "EMAID-XYZ", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        _pem(private_key, private=True),
        algorithm="RS256",
    )
    pnc_result = await service.start_via_plug_and_charge(cert, "CP-003", validator)
    assert pnc_result.payment_method == expected_methods[plug_and_charge_driver_id]

    # All three resolved a different driver's own default method, never mixed up.
    assert len({qr_result.payment_method.wallet_id, autocharge_result.payment_method.wallet_id, pnc_result.payment_method.wallet_id}) == 3
