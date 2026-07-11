"""Task 3.3 — POST /wallet/topup and the PSP webhook callback."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from evagg.billing.wallet import WalletService


class TopupRequest(BaseModel):
    wallet_id: uuid.UUID
    psp_token: str
    amount_minor_units: int
    currency: str


class TopupWebhookPayload(BaseModel):
    wallet_id: uuid.UUID
    psp_transaction_id: str
    amount_minor_units: int


def build_wallet_router(service_dependency) -> APIRouter:
    router = APIRouter(prefix="/wallet", tags=["wallet"])

    @router.post("/topup")
    async def topup(body: TopupRequest, service: WalletService = Depends(service_dependency)) -> dict:
        txn_ref = await service.initiate_topup(body.wallet_id, body.psp_token, body.amount_minor_units, body.currency)
        return {"psp_transaction_ref": txn_ref}

    @router.post("/topup/webhook")
    async def topup_webhook(body: TopupWebhookPayload, service: WalletService = Depends(service_dependency)) -> dict:
        await service.handle_topup_webhook(body.wallet_id, body.psp_transaction_id, body.amount_minor_units)
        return {"status": "ok"}

    @router.get("/{wallet_id}/balance")
    async def get_balance(wallet_id: uuid.UUID, service: WalletService = Depends(service_dependency)) -> dict:
        balance = await service.get_balance(wallet_id)
        return {"wallet_id": str(wallet_id), "balance_minor_units": balance}

    return router
