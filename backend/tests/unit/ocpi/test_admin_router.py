import asyncio
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from starlette.testclient import TestClient

from evagg.ocpi.admin_router import build_admin_router
from evagg.ocpi.charging_profiles import InMemorySessionChargerMap
from evagg.ocpi.partner_admin import InMemoryPriceListStore, InMemoryReconciliationResultStore, ReconciliationEntry
from evagg.ocpi.partner_store import InMemoryPartnerRegistry, Partner

TENANT_ID = uuid.uuid4()


def _build_app(registry, reconciliation_store, session_charger_map=None, price_list_store=None):
    async def get_registry():
        return registry

    async def get_reconciliation_store():
        return reconciliation_store

    async def get_session_charger_map():
        return session_charger_map or InMemorySessionChargerMap()

    async def get_price_list_store():
        return price_list_store or InMemoryPriceListStore()

    app = FastAPI()
    app.include_router(
        build_admin_router(get_registry, get_reconciliation_store, get_session_charger_map, get_price_list_store)
    )
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


def test_create_partner_endpoint_returns_a_one_time_token_a():
    registry = InMemoryPartnerRegistry()
    client = TestClient(_build_app(registry, InMemoryReconciliationResultStore()))

    response = client.post(
        "/admin/ocpi/partners",
        json={"tenant_id": str(TENANT_ID), "party_id": "XYZ", "country_code": "AE"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == str(TENANT_ID)
    assert body["party_id"] == "XYZ"
    assert body["country_code"] == "AE"
    assert body["status"] == "pending"
    assert len(body["token_a"]) > 0

    partners = asyncio.run(registry.list_all())
    assert len(partners) == 1
    assert partners[0].token_a == body["token_a"]


def test_created_partner_can_immediately_rotate_its_token():
    registry = InMemoryPartnerRegistry()
    client = TestClient(_build_app(registry, InMemoryReconciliationResultStore()))

    created = client.post(
        "/admin/ocpi/partners",
        json={"tenant_id": str(TENANT_ID), "party_id": "XYZ", "country_code": "AE"},
    ).json()

    response = client.post(f"/admin/ocpi/partners/{created['id']}/rotate-token")

    assert response.status_code == 200
    assert response.json()["token_a"] != created["token_a"]


def test_attach_price_list_endpoint_records_the_attachment():
    store = InMemoryPriceListStore()
    client = TestClient(
        _build_app(InMemoryPartnerRegistry(), InMemoryReconciliationResultStore(), price_list_store=store)
    )
    partner_id = uuid.uuid4()
    tariff_id = uuid.uuid4()

    response = client.post(
        f"/admin/ocpi/partners/{partner_id}/price-lists",
        json={"connector_type": "CCS2", "tariff_id": str(tariff_id), "effective_from": "2026-01-01T00:00:00Z"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["partner_id"] == str(partner_id)
    assert body["connector_type"] == "CCS2"

    active = asyncio.run(store.get_active(partner_id, "CCS2", datetime(2026, 6, 1, tzinfo=timezone.utc)))
    assert active is not None
    assert active.tariff_id == tariff_id


def test_session_binding_endpoint_records_the_charger_mapping():
    session_charger_map = InMemorySessionChargerMap()
    client = TestClient(
        _build_app(InMemoryPartnerRegistry(), InMemoryReconciliationResultStore(), session_charger_map)
    )

    response = client.post(
        "/admin/ocpi/sessions/SESSION-1/binding",
        json={"charger_id": "CP-001", "tenant_id": str(TENANT_ID), "connector_id": 1},
    )

    assert response.status_code == 200
    binding = asyncio.run(session_charger_map.get_charger_for_session("SESSION-1"))
    assert binding is not None
    assert binding.charger_id == "CP-001"
    assert binding.connector_id == 1
