"""Task 6.3 — rejects any `X-Tenant-Id` header not signed by the gateway.

Runs *outside* (before) `evagg.core.tenancy.TenantContextMiddleware`: a
request that fails this check never even gets to populate the tenant context,
closing the "client spoofs the tenant header directly" gap called out in the
acceptance criteria.
"""

from __future__ import annotations

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from evagg.core.tenancy import EXEMPT_PATHS, TENANT_HEADER
from evagg.gateway.trust import SIGNATURE_HEADER, verify_tenant_signature


def _problem_response(status: int, title: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status},
        media_type="application/problem+json",
    )


class GatewaySignatureMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope["path"]
        if path in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        headers = {k.decode().lower(): v.decode() for k, v in scope["headers"]}
        raw_tenant = headers.get(TENANT_HEADER)
        if raw_tenant is None:
            # No tenant header at all — TenantContextMiddleware downstream
            # will reject this with its own 401; nothing to verify here.
            await self.app(scope, receive, send)
            return

        signature = headers.get(SIGNATURE_HEADER)
        if not signature or not verify_tenant_signature(raw_tenant, signature):
            response = _problem_response(403, "untrusted tenant header")
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
