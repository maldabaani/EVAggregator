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

`start_via_autocharge`/`start_via_plug_and_charge` also check the
driver's own opt-in flag (`Vehicle.plug_and_charge_enabled`, toggled from
the mobile app's "My Cars" screen) before dispatching — otherwise that
toggle would have no actual effect on whether an automatic session-start
is allowed to happen at all.

`stop_session` awards rewards points on every successful stop
(`evagg.driver_app.rewards`) — a completed session is the one place in
this flow that unambiguously represents "the driver actually charged
here," so it's the natural (and only) point to award from. It also
records a `CompletedSession` (`evagg.driver_app.session_history`) from
that same live snapshot, the only persistent record of a finished
session anywhere in this system — `usage_insights.py` reads it back.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from evagg.billing.payment_methods import PaymentMethod, PaymentMethodStore
from evagg.billing.tariffs import TariffService
from evagg.charging_auth.autocharge import AutochargeMacStore, synthesize_id_tag_for_mac
from evagg.charging_auth.plug_and_charge import PlugAndChargeError, PlugAndChargeValidator
from evagg.charging_auth.qr_token import QrTokenError, verify_qr_token
from evagg.driver_app.rewards import RewardsService
from evagg.driver_app.session_history import CompletedSession, SessionHistoryStore
from evagg.driver_app.vehicles import VehicleStore
from evagg.ocpi.charging_profiles import InMemorySessionChargerMap, SessionChargerBinding
from evagg.ocpp_gateway.commands import ChargerOfflineError, CommandStatus, RemoteCommandService
from evagg.ocpp_gateway.live_meter_readings import LatestMeterReadingStore
from evagg.ocpp_gateway.transactions import ActiveTransaction, TransactionRepository

ENERGY_MEASURAND = "Energy.Active.Import.Register"
POWER_MEASURAND = "Power.Active.Import"
# Used only when the tenant has no tariff to price the live estimate
# against — matches the mobile app's own existing AED convention
# (wallet_screen.dart/insights_screen.dart) for the same reason: the
# backend has nothing else to report a currency as in that case.
DEFAULT_LIVE_STATUS_CURRENCY = "AED"


class SessionStartError(Exception):
    pass


class SessionNotFoundError(Exception):
    """Raised for an unknown session_id, or one that belongs to a
    different driver — the two are deliberately indistinguishable to the
    caller, so a driver probing random session ids can't learn whether one
    happens to exist."""


@dataclass(frozen=True)
class SessionStartResult:
    session_id: str
    driver_id: uuid.UUID
    charger_id: str
    connector_id: int | None
    id_tag: str
    payment_method: PaymentMethod | None
    auth_method: str  # 'qr' | 'autocharge' | 'plug_and_charge' | 'app'


@dataclass(frozen=True)
class SessionStatus:
    charger_id: str
    connector_id: int
    active: bool


@dataclass(frozen=True)
class LiveSessionStatus:
    status: str  # 'charging' | 'finished'
    energy_kwh: float
    power_kw: float
    cost_minor_units: int
    currency: str
    started_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class _LiveSnapshot:
    energy_kwh: float
    power_kw: float
    cost_minor_units: int
    currency: str
    started_at: datetime
    updated_at: datetime


def synthesize_id_tag_for_driver(driver_id: uuid.UUID) -> str:
    return f"DRIVER:{driver_id}"


