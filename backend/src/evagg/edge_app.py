"""FastAPI app entrypoint — the "edge" app for trust boundaries that are NOT
tenant-header-authenticated: OCPI (roaming partners call this directly,
authenticated by their own OCPI bearer token), the OCPP WebSocket (charge
points connect directly, authenticated by their own per-charger credential
in the handshake), and driver signup/login (a driver has no tenant yet at
that point — auth *establishes* their session, so it can't sit behind a
tenant-header check). None of these belong on `evagg.main`, which requires
a gateway-signed `X-Tenant-Id` header no partner, charge point, or
unauthenticated driver ever sends.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from evagg.composition import build_services, shutdown_services, startup_services
from evagg.core.observability import configure_logging, instrument_app
from evagg.identity.driver_auth_router import build_driver_auth_router
from evagg.ocpi.admin_router import build_admin_router
from evagg.ocpi.router import build_ocpi_router, register_ocpi_exception_handlers
from evagg.ocpp_gateway.ws_app import build_ocpp_ws_router

configure_logging()
services = build_services()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_services(services)
    try:
        yield
    finally:
        await shutdown_services(services)


app = FastAPI(title="EV Charging Aggregator Platform Edge Services", version="0.1.0", lifespan=lifespan)
register_ocpi_exception_handlers(app)


async def _partner_registry():
    return services.partner_registry


async def _location_repository():
    return services.location_repository


async def _reconciliation_store():
    return services.reconciliation_store


async def _tariff_catalog():
    return services.tariff_catalog


async def _charging_profile_service():
    return services.charging_profile_service


async def _session_charger_map():
    return services.session_charger_map


async def _ocpi_command_service():
    return services.ocpi_command_service


async def _charging_preferences_service():
    return services.charging_preferences_service


async def _price_list_store():
    return services.price_list_store


async def _driver_account_store():
    return services.driver_account_store


async def _driver_refresh_token_store():
    return services.driver_refresh_token_store


app.include_router(build_driver_auth_router(_driver_account_store, _driver_refresh_token_store))
app.include_router(
    build_ocpi_router(
        _partner_registry, _location_repository, _tariff_catalog, _charging_profile_service, _ocpi_command_service,
        _charging_preferences_service,
    )
)
app.include_router(
    build_admin_router(_partner_registry, _reconciliation_store, _session_charger_map, _price_list_store)
)
app.include_router(
    build_ocpp_ws_router(services.connection_manager, services.message_handlers, services.live_connections)
)

instrument_app(app, services.redis_client)
