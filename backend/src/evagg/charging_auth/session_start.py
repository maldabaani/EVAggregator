"""Task 5.2 — regardless of which of the four methods started the session,
once it's confirmed the session ties to the driver's default payment method
(Task 3.3). One shared helper (`_resolve_payment_method`) is what all four
public entrypoints call, rather than four copies of the same lookup.

Beyond resolving *who* is starting a session and *how they'll pay*, this
also actually dispatches the OCPP `RemoteStartTransaction` command and
records a session_id -> charger binding (mirroring
`evagg.ocpi.commands.OcpiCommandService.start_session`'s exact pattern) —
resolving auth without ever telling the charger to start would make
"start charging" a no-op that only ever looked like it worked.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Callable

from evagg.billing.payment_methods import PaymentMethod, PaymentMethodStore
from evagg.charging_auth.autocharge import AutochargeMacStore, synthesize_id_tag_for_mac
from evagg.charging_auth.plug_and_charge import PlugAndChargeError, PlugAndChargeValidator
from evagg.charging_auth.qr_token import QrTokenError, verify_qr_token
from evagg.ocpi.charging_profiles import InMemorySessionChargerMap, SessionChargerBinding
from evagg.ocpp_gateway.commands import ChargerOfflineError, CommandStatus, RemoteCommandService


class SessionStartError(Exception):
    pass


@dataclass(frozen=True)
class SessionStartResult:
    session_id: str
    driver_id: uuid.UUID
    charger_id: str
    connector_id: int | None
    id_tag: str
    payment_method: PaymentMethod | None
    auth_method: str  # 'qr' | 'autocharge' | 'plug_and_charge' | 'app'


def synthesize_id_tag_for_driver(driver_id: uuid.UUID) -> str:
    return f"DRIVER:{driver_id}"


class SessionStartService:
    def __init__(
        self,
        payment_method_store: PaymentMethodStore,
        wallet_id_for_driver: Callable[[uuid.UUID], uuid.UUID],
        command_service: RemoteCommandService,
        session_charger_map: InMemorySessionChargerMap,
    ) -> None:
        self._payment_method_store = payment_method_store
        self._wallet_id_for_driver = wallet_id_for_driver
        self._command_service = command_service
        self._session_charger_map = session_charger_map

    async def _resolve_payment_method(self, driver_id: uuid.UUID) -> PaymentMethod | None:
        wallet_id = self._wallet_id_for_driver(driver_id)
        return await self._payment_method_store.get_default(wallet_id)

    async def _dispatch_remote_start(
        self,
        driver_id: uuid.UUID,
        tenant_id: uuid.UUID,
        charger_id: str,
        connector_id: int | None,
        id_tag: str,
        auth_method: str,
    ) -> SessionStartResult:
        payload: dict[str, object] = {"idTag": id_tag}
        if connector_id is not None:
            payload["connectorId"] = connector_id
        try:
            result = await self._command_service.send_command(charger_id, tenant_id, "RemoteStartTransaction", payload)
        except ChargerOfflineError as exc:
            raise SessionStartError(str(exc)) from exc
        if result.status != CommandStatus.ACCEPTED:
            raise SessionStartError(f"charge point responded {result.status.value}")

        session_id = str(uuid.uuid4())
        self._session_charger_map.set_binding(
            session_id, SessionChargerBinding(charger_id, tenant_id, connector_id or 1)
        )
        payment_method = await self._resolve_payment_method(driver_id)
        return SessionStartResult(
            session_id=session_id, driver_id=driver_id, charger_id=charger_id, connector_id=connector_id,
            id_tag=id_tag, payment_method=payment_method, auth_method=auth_method,
        )

    async def start_via_qr(
        self, token: str, driver_id: uuid.UUID, secret: str, tenant_id: uuid.UUID, now: float | None = None
    ) -> SessionStartResult:
        try:
            payload = verify_qr_token(token, secret, now=now)
        except QrTokenError as exc:
            raise SessionStartError(str(exc)) from exc

        return await self._dispatch_remote_start(
            driver_id, tenant_id, payload.charger_id, payload.connector_id,
            synthesize_id_tag_for_driver(driver_id), "qr",
        )

    async def start_via_autocharge(
        self, mac_address: str, charger_id: str, tenant_id: uuid.UUID, mac_store: AutochargeMacStore
    ) -> SessionStartResult:
        driver_id = await mac_store.get_driver_id_for_mac(mac_address)
        if driver_id is None:
            raise SessionStartError(f"no driver registered for MAC address {mac_address}")

        return await self._dispatch_remote_start(
            driver_id, tenant_id, charger_id, None, synthesize_id_tag_for_mac(mac_address), "autocharge",
        )

    async def start_via_plug_and_charge(
        self, cert_token: str, charger_id: str, tenant_id: uuid.UUID, validator: PlugAndChargeValidator
    ) -> SessionStartResult:
        try:
            driver_id = await validator.resolve_driver_from_cert(cert_token)
        except PlugAndChargeError as exc:
            raise SessionStartError(str(exc)) from exc

        return await self._dispatch_remote_start(
            driver_id, tenant_id, charger_id, None, synthesize_id_tag_for_driver(driver_id), "plug_and_charge",
        )

    async def start_via_app(
        self, charger_id: str, connector_id: int, driver_id: uuid.UUID, tenant_id: uuid.UUID
    ) -> SessionStartResult:
        """The mobile app's own "Start Charging" button: the driver is
        already authenticated (their JWT resolved `driver_id`/`tenant_id`
        before this is ever called — see
        `evagg.driver_app.session_start_forwarder`), so there's no separate
        token/secret to verify, unlike the QR flow's physically-displayed
        code."""
        return await self._dispatch_remote_start(
            driver_id, tenant_id, charger_id, connector_id, synthesize_id_tag_for_driver(driver_id), "app",
        )
