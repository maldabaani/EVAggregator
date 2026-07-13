"""FastAPI app entrypoint for the API Gateway / BFF (Task 6.3): OAuth2/PKCE/
SSO token issuance (`evagg.gateway.app.build_gateway_app`), plus — only in
`app_mode=testing` — a dev-mode request forwarder
(`evagg.gateway.dev_forwarder`) that lets the portal's tariff-builder,
cost-dashboard, and command-panel pages reach `evagg.main` from a browser.

That forwarder is a stand-in for the real thing: Task 6.3 built OAuth token
issuance but never the actual "forwards authenticated calls to internal
services with a signed X-Tenant-Id header" half, and the portal has no
login flow to derive real trust from — an operator just types a tenant id
into a form. Trusting `X-Dev-Tenant-Id` as-is is only acceptable for local
dev/testing, so it's excluded entirely in `app_mode=production` rather than
shipped as a latent bypass.
"""

from __future__ import annotations

from evagg.core.config import settings
from evagg.core.observability import MetricsMiddleware, build_metrics_router, configure_logging
from evagg.gateway.app import build_gateway_app
from evagg.gateway.dev_forwarder import mount_dev_forwarder

configure_logging()

app = build_gateway_app()

if settings.app_mode == "testing":
    mount_dev_forwarder(
        app,
        settings.internal_services_base_url,
        path_prefixes=("/admin/tariffs", "/admin/teams", "/admin/chargers"),
    )

# Not `instrument_app`: that bundles in a Postgres/Redis/NATS `/healthz`
# check this app has no business depending on (it doesn't touch any of
# them) — `build_gateway_app()` already has its own plain `/healthz`.
app.add_middleware(MetricsMiddleware)
app.include_router(build_metrics_router())
