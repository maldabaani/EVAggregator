"""POST /auth/signup, /auth/login, /auth/refresh — driver account creation
and session issuance for the mobile app. Reuses the same access-token/
refresh-token pair shape the gateway issues to portal operators
(`evagg.gateway.jwt_tokens`, `evagg.gateway.refresh_store`), just for a
driver identity instead of a portal one.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from evagg.gateway.jwt_tokens import create_access_token
from evagg.gateway.refresh_store import RefreshTokenError, RefreshTokenStore
from evagg.identity.driver_auth import DriverAccount, DriverAccountStore, EmailAlreadyRegisteredError, verify_password


def _check_email(value: str) -> str:
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        raise ValueError("not a valid email address")
    return value


class SignupRequest(BaseModel):
    email: str
    full_name: str
    password: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _check_email(value)


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str) -> str:
        return _check_email(value)


class RefreshRequest(BaseModel):
    refresh_token: str


def _account_to_dict(account: DriverAccount) -> dict:
    return {"id": str(account.id), "email": account.email, "full_name": account.full_name}


async def _issue_session(account: DriverAccount, refresh_store: RefreshTokenStore) -> dict:
    access_token = create_access_token(str(account.id), account.tenant_id)
    refresh = await refresh_store.issue(str(account.id), account.tenant_id)
    return {"access_token": access_token, "refresh_token": refresh.token, "driver": _account_to_dict(account)}


def build_driver_auth_router(store_dependency, refresh_store_dependency) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["driver-auth"])

    @router.post("/signup")
    async def signup(
        body: SignupRequest,
        store: DriverAccountStore = Depends(store_dependency),
        refresh_store: RefreshTokenStore = Depends(refresh_store_dependency),
    ) -> dict:
        try:
            account = await store.create(body.email, body.full_name, body.password)
        except EmailAlreadyRegisteredError:
            raise HTTPException(status_code=409, detail="email already registered")
        return await _issue_session(account, refresh_store)

    @router.post("/login")
    async def login(
        body: LoginRequest,
        store: DriverAccountStore = Depends(store_dependency),
        refresh_store: RefreshTokenStore = Depends(refresh_store_dependency),
    ) -> dict:
        account = await store.find_by_email(body.email)
        if account is None or not verify_password(account, body.password):
            raise HTTPException(status_code=401, detail="invalid email or password")
        return await _issue_session(account, refresh_store)

    @router.post("/refresh")
    async def refresh(
        body: RefreshRequest,
        store: DriverAccountStore = Depends(store_dependency),
        refresh_store: RefreshTokenStore = Depends(refresh_store_dependency),
    ) -> dict:
        try:
            rotated = await refresh_store.rotate(body.refresh_token)
        except RefreshTokenError:
            raise HTTPException(status_code=401, detail="invalid refresh token")
        account = await store.get(uuid.UUID(rotated.subject))
        if account is None:
            raise HTTPException(status_code=401, detail="invalid refresh token")
        access_token = create_access_token(str(account.id), account.tenant_id)
        return {"access_token": access_token, "refresh_token": rotated.token, "driver": _account_to_dict(account)}

    return router
