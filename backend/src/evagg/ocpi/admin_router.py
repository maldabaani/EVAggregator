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
    export_reconciliation_csv,
    filter_reconciliation_entries,
    rotate_token_a,
)
from evagg.ocpi.partner_store import Partner, PartnerRegistry


class SessionBindingRequest(BaseModel):
    charger_id: str
    tenant_id: uuid.UUID
    connector_id: int


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
    partner_registry_dependency, reconciliation_store_dependency, session_charger_map_dependency
) -> APIRouter:
    router = APIRouter(prefix="/admin/ocpi", tags=["ocpi-admin"])

    @router.get("/partners")
    async def list_partners(registry: PartnerRegistry = Depends(partner_registry_dependency)) -> dict:
        partners = await registry.list_all()
        return {"data": [_partner_to_dict(p) for p in partners]}

    @router.post("/partners/{partner_id}/rotate-token")
    async def rotate_token(
        partner_id: uuid.UUID, registry: PartnerRegistry = Depends(partner_registry_dependency)
    ) -> dict:
        new_token = secrets.token_urlsafe(24)
        await rotate_token_a(registry, partner_id, new_token)
        return {"token_a": new_token}

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
