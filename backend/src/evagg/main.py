"""FastAPI app entrypoint — the internal, tenant-scoped services app: billing
(tariffs, wallet + Stripe webhook), carbon intensity, fleet cost reports,
charging-session start, and OCPP presence reads. Everything here sits behind
the two trust-boundary middlewares below and is meant to be called by
`evagg.gateway.app` (the BFF), never directly by a client.

OCPI (partner-facing) and the OCPP WebSocket (charge-point-facing) are
deliberately NOT mounted here — they have their own auth (OCPI bearer
tokens, per-charger WS credentials), not a tenant header, so they run on the
separate `evagg.edge_app` instead. See that module's docstring.

Middleware order matters: `GatewaySignatureMiddleware` is added last so it
runs *outermost* (first), rejecting any `X-Tenant-Id` header that wasn't
signed by the gateway before `TenantContextMiddleware` ever reads it.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from evagg.billing.stripe_webhook import build_stripe_webhook_router
from evagg.billing.tariff_router import build_tariff_router
from evagg.billing.wallet_router import build_wallet_router
from evagg.carbon.router import build_carbon_router
from evagg.charging_auth.session_start_router import build_session_router, build_session_start_router
from evagg.composition import build_services, shutdown_services, startup_services
from evagg.core.config import settings
from evagg.core.observability import configure_logging, instrument_app
from evagg.core.tenancy import TenantContextMiddleware
from evagg.fleet.cost_report_router import build_cost_report_router
from evagg.gateway.middleware import GatewaySignatureMiddleware
from evagg.ocpp_gateway.command_router import build_command_router
from evagg.ocpp_gateway.presence_api import build_presence_router

configure_logging()
services = build_services()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await startup_services(services)
    try:
        yield
    finally:
        await shutdown_services(services)


app = FastAPI(title="EV Charging Aggregator Platform API", version="0.1.0", lifespan=lifespan)


async def _tariff_service():
    return services.tariff_service


async def _wallet_service():
    return services.wallet_service


async def _carbon_service():
    return services.carbon_service


async def _cost_report_service():
    return services.cost_report_service


async def _session_start_service():
    return services.session_start_service


async def _autocharge_mac_store():
    return services.autocharge_mac_store


async def _plug_and_charge_validator():
    return services.plug_and_charge_validator


async def _presence_registry():
    return services.presence_registry


async def _remote_command_service():
    return services.remote_command_service


async def _command_log_store():
    return services.command_log_store


app.include_router(build_tariff_router(_tariff_service))
app.include_router(build_wallet_router(_wallet_service))
app.include_router(build_stripe_webhook_router(_wallet_service, settings.stripe_webhook_secret))
app.include_router(build_carbon_router(_carbon_service))
app.include_router(build_cost_report_router(_cost_report_service))
app.include_router(
    build_session_start_router(_session_start_service, _autocharge_mac_store, _plug_and_charge_validator)
)
app.include_router(build_session_router(_session_start_service))
app.include_router(build_presence_router(_presence_registry))
app.include_router(build_command_router(_remote_command_service, _command_log_store))

app.add_middleware(TenantContextMiddleware)
app.add_middleware(GatewaySignatureMiddleware)

instrument_app(app, services.redis_client)
