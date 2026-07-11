"""FastAPI app entrypoint — the internal-services app.

Middleware order matters: `GatewaySignatureMiddleware` is added last so it
runs *outermost* (first), rejecting any `X-Tenant-Id` header that wasn't
signed by the gateway before `TenantContextMiddleware` ever reads it. The
public-facing gateway/BFF itself (OAuth2/PKCE, SSO, rate limiting — Task 6.3)
is a separate app, see `evagg.gateway.app`.
"""

from __future__ import annotations

from fastapi import FastAPI

from evagg.core.tenancy import TenantContextMiddleware
from evagg.gateway.middleware import GatewaySignatureMiddleware

app = FastAPI(title="EV Charging Aggregator Platform API", version="0.1.0")
app.add_middleware(TenantContextMiddleware)
app.add_middleware(GatewaySignatureMiddleware)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}
