"""Task 1.3 — operator portal admin API: partner list/credentials rotation
and reconciliation query + CSV export.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from evagg.ocpi.charging_profiles import InMemorySessionChargerMap, SessionChargerBinding
from evagg.ocpi.partner_admin import (
    PartnerPriceList,
    PriceListStore,
    export_reconciliation_csv,
    filter_reconciliation_entries,
    rotate_token_a,
)
from evagg.ocpi.partner_store import Partner, PartnerRegistry


class SessionBindingRequest(BaseModel):
    charger_id: str
    tenant_id: uuid.UUID
    connector_id: int


class CreatePartnerRequest(BaseModel):
    tenant_id: uuid.UUID
    party_id: str
    country_code: str


class AttachPriceListRequest(BaseModel):
    connector_type: str
    tariff_id: uuid.UUID
    effective_from: datetime


def _partner_to_dict(partner: Partner) -> dict:
    return {
        "id": str(partner.id),
        "party_id": partner.party_id,
        "country_code": partner.country_code,
        "negotiated_version": partner.negotiated_version,
        "status": partner.status,
        "last_handshake_at": partner.last_handshake_at.isoformat() if partner.last_handshake_at else None,
    }


def build_admin_router(
    partner_registry_dependency,
    reconciliation_store_dependency,
    session_charger_map_dependency,
    price_list_store_dependency,
) -> APIRouter:
    router = APIRouter(prefix="/admin/ocpi", tags=["ocpi-admin"])

    @router.get("/partners")
    async def list_partners(registry: PartnerRegistry = Depends(partner_registry_dependency)) -> dict:
        partners = await registry.list_all()
        return {"data": [_partner_to_dict(p) for p in partners]}

    @router.post("/partners")
    async def create_partner(
        body: CreatePartnerRequest, registry: PartnerRegistry = Depends(partner_registry_dependency)
    ) -> dict:
        # token_a is generated here, not inside the store, matching
        # rotate_token's existing split (crypto concerns live at the route,
        # persistence at the store) — returned once so the operator can
        # copy it to share with the partner out-of-band; no later read of
        # this partner ever exposes it again.
        token_a = secrets.token_urlsafe(24)
        partner = await registry.create(body.tenant_id, body.party_id, body.country_code, token_a)
        return _partner_to_dict(partner) | {"token_a": token_a}

    @router.post("/partners/{partner_id}/rotate-token")
    async def rotate_token(
        partner_id: uuid.UUID, registry: PartnerRegistry = Depends(partner_registry_dependency)
    ) -> dict:
        new_token = secrets.token_urlsafe(24)
        await rotate_token_a(registry, partner_id, new_token)
        return {"token_a": new_token}

    @router.post("/partners/{partner_id}/price-lists")
    async def attach_price_list(
        partner_id: uuid.UUID,
        body: AttachPriceListRequest,
        store: PriceListStore = Depends(price_list_store_dependency),
    ) -> dict:
        price_list = PartnerPriceList(
            partner_id=partner_id,
            connector_type=body.connector_type,
            tariff_id=body.tariff_id,
            effective_from=body.effective_from,
        )
        await store.attach(price_list)
        return {
            "partner_id": str(partner_id),
            "connector_type": body.connector_type,
            "tariff_id": str(body.tariff_id),
            "effective_from": body.effective_from.isoformat(),
        }

    @router.get("/reconciliation")
    async def reconciliation(
        status: str | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
        store=Depends(reconciliation_store_dependency),
    ) -> dict:
        entries = await store.query(from_=from_, to=to)
        filtered = filter_reconciliation_entries(entries, status=status)
        return {"data": [entry.__dict__ for entry in filtered]}

    @router.get("/reconciliation/export")
    async def reconciliation_export(
        status: str | None = None,
        from_: datetime | None = None,
        to: datetime | None = None,
        store=Depends(reconciliation_store_dependency),
    ) -> Response:
        entries = await store.query(from_=from_, to=to)
        filtered = filter_reconciliation_entries(entries, status=status)
        csv_body = export_reconciliation_csv(filtered)
        return Response(content=csv_body, media_type="text/csv")

    @router.post("/sessions/{session_id}/binding")
    async def bind_session_to_charger(
        session_id: str,
        body: SessionBindingRequest,
        session_charger_map: InMemorySessionChargerMap = Depends(session_charger_map_dependency),
    ) -> dict:
        """Records which charger/connector an OCPI session_id maps to, so the
        ChargingProfiles module can resolve it. A stand-in for the live
        `LocationSyncService`-style event consumer this doesn't have yet
        (see `charging_profiles.py`'s module docstring) — start_transaction
        already mints the transaction_id/session_id, but nothing today
        pushes that mapping here automatically."""
        session_charger_map.set_binding(
            session_id,
            SessionChargerBinding(charger_id=body.charger_id, tenant_id=body.tenant_id, connector_id=body.connector_id),
        )
        return {"session_id": session_id, "charger_id": body.charger_id, "connector_id": body.connector_id}

    return router
