"""The composition root — the one place that wires every independently
unit-tested service/store into a single set of running FastAPI apps.

Until now, every task in this backlog shipped a service and a `build_x_router`
factory, each covered by its own tests with in-memory or mocked dependencies,
but nothing ever constructed a real instance of all of them together and
mounted them on an app you could `uvicorn` and hit over HTTP. This module is
that missing assembly step.

**What `app_mode` does and doesn't control**

`app_mode=testing` wires every external, third-party integration (Stripe,
Electricity Maps, OCSP, OCPI partner push) to an in-process mock — no
account, API key, or network access required for any of them. `production`
swaps in the real adapters and calls `validate_production_config()` at
startup, which raises if any of their settings are still holding a
dev-only placeholder — it never silently falls back to a mock.

`app_mode` does **not** control persistence — `persistence_backend` does,
a separate axis. `persistence_backend=memory` (the default): every domain
store (tariffs, wallet ledger, OCPI locations/partners, OCPP chargers/
transactions/connectors/credentials/meter-values) is in-process and lost on
restart — true in both `app_mode`s, and still what cost-report rollups and
OCPI locations/partners use regardless of this setting (see below).
`persistence_backend=supabase`: tariffs, wallet, and the OCPP core
(chargers/connectors/transactions/credentials/meter-values) are backed by
real PostgREST calls against a Supabase project instead
(`evagg.persistence`) — see `docs/supabase/schema.sql` for the schema those
calls expect. OCPI locations/partners and cost-report rollups have no
Supabase-backed repository yet either way; that remains the largest
production-readiness gap — see `docs/production_readiness.md`.

Redis and NATS are real in both modes (they're free/local infra, not
third-party accounts), so presence, rate limiting, the carbon cache, and the
OCPP event bus all use their real backing service here regardless of
`persistence_backend`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import redis.asyncio as redis_asyncio

from evagg.billing.payment_methods import InMemoryPaymentMethodStore, PaymentMethodStore
from evagg.billing.payment_provider import PaymentProvider, StripePaymentProvider, StubPaymentProvider
from evagg.billing.tariffs import InMemoryTariffStore, InMemoryTenantCurrencyProvider, TariffService
from evagg.billing.wallet import InMemoryWalletLedgerStore, WalletService
from evagg.carbon.cache import CarbonCache, RedisCarbonCache
from evagg.carbon.provider import CarbonProvider, ElectricityMapsClient, MockCarbonProvider
from evagg.carbon.service import CarbonIntensityService
from evagg.carbon.zone_map import InMemoryCarbonZoneMap
from evagg.charging_auth.autocharge import InMemoryAutochargeMacStore
from evagg.charging_auth.plug_and_charge import (
    HttpOcspChecker,
    InMemoryEmaidDriverMap,
    InMemoryOcspChecker,
    OcspChecker,
    PlugAndChargeValidator,
)
from evagg.charging_auth.session_start import SessionStartService
from evagg.core.config import settings
from evagg.fleet.cost_report import CostReportService
from evagg.fleet.rollup import InMemoryRollupStore
from evagg.gateway.rate_limit import RateLimiter, RedisRateLimiter
from evagg.driver_app.reservations import DriverReservationService
from evagg.driver_app.vehicles import InMemoryVehicleStore, VehicleStore
from evagg.gateway.refresh_store import InMemoryRefreshTokenStore, RefreshTokenStore
from evagg.identity.driver_auth import DriverAccountStore, InMemoryDriverAccountStore
from evagg.ocpi.charging_preferences import ChargingPreferencesService, InMemoryChargingPreferencesStore
from evagg.ocpi.charging_profiles import (
    ChargingProfileService,
    InMemoryActiveChargingProfileStore,
    InMemorySessionChargerMap,
)
from evagg.ocpi.commands import OcpiCommandService
from evagg.ocpi.location_sync import HttpPartnerPushClient, InMemoryPartnerPushClient, PartnerPushClient
from evagg.ocpi.locations import InMemoryLocationRepository
from evagg.ocpi.partner_admin import InMemoryPriceListStore, InMemoryReconciliationResultStore, PriceListStore
from evagg.ocpi.partner_store import InMemoryPartnerRegistry
from evagg.ocpi.session_sync import HttpSessionPushClient, InMemorySessionPushClient, SessionPushClient
from evagg.ocpi.tariff_bridge import OcpiTariffCatalog
from evagg.ocpp_gateway.authorize import AuthStatus, Authorizer, InMemoryLocalIdTagStore, InMemoryRoamingTokenChecker
from evagg.ocpp_gateway.commands import (
    CommandLogStore,
    FirmwareUpdateStore,
    InMemoryCommandLogStore,
    InMemoryConnectorCapacityProvider,
    InMemoryFirmwareUpdateStore,
    RemoteCommandService,
)
from evagg.ocpp_gateway.connection_manager import ConnectionManager
from evagg.ocpp_gateway.connectors import ConnectorStore, InMemoryConnectorStore
from evagg.ocpp_gateway.credentials import CredentialVerifier, InMemoryCredentialVerifier
from evagg.ocpp_gateway.event_bus import NatsEventBus
from evagg.ocpp_gateway.bus_event_publisher import BusEventPublisher
from evagg.ocpp_gateway.message_handlers import OcppMessageHandlers
from evagg.ocpp_gateway.meter_values import InMemoryMeterValueSink, MeterValueBuffer, MeterValueSink
from evagg.ocpp_gateway.nats_command_transport import NatsCommandTransport, serve_commands
from evagg.ocpp_gateway.presence import PresenceRegistry, RedisPresenceRegistry
from evagg.ocpp_gateway.registration import ChargerRegistry, InMemoryChargerRegistry
from evagg.ocpp_gateway.transactions import InMemoryTransactionRepository, TransactionRepository
from evagg.ocpp_gateway.ws_app import LiveConnectionRegistry
from evagg.persistence.supabase_billing import SupabaseTariffStore, SupabaseWalletLedgerStore
from evagg.persistence.supabase_client import SupabaseRestClient
from evagg.persistence.supabase_ocpp import (
    SupabaseChargerRegistry,
    SupabaseConnectorStore,
    SupabaseCredentialVerifier,
    SupabaseMeterValueSink,
    SupabaseTransactionRepository,
)


class ProductionConfigError(Exception):
    """Raised at startup in app_mode=production when a required real value
    is still a dev-only placeholder."""


_PLACEHOLDER_MARKERS = ("dev_only", "dev-only", "replace_me", "example.com")


def _looks_like_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker in lowered for marker in _PLACEHOLDER_MARKERS)


def validate_production_config() -> None:
    """Fails fast rather than silently running with placeholder secrets
    against real third-party endpoints."""
    checks = {
        "stripe_api_key": settings.stripe_api_key,
        "stripe_webhook_secret": settings.stripe_webhook_secret,
        "electricity_maps_api_key": settings.electricity_maps_api_key,
        "ocsp_responder_url": settings.ocsp_responder_url,
        "ocpi_partner_push_base_url": settings.ocpi_partner_push_base_url,
        "ocpi_partner_push_token": settings.ocpi_partner_push_token,
        "jwt_signing_secret": settings.jwt_signing_secret,
        "gateway_trust_secret": settings.gateway_trust_secret,
    }
    placeholders = [name for name, value in checks.items() if _looks_like_placeholder(value)]
    if placeholders:
        raise ProductionConfigError(
            "app_mode=production but these settings still hold dev-only placeholder values: "
            + ", ".join(sorted(placeholders))
        )


@dataclass
class Services:
    """Every shared, process-lifetime service instance the apps mount
    routers against. Built once by `build_services()`, imported by
    `evagg.main`, `evagg.edge_app`, and `evagg.ocpp_gateway.ws_app`."""

    tariff_service: TariffService
    wallet_service: WalletService
    payment_method_store: PaymentMethodStore
    carbon_service: CarbonIntensityService
    cost_report_service: CostReportService
    session_start_service: SessionStartService
    plug_and_charge_validator: PlugAndChargeValidator
    autocharge_mac_store: InMemoryAutochargeMacStore

    location_repository: InMemoryLocationRepository
    partner_registry: InMemoryPartnerRegistry
    tariff_catalog: OcpiTariffCatalog
    charging_profile_service: ChargingProfileService
    session_charger_map: InMemorySessionChargerMap
    ocpi_command_service: OcpiCommandService
    driver_reservation_service: DriverReservationService
    charging_preferences_service: ChargingPreferencesService
    reconciliation_store: InMemoryReconciliationResultStore
    price_list_store: PriceListStore
    partner_push_client: PartnerPushClient
    session_push_client: SessionPushClient

    driver_account_store: DriverAccountStore
    driver_refresh_token_store: RefreshTokenStore
    vehicle_store: VehicleStore

    presence_registry: PresenceRegistry
    rate_limiter: RateLimiter
    # Typed as the concrete `NatsEventBus`, not the `EventBus` Protocol —
    # `startup_services`/`shutdown_services` call `connect()`/`close()`,
    # which are a `NatsEventBus`-specific lifecycle, not part of the
    # `EventBus` interface `BusEventPublisher` depends on.
    event_bus: NatsEventBus
    connection_manager: ConnectionManager
    message_handlers: OcppMessageHandlers
    credential_verifier: CredentialVerifier
    live_connections: LiveConnectionRegistry
    firmware_update_store: FirmwareUpdateStore
    node_id: str
    command_log_store: CommandLogStore
    command_transport: NatsCommandTransport
    remote_command_service: RemoteCommandService

    redis_client: redis_asyncio.Redis
    # Set by `startup_services` once `serve_commands` has subscribed — this
    # node can't receive outbound commands until then. `Any` because it's
    # the raw `nats.aio.client.Client` connection, imported lazily inside
    # `nats_command_transport` to keep that import optional everywhere else.
    _command_listener_nc: Any = field(default=None, repr=False)


def _build_payment_provider() -> PaymentProvider:
    if settings.app_mode == "production":
        return StripePaymentProvider(api_key=settings.stripe_api_key, base_url=settings.stripe_base_url)
    return StubPaymentProvider()


def _build_carbon_provider() -> CarbonProvider:
    if settings.app_mode == "production":
        return ElectricityMapsClient(
            api_key=settings.electricity_maps_api_key, base_url=settings.electricity_maps_base_url
        )
    return MockCarbonProvider()


def _build_ocsp_checker() -> OcspChecker:
    if settings.app_mode == "production":
        return HttpOcspChecker(responder_url=settings.ocsp_responder_url)
    return InMemoryOcspChecker()


def _build_partner_push_client() -> PartnerPushClient:
    if settings.app_mode == "production":
        return HttpPartnerPushClient(settings.ocpi_partner_push_base_url, settings.ocpi_partner_push_token)
    return InMemoryPartnerPushClient()


def _build_session_push_client() -> SessionPushClient:
    if settings.app_mode == "production":
        return HttpSessionPushClient(settings.ocpi_partner_push_base_url, settings.ocpi_partner_push_token)
    return InMemorySessionPushClient()


def _build_supabase_client() -> SupabaseRestClient:
    return SupabaseRestClient(settings.supabase_url, settings.supabase_api_key)


def build_services() -> Services:
    if settings.app_mode == "production":
        validate_production_config()

    redis_client = redis_asyncio.from_url(settings.redis_url)

    # --- Billing -----------------------------------------------------
    supabase_client = _build_supabase_client() if settings.persistence_backend == "supabase" else None
    if supabase_client is not None:
        tariff_service = TariffService(SupabaseTariffStore(supabase_client), InMemoryTenantCurrencyProvider())
        wallet_service = WalletService(SupabaseWalletLedgerStore(supabase_client), _build_payment_provider())
    else:
        tariff_service = TariffService(InMemoryTariffStore(), InMemoryTenantCurrencyProvider())
        wallet_service = WalletService(InMemoryWalletLedgerStore(), _build_payment_provider())
    payment_method_store: PaymentMethodStore = InMemoryPaymentMethodStore()

    # --- Carbon --------------------------------------------------------
    zone_map = InMemoryCarbonZoneMap()
    for country, area, provider_zone in (("AE", "DXB", "AE"), ("GB", "LON", "GB"), ("US", "CAISO", "US-CAL-CISO")):
        zone_map.set_mapping(country, area, provider_zone)
    carbon_cache: CarbonCache = RedisCarbonCache(redis_client)
    carbon_service = CarbonIntensityService(
        zone_map, _build_carbon_provider(), carbon_cache, ttl_seconds=settings.carbon_intensity_cache_ttl_seconds
    )

    # --- Fleet -----------------------------------------------------------
    cost_report_service = CostReportService(InMemoryRollupStore())

    # --- Charging auth ---------------------------------------------------
    autocharge_mac_store = InMemoryAutochargeMacStore()
    plug_and_charge_validator = PlugAndChargeValidator(
        trusted_ca_certs_pem=[], emaid_map=InMemoryEmaidDriverMap(), ocsp_checker=_build_ocsp_checker()
    )
    # session_start_service is constructed further below, once
    # remote_command_service and session_charger_map (both needed to
    # actually dispatch RemoteStartTransaction) exist.

    # --- OCPI --------------------------------------------------------
    location_repository = InMemoryLocationRepository()
    partner_registry = InMemoryPartnerRegistry()
    reconciliation_store = InMemoryReconciliationResultStore()
    price_list_store: PriceListStore = InMemoryPriceListStore()
    tariff_catalog = OcpiTariffCatalog(tariff_service, settings.ocpi_party_id, settings.ocpi_country_code)
    # Constructed but not yet wired to live event-bus consumption — see
    # module docstring's "what app_mode doesn't control" for location_sync/
    # session_sync's own separate pending-wiring note.
    partner_push_client = _build_partner_push_client()
    session_push_client = _build_session_push_client()

    driver_account_store: DriverAccountStore = InMemoryDriverAccountStore()
    driver_refresh_token_store: RefreshTokenStore = InMemoryRefreshTokenStore()
    vehicle_store: VehicleStore = InMemoryVehicleStore()

    # --- OCPP gateway (Redis/NATS are real in both modes) -----------------
    presence_registry: PresenceRegistry = RedisPresenceRegistry(redis_client)
    rate_limiter: RateLimiter = RedisRateLimiter(redis_client)
    event_bus = NatsEventBus(settings.nats_url)

    credential_verifier: CredentialVerifier
    charger_registry: ChargerRegistry
    transaction_repository: TransactionRepository
    connector_store: ConnectorStore
    meter_value_sink: MeterValueSink

    if supabase_client is not None:
        credential_verifier = SupabaseCredentialVerifier(supabase_client)
        charger_registry = SupabaseChargerRegistry(supabase_client)
        transaction_repository = SupabaseTransactionRepository(supabase_client)
        connector_store = SupabaseConnectorStore(supabase_client)
        meter_value_sink = SupabaseMeterValueSink(supabase_client)
        # Demo credential/id-tag seeding (below) needs a synchronous call —
        # SupabaseCredentialVerifier.set_credential is an HTTP request, so it
        # can't run here. Seed a demo charger's row + ws_credential_hash via
        # the SQL Editor or a one-off REST call if you want the same
        # end-to-end demo this session ran against local Postgres.
    else:
        in_memory_credential_verifier = InMemoryCredentialVerifier()
        if settings.app_mode == "testing":
            # A charge point with no seeded credential can never pass the WS
            # handshake — this is the one demo charger a local smoke test /
            # `ws_smoke_test.py` connects as. Production has no seed at all;
            # provisioning real per-charger credentials is part of the same
            # "no persistence layer yet" gap the module docstring calls out.
            in_memory_credential_verifier.set_credential("demo-charger-1", "demo-secret")
        credential_verifier = in_memory_credential_verifier
        charger_registry = InMemoryChargerRegistry()
        transaction_repository = InMemoryTransactionRepository()
        connector_store = InMemoryConnectorStore()
        meter_value_sink = InMemoryMeterValueSink()
    meter_value_buffer = MeterValueBuffer(sink=meter_value_sink)
    local_id_tag_store = InMemoryLocalIdTagStore()
    if settings.app_mode == "testing":
        # Same demo-seed rationale as the credential above — nothing else
        # ever authorizes an id_tag without this.
        local_id_tag_store.set_status("TAG-123", AuthStatus.ACCEPTED)
    authorizer = Authorizer(local_id_tag_store, InMemoryRoamingTokenChecker())
    event_publisher = BusEventPublisher(event_bus)
    node_id = f"ocpp-gw-{uuid.uuid4().hex[:8]}"
    live_connections = LiveConnectionRegistry()
    firmware_update_store: FirmwareUpdateStore = InMemoryFirmwareUpdateStore()
    command_log_store: CommandLogStore = InMemoryCommandLogStore()
    command_transport = NatsCommandTransport(settings.nats_url)
    remote_command_service = RemoteCommandService(
        presence=presence_registry,
        command_log=command_log_store,
        transport=command_transport,
        firmware_store=firmware_update_store,
    )
    session_charger_map = InMemorySessionChargerMap()
    charging_profile_service = ChargingProfileService(
        session_charger_map=session_charger_map,
        active_profile_store=InMemoryActiveChargingProfileStore(),
        command_service=remote_command_service,
        capacity_provider=InMemoryConnectorCapacityProvider(),
    )
    ocpi_command_service = OcpiCommandService(
        session_charger_map=session_charger_map,
        transaction_repository=transaction_repository,
        command_service=remote_command_service,
    )
    driver_reservation_service = DriverReservationService(ocpi_command_service)
    charging_preferences_service = ChargingPreferencesService(
        session_charger_map=session_charger_map,
        store=InMemoryChargingPreferencesStore(),
    )
    session_start_service = SessionStartService(
        payment_method_store=payment_method_store,
        # No driver->wallet mapping table exists yet (see module docstring on
        # persistence); identity mapping is a testing-mode simplification.
        wallet_id_for_driver=lambda driver_id: driver_id,
        command_service=remote_command_service,
        session_charger_map=session_charger_map,
        transaction_repository=transaction_repository,
    )

    connection_manager = ConnectionManager(
        presence=presence_registry,
        credentials=credential_verifier,
        transactions=transaction_repository,
        charger_registry=charger_registry,
        events=event_publisher,
        node_id=node_id,
        default_heartbeat_interval_seconds=settings.heartbeat_default_interval_seconds,
    )
    message_handlers = OcppMessageHandlers(
        charger_registry=charger_registry,
        connector_store=connector_store,
        authorizer=authorizer,
        transaction_repository=transaction_repository,
        meter_value_buffer=meter_value_buffer,
        events=event_publisher,
        firmware_update_store=firmware_update_store,
    )

    return Services(
        tariff_service=tariff_service,
        wallet_service=wallet_service,
        payment_method_store=payment_method_store,
        carbon_service=carbon_service,
        cost_report_service=cost_report_service,
        session_start_service=session_start_service,
        plug_and_charge_validator=plug_and_charge_validator,
        autocharge_mac_store=autocharge_mac_store,
        location_repository=location_repository,
        partner_registry=partner_registry,
        tariff_catalog=tariff_catalog,
        charging_profile_service=charging_profile_service,
        session_charger_map=session_charger_map,
        ocpi_command_service=ocpi_command_service,
        driver_reservation_service=driver_reservation_service,
        charging_preferences_service=charging_preferences_service,
        reconciliation_store=reconciliation_store,
        price_list_store=price_list_store,
        partner_push_client=partner_push_client,
        session_push_client=session_push_client,
        driver_account_store=driver_account_store,
        driver_refresh_token_store=driver_refresh_token_store,
        vehicle_store=vehicle_store,
        presence_registry=presence_registry,
        rate_limiter=rate_limiter,
        event_bus=event_bus,
        connection_manager=connection_manager,
        message_handlers=message_handlers,
        credential_verifier=credential_verifier,
        live_connections=live_connections,
        firmware_update_store=firmware_update_store,
        node_id=node_id,
        command_log_store=command_log_store,
        command_transport=command_transport,
        remote_command_service=remote_command_service,
        redis_client=redis_client,
    )


async def startup_services(services: Services) -> None:
    """`NatsEventBus.connect()` provisions the JetStream stream and must run
    before the first publish — call from each app's FastAPI lifespan.
    `command_transport.connect()` and `serve_commands()` bring up the two
    halves of the outbound-command channel: this process can now issue
    commands (`RemoteCommandService.send_command`), and this node's live
    WebSocket connections can now receive them, addressed via `node_id`."""
    await services.event_bus.connect()
    await services.command_transport.connect()
    services._command_listener_nc = await serve_commands(
        settings.nats_url, services.node_id, services.live_connections
    )


async def shutdown_services(services: Services) -> None:
    await services.event_bus.close()
    await services.command_transport.close()
    if services._command_listener_nc is not None:
        await services._command_listener_nc.close()
    await services.redis_client.aclose()