class SessionStartService:
    def __init__(
        self,
        payment_method_store: PaymentMethodStore,
        wallet_id_for_driver: Callable[[uuid.UUID], uuid.UUID],
        command_service: RemoteCommandService,
        session_charger_map: InMemorySessionChargerMap,
        transaction_repository: TransactionRepository,
        vehicle_store: VehicleStore,
        rewards_service: RewardsService,
        latest_meter_readings: LatestMeterReadingStore,
        tariff_service: TariffService,
        session_history_store: SessionHistoryStore,
    ) -> None:
        self._payment_method_store = payment_method_store
        self._wallet_id_for_driver = wallet_id_for_driver
        self._command_service = command_service
        self._session_charger_map = session_charger_map
        self._transaction_repository = transaction_repository
        self._vehicle_store = vehicle_store
        self._rewards_service = rewards_service
        self._latest_meter_readings = latest_meter_readings
        self._tariff_service = tariff_service
        self._session_history_store = session_history_store
        # Tracks which driver started each session, regardless of auth
        # method, so status/stop can refuse a driver who isn't the one who
        # started it — without this, guessing or observing another
        # driver's session_id would let you stop their charging session.
        self._session_owner: dict[str, uuid.UUID] = {}

    async def _resolve_payment_method(self, driver_id: uuid.UUID) -> PaymentMethod | None:
        wallet_id = self._wallet_id_for_driver(driver_id)
        return await self._payment_method_store.get_default(wallet_id)

    async def _require_plug_and_charge_opt_in(self, driver_id: uuid.UUID) -> None:
        # AutochargeMacStore/PlugAndChargeValidator resolve only a driver_id
        # from the MAC address/certificate, not which specific vehicle it
        # belongs to — so this checks whether *any* of the driver's
        # vehicles has opted in, the most it can verify without a
        # MAC/EMAID-to-vehicle mapping that doesn't exist yet.
        vehicles = await self._vehicle_store.list_for_driver(driver_id)
        if not any(v.plug_and_charge_enabled for v in vehicles):
            raise SessionStartError("plug and charge is not enabled for this driver's vehicles")

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
        self._session_owner[session_id] = driver_id
        payment_method = await self._resolve_payment_method(driver_id)
        return SessionStartResult(
            session_id=session_id, driver_id=driver_id, charger_id=charger_id, connector_id=connector_id,
            id_tag=id_tag, payment_method=payment_method, auth_method=auth_method,
        )

    async def _owned_binding(self, session_id: str, driver_id: uuid.UUID) -> SessionChargerBinding:
        if self._session_owner.get(session_id) != driver_id:
            raise SessionNotFoundError(session_id)
        binding = await self._session_charger_map.get_charger_for_session(session_id)
        if binding is None:
            raise SessionNotFoundError(session_id)
        return binding

    async def get_session_status(self, session_id: str, driver_id: uuid.UUID) -> SessionStatus:
        binding = await self._owned_binding(session_id, driver_id)
        active_transaction = await self._transaction_repository.get_active_transaction(binding.charger_id)
        return SessionStatus(
            charger_id=binding.charger_id, connector_id=binding.connector_id, active=active_transaction is not None
        )

    async def get_live_status(self, session_id: str, driver_id: uuid.UUID, tenant_id: uuid.UUID) -> LiveSessionStatus:
        """Real energy (kWh) and power (kW) come from the charger's own
        MeterValues, not a fabricated estimate. Cost is a live *estimate*
        only: there's no charger-to-tariff assignment anywhere in this
        system yet (see `evagg.billing.pricing_resolution`'s override
        chain, which resolves a tariff *given* a site/operator id — nothing
        maps a charger to one) — so this uses the tenant's first tariff, if
        it has any, the same kind of documented stand-in as
        `wallet_id_for_driver` above. The definitive settled cost still
        comes from `SessionBillingService.charge_session`'s caller-supplied
        amount, not from this estimate.
        """
        binding = await self._owned_binding(session_id, driver_id)
        active_transaction = await self._transaction_repository.get_active_transaction(binding.charger_id)

        now = datetime.now(timezone.utc)
        if active_transaction is None:
            # No signal for exactly when it stopped is kept here — this
            # only reports "it's over", matching `SessionStatus.finished`
            # on the mobile side, which has no separate "just now" state.
            return LiveSessionStatus(
                status="finished", energy_kwh=0.0, power_kw=0.0, cost_minor_units=0,
                currency=DEFAULT_LIVE_STATUS_CURRENCY, started_at=now, updated_at=now,
            )

        snapshot = await self._compute_live_snapshot(active_transaction, tenant_id, now)
        return LiveSessionStatus(
            status="charging", energy_kwh=snapshot.energy_kwh, power_kw=snapshot.power_kw,
            cost_minor_units=snapshot.cost_minor_units, currency=snapshot.currency,
            started_at=snapshot.started_at, updated_at=snapshot.updated_at,
        )

    async def _compute_live_snapshot(
        self, active_transaction: ActiveTransaction, tenant_id: uuid.UUID, now: datetime
    ) -> _LiveSnapshot:
        """Shared by `get_live_status` and `stop_session` (for the
        completed-session record it writes) — the definitive settled cost
        still comes from `SessionBillingService.charge_session`'s
        caller-supplied amount, not from this estimate, in both cases."""
        transaction_id = active_transaction.id
        energy_reading = await self._latest_meter_readings.get_latest(transaction_id, ENERGY_MEASURAND)
        power_reading = await self._latest_meter_readings.get_latest(transaction_id, POWER_MEASURAND)
        energy_kwh = energy_reading.value if energy_reading is not None else 0.0
        power_kw = power_reading.value if power_reading is not None else 0.0
        updated_at = max((r.ts for r in (energy_reading, power_reading) if r is not None), default=now)

        started_at = active_transaction.start_timestamp
        duration_minutes = max(0.0, (now - started_at).total_seconds() / 60)

        cost_minor_units = 0
        currency = DEFAULT_LIVE_STATUS_CURRENCY
        tenant_tariffs = [t for t in await self._tariff_service.list_all_tariffs() if t.tenant_id == tenant_id]
        if tenant_tariffs:
            tariff = tenant_tariffs[0]
            cost_minor_units = await self._tariff_service.preview(tariff.id, duration_minutes, energy_kwh)
            currency = tariff.currency

        return _LiveSnapshot(
            energy_kwh=energy_kwh, power_kw=power_kw, cost_minor_units=cost_minor_units,
            currency=currency, started_at=started_at, updated_at=updated_at,
        )

    async def stop_session(self, session_id: str, driver_id: uuid.UUID, tenant_id: uuid.UUID) -> None:
        binding = await self._owned_binding(session_id, driver_id)
        active_transaction = await self._transaction_repository.get_active_transaction(binding.charger_id)
        if active_transaction is None:
            raise SessionStartError("no active transaction on this charger")

        now = datetime.now(timezone.utc)
        snapshot = await self._compute_live_snapshot(active_transaction, tenant_id, now)

        try:
            result = await self._command_service.send_command(
                binding.charger_id, tenant_id, "RemoteStopTransaction",
                {"transactionId": str(active_transaction.id)},
            )
        except ChargerOfflineError as exc:
            raise SessionStartError(str(exc)) from exc
        if result.status != CommandStatus.ACCEPTED:
            raise SessionStartError(f"charge point responded {result.status.value}")

        await self._rewards_service.award_for_completed_session(driver_id)
        await self._session_history_store.record(
            CompletedSession(
                session_id=session_id, driver_id=driver_id, charger_id=binding.charger_id,
                started_at=active_transaction.start_timestamp, ended_at=now,
                energy_kwh=snapshot.energy_kwh, cost_minor_units=snapshot.cost_minor_units,
                currency=snapshot.currency,
            )
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
        await self._require_plug_and_charge_opt_in(driver_id)

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
        await self._require_plug_and_charge_opt_in(driver_id)

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
