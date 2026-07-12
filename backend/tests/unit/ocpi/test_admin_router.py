import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.ocpi.admin_router import build_admin_router
from evagg.ocpi.partner_admin import InMemoryReconciliationResultStore, ReconciliationEntry
from evagg.ocpi.partner_store import InMemoryPartnerRegistry, Partner

TENANT_ID = uuid.uuid4()


def _build_app(registry, reconciliation_store):
    async def get_registry():
        return registry

    async def get_reconciliation_store():
        return reconciliation_store

    app = FastAPI()
    app.include_router(build_admin_router(get_registry, get_reconciliation_store))
    return app


def test_partner_list_endpoint_returns_all_partners():
    partner = Partner(
        id=uuid.uuid4(), tenant_id=TENANT_ID, party_id="ABC", country_code="AE",
        token_a="tok-a", token_c="tok-c", negotiated_version="2.2.1", status="connected",
    )
    registry = InMemoryPartnerRegistry([partner])
    client = TestClient(_build_app(registry, InMemoryReconciliationResultStore()))

    response = client.get("/admin/ocpi/partners")

    assert response.status_code == 200
    assert response.json()["data"][0]["party_id"] == "ABC"


def test_partner_list_endpoint_returns_empty_list_when_no_partners():
    client = TestClient(_build_app(InMemoryPartnerRegistry(), InMemoryReconciliationResultStore()))

    response = client.get("/admin/ocpi/partners")

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_rotate_token_endpoint_invalidates_old_token():
    partner = Partner(
        id=uuid.uuid4(), tenant_id=TENANT_ID, party_id="ABC", country_code="AE",
        token_a="old-token", token_c=None, negotiated_version=None, status="connected",
    )
    registry = InMemoryPartnerRegistry([partner])
    client = TestClient(_build_app(registry, InMemoryReconciliationResultStore()))

    response = client.post(f"/admin/ocpi/partners/{partner.id}/rotate-token")

    assert response.status_code == 200
    new_token = response.json()["token_a"]
    assert new_token != "old-token"


def test_reconciliation_export_endpoint_returns_csv():
    store = InMemoryReconciliationResultStore()
    entry = ReconciliationEntry(local_cdr_id="CDR-1", partner_cdr_uid="P-1", status="mismatched", delta_fraction=0.05)
    asyncio.run(store.save_batch([entry], run_at=datetime.now(timezone.utc)))
    client = TestClient(_build_app(InMemoryPartnerRegistry(), store))

    response = client.get("/admin/ocpi/reconciliation/export", params={"status": "mismatched"})

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "CDR-1" in response.text
