"""Task 5.2 — regardless of which of the three methods started the session,
once it's confirmed the session ties to the driver's default payment method
(Task 3.3). One shared helper (`_resolve_payment_method`) is what all three
public entrypoints call, rather than three copies of the same lookup.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from evagg.billing.payment_methods import PaymentMethod, PaymentMethodStore
from evagg.charging_auth.autocharge import AutochargeMacStore, synthesize_id_tag_for_mac
from evagg.charging_auth.plug_and_charge import PlugAndChargeError, PlugAndChargeValidator
from evagg.charging_auth.qr_token import QrTokenError, verify_qr_token


class SessionStartError(Exception):
    pass


@dataclass(frozen=True)
class SessionStartResult:
    driver_id: uuid.UUID
    charger_id: str
    connector_id: int | None
    id_tag: str | None
    payment_method: PaymentMethod | None
    auth_method: str  # 'qr' | 'autocharge' | 'plug_and_charge'


class SessionStartService:
    def __init__(
        self,
        payment_method_store: PaymentMethodStore,
        wallet_id_for_driver: Callable[[uuid.UUID], uuid.UUID],
    ) -> None:
        self._payment_method_store = payment_method_store
        self._wallet_id_for_driver = wallet_id_for_driver

    async def _resolve_payment_method(self, driver_id: uuid.UUID) -> PaymentMethod | None:
        wallet_id = self._wallet_id_for_driver(driver_id)
        return await self._payment_method_store.get_default(wallet_id)

    async def start_via_qr(
        self, token: str, driver_id: uuid.UUID, secret: str, now: float | None = None
    ) -> SessionStartResult:
        try:
            payload = verify_qr_token(token, secret, now=now)
        except QrTokenError as exc:
            raise SessionStartError(str(exc)) from exc

        payment_method = await self._resolve_payment_method(driver_id)
        return SessionStartResult(
            driver_id=driver_id, charger_id=payload.charger_id, connector_id=payload.connector_id,
            id_tag=None, payment_method=payment_method, auth_method="qr",
        )

    async def start_via_autocharge(
        self, mac_address: str, charger_id: str, mac_store: AutochargeMacStore
    ) -> SessionStartResult:
        driver_id = await mac_store.get_driver_id_for_mac(mac_address)
        if driver_id is None:
            raise SessionStartError(f"no driver registered for MAC address {mac_address}")

        payment_method = await self._resolve_payment_method(driver_id)
        return SessionStartResult(
            driver_id=driver_id, charger_id=charger_id, connector_id=None,
            id_tag=synthesize_id_tag_for_mac(mac_address), payment_method=payment_method, auth_method="autocharge",
        )

    async def start_via_plug_and_charge(
        self, cert_token: str, charger_id: str, validator: PlugAndChargeValidator
    ) -> SessionStartResult:
        try:
            driver_id = await validator.resolve_driver_from_cert(cert_token)
        except PlugAndChargeError as exc:
            raise SessionStartError(str(exc)) from exc

        payment_method = await self._resolve_payment_method(driver_id)
        return SessionStartResult(
            driver_id=driver_id, charger_id=charger_id, connector_id=None,
            id_tag=None, payment_method=payment_method, auth_method="plug_and_charge",
        )
