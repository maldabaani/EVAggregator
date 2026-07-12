"""Task 6.3 — the public-facing API Gateway / BFF.

This is a separate FastAPI app from `evagg.main` (the internal-services app):
it terminates OAuth2/PKCE and SSO, rate-limits per tenant, and — in a real
deployment — forwards authenticated calls to internal services with a signed
`X-Tenant-Id` header (see `evagg.gateway.trust`). It's a factory function
rather than a module-level singleton so tests can inject in-memory stores
instead of hitting Redis.

Real OAuth2 token endpoints use form-encoded bodies; this uses JSON bodies for
simplicity — a deliberate simplification, not a spec claim.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from evagg.core.config import settings
from evagg.gateway.jwt_tokens import create_access_token
from evagg.gateway.pkce import verify_code_verifier
from evagg.gateway.rate_limit import InMemoryRateLimiter, RateLimiter
from evagg.gateway.refresh_store import InMemoryRefreshTokenStore, RefreshTokenError, RefreshTokenStore
from evagg.gateway.sso import SSOError, SSOProvider


@dataclass(frozen=True)
class _PendingAuthorization:
    code_challenge: str
    subject: str
    tenant_id: uuid.UUID


class AuthorizationCodeStore:
    """In-memory single-use store mapping an issued auth `code` to the PKCE
    challenge and identity it was issued for. Production backs this with
    Redis (short TTL) since codes are single-use and short-lived by spec."""

    def __init__(self) -> None:
        self._pending: dict[str, _PendingAuthorization] = {}

    def create(self, subject: str, tenant_id: uuid.UUID, code_challenge: str) -> str:
        code = str(uuid.uuid4())
        self._pending[code] = _PendingAuthorization(code_challenge, subject, tenant_id)
        return code

    def consume(self, code: str) -> _PendingAuthorization:
        pending = self._pending.pop(code, None)
        if pending is None:
            raise HTTPException(status_code=400, detail="invalid or already-used authorization code")
        return pending


class AuthorizeRequest(BaseModel):
    subject: str
    tenant_id: uuid.UUID
    code_challenge: str


class TokenRequest(BaseModel):
    grant_type: str
    code: str | None = None
    code_verifier: str | None = None
    refresh_token: str | None = None


class SSOCallbackRequest(BaseModel):
    tenant_id: uuid.UUID
    credential: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


def build_gateway_app(
    rate_limiter: RateLimiter | None = None,
    refresh_store: RefreshTokenStore | None = None,
    auth_code_store: AuthorizationCodeStore | None = None,
    sso_providers: dict[str, SSOProvider] | None = None,
) -> FastAPI:
    rate_limiter = rate_limiter or InMemoryRateLimiter()
    refresh_store = refresh_store or InMemoryRefreshTokenStore()
    auth_code_store = auth_code_store or AuthorizationCodeStore()
    sso_providers = sso_providers or {}

    app = FastAPI(title="EV Charging Aggregator Gateway/BFF", version="0.1.0")

    async def _enforce_rate_limit(tenant_id: uuid.UUID) -> None:
        allowed = await rate_limiter.allow(
            key=f"tenant:{tenant_id}",
            limit=settings.rate_limit_requests_per_window,
            window_seconds=settings.rate_limit_window_seconds,
        )
        if not allowed:
            raise HTTPException(status_code=429, detail="rate limit exceeded")

    @app.post("/oauth/authorize")
    async def authorize(body: AuthorizeRequest) -> dict[str, str]:
        # Simplified for a public mobile client: a real flow redirects to a
        # login UI first and only issues the code after the user authenticates.
        code = auth_code_store.create(body.subject, body.tenant_id, body.code_challenge)
        return {"code": code}

    @app.post("/oauth/token", response_model=TokenResponse)
    async def token(body: TokenRequest) -> TokenResponse:
        if body.grant_type == "authorization_code":
            if not body.code or not body.code_verifier:
                raise HTTPException(status_code=400, detail="code and code_verifier required")
            pending = auth_code_store.consume(body.code)
            if not verify_code_verifier(body.code_verifier, pending.code_challenge):
                raise HTTPException(status_code=400, detail="PKCE verification failed")

            await _enforce_rate_limit(pending.tenant_id)
            access_token = create_access_token(pending.subject, pending.tenant_id)
            refresh = await refresh_store.issue(pending.subject, pending.tenant_id)
            return TokenResponse(access_token=access_token, refresh_token=refresh.token)

        if body.grant_type == "refresh_token":
            if not body.refresh_token:
                raise HTTPException(status_code=400, detail="refresh_token required")
            try:
                rotated = await refresh_store.rotate(body.refresh_token)
            except RefreshTokenError as exc:
                raise HTTPException(status_code=401, detail=str(exc)) from exc

            await _enforce_rate_limit(rotated.tenant_id)
            access_token = create_access_token(rotated.subject, rotated.tenant_id)
            return TokenResponse(access_token=access_token, refresh_token=rotated.token)

        raise HTTPException(status_code=400, detail=f"unsupported grant_type: {body.grant_type}")

    @app.post("/sso/{provider_id}/callback", response_model=TokenResponse)
    async def sso_callback(provider_id: str, body: SSOCallbackRequest) -> TokenResponse:
        provider = sso_providers.get(provider_id)
        if provider is None:
            raise HTTPException(status_code=404, detail="unknown SSO provider")
        try:
            identity = provider.authenticate(body.credential)
        except SSOError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

        await _enforce_rate_limit(body.tenant_id)
        access_token = create_access_token(identity.subject_id, body.tenant_id)
        refresh = await refresh_store.issue(identity.subject_id, body.tenant_id)
        return TokenResponse(access_token=access_token, refresh_token=refresh.token)

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app
