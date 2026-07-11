"""Task 4.1 — request-scoped tenant context.

The API Gateway (Task 6.3) validates the caller's JWT and forwards the
resolved tenant as a trusted internal header; internal services trust that
header only because it arrives over the gateway's private network path, never
from a client-supplied value directly. This module resolves that header into a
context var, and `bind_tenant_context` stamps it onto the Postgres session via
`set_config('app.current_tenant', ..., true)` (transaction-scoped, so it can
never leak across a pooled connection) before any query runs — RLS policies
key off that setting and fail closed (zero rows) when it's unset.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextvars import ContextVar

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

logger = logging.getLogger("evagg.tenancy")

TENANT_HEADER = "x-tenant-id"

# Paths that must be reachable without a resolved tenant (health checks,
# generated API docs). Everything else fails closed.
EXEMPT_PATHS: frozenset[str] = frozenset({"/healthz", "/docs", "/openapi.json", "/redoc"})

current_tenant_id: ContextVar[uuid.UUID | None] = ContextVar("current_tenant_id", default=None)


def _problem_response(status: int, title: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"type": "about:blank", "title": title, "status": status},
        media_type="application/problem+json",
    )


class TenantContextMiddleware:
    """Rejects any request with no resolvable tenant before it reaches a
    route handler or touches the database — fail closed, not open."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        if request.url.path in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        raw_tenant = request.headers.get(TENANT_HEADER)
        if not raw_tenant:
            response = _problem_response(401, "tenant context required")
            await response(scope, receive, send)
            return

        try:
            tenant_id = uuid.UUID(raw_tenant)
        except ValueError:
            response = _problem_response(401, "invalid tenant context")
            await response(scope, receive, send)
            return

        token = current_tenant_id.set(tenant_id)
        try:
            await self.app(scope, receive, send)
        finally:
            current_tenant_id.reset(token)


async def bind_tenant_context(session: AsyncSession, tenant_id: uuid.UUID) -> None:
    await session.execute(text("SELECT set_config('app.current_tenant', :tenant_id, true)"), {"tenant_id": str(tenant_id)})


def require_current_tenant() -> uuid.UUID:
    tenant_id = current_tenant_id.get()
    if tenant_id is None:
        raise HTTPException(status_code=401, detail="tenant context required")
    return tenant_id


async def get_tenant_scoped_db(session_factory: Callable[[], Awaitable[AsyncSession]]) -> AsyncIterator[AsyncSession]:
    """Not used directly as a FastAPI dependency (kept framework-agnostic for
    testability) — see `evagg.core.db.get_db` for the actual dependency that
    wires this to the app's session factory."""
    tenant_id = require_current_tenant()
    session = await session_factory()
    try:
        await bind_tenant_context(session, tenant_id)
        yield session
    finally:
        await session.close()


async def log_superadmin_access(actor: str, reason: str, table: str | None = None) -> None:
    """Every BYPASSRLS access must be logged — see Task 4.1's acceptance
    criteria. This is a structured log line (correlation-friendly) rather than
    a DB row, so it can never itself be hidden by an RLS policy."""
    logger.warning(
        "superadmin_bypass_access",
        extra={"actor": actor, "reason": reason, "table": table},
    )
