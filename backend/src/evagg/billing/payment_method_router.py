"""GET/POST /wallet/{wallet_id}/payment-method — lets a driver actually set
their default payment method. `PaymentMethodStore` (Task 3.3) always had
`get_default` (read by `SessionStartService`/`SessionBillingService` when
a session starts/ends) but nothing ever wrote to it outside test seeding —
there was no way for a driver to actually register one.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator

from evagg.billing.payment_methods import DIRECT_CARD, WALLET_BALANCE, PaymentMethod, PaymentMethodStore

_VALID_TYPES = (WALLET_BALANCE, DIRECT_CARD)


class SetPaymentMethodRequest(BaseModel):
    type: str
    psp_token: str | None = None

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        if value not in _VALID_TYPES:
            raise ValueError(f"type must be one of {_VALID_TYPES}")
        return value


def _method_dict(method: PaymentMethod) -> dict:
    return {"id": str(method.id), "type": method.type, "psp_token": method.psp_token, "is_default": method.is_default}


def build_payment_method_router(service_dependency) -> APIRouter:
    router = APIRouter(prefix="/wallet/{wallet_id}/payment-method", tags=["wallet"])

    @router.get("")
    async def get_payment_method(
        wallet_id: uuid.UUID, store: PaymentMethodStore = Depends(service_dependency)
    ) -> dict:
        method = await store.get_default(wallet_id)
        return {"data": _method_dict(method) if method else None}

    @router.post("")
    async def set_payment_method(
        wallet_id: uuid.UUID,
        body: SetPaymentMethodRequest,
        store: PaymentMethodStore = Depends(service_dependency),
    ) -> dict:
        if body.type == DIRECT_CARD and not body.psp_token:
            raise HTTPException(status_code=422, detail="psp_token is required for a direct_card payment method")
        method = await store.set_default(wallet_id, body.type, body.psp_token)
        return _method_dict(method)

    return router
