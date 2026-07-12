"""Task 1.3 backend unit tests — token rotation, price-list scheduling, and
the nightly reconciliation job + CSV export. The Partner List empty-state
test lives in the Angular portal (see portal/src/app/.../partner-list)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from evagg.ocpi.partner_admin import (
    InMemoryPriceListStore,
    PartnerPriceList,
    export_reconciliation_csv,
    filter_reconciliation_entries,
    reconcile_cdr_batch,
    rotate_token_a,
)
from evagg.ocpi.partner_store import InMemoryPartnerRegistry, Partner

TENANT_ID = uuid.uuid4()


def _partner(**overrides) -> Partner:
    defaults = dict(
        id=uuid.uuid4(),
        tenant_id=TENANT_ID,
        party_id="ABC",
        country_code="AE",
        token_a="old-token-a",
        token_c=None,
        negotiated_version=None,
        status="connected",
    )
    defaults.update(overrides)
    return Partner(**defaults)


@pytest.mark.asyncio
async def test_token_rotation_invalidates_old_token():
    partner = _partner()
    registry = InMemoryPartnerRegistry([partner])

    await rotate_token_a(registry, partner.id, "new-token-a")

    assert await registry.find_by_token_a("old-token-a") is None
    found = await registry.find_by_token_a("new-token-a")
    assert found is not None
    assert found.id == partner.id


@pytest.mark.asyncio
async def test_price_list_not_applied_before_effective_date():
    store = InMemoryPriceListStore()
    partner_id = uuid.uuid4()
    tariff_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    future = now + timedelta(days=7)
    await store.attach(PartnerPriceList(partner_id=partner_id, connector_type="CCS2", tariff_id=tariff_id, effective_from=future))

    before = await store.get_active(partner_id, "CCS2", at=now)
    after = await store.get_active(partner_id, "CCS2", at=future + timedelta(seconds=1))

    assert before is None
    assert after is not None
    assert after.tariff_id == tariff_id


@pytest.mark.asyncio
async def test_price_list_uses_most_recent_effective_entry():
    store = InMemoryPriceListStore()
    partner_id = uuid.uuid4()
    old_tariff_id = uuid.uuid4()
    new_tariff_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    await store.attach(PartnerPriceList(partner_id, "CCS2", old_tariff_id, effective_from=now - timedelta(days=30)))
    await store.attach(PartnerPriceList(partner_id, "CCS2", new_tariff_id, effective_from=now - timedelta(days=1)))

    active = await store.get_active(partner_id, "CCS2", at=now)

    assert active.tariff_id == new_tariff_id


def test_reconciliation_job_flags_amount_mismatch_above_threshold():
    local_totals = {"CDR-1": 100.0, "CDR-2": 50.0}
    partner_reports = [
        ("PARTNER-CDR-1", "CDR-1", 105.0),  # 5% delta -> mismatched
        ("PARTNER-CDR-2", "CDR-2", 50.5),  # 1% delta -> matched
    ]

    results = reconcile_cdr_batch(local_totals, partner_reports)

    by_partner_uid = {r.partner_cdr_uid: r for r in results}
    assert by_partner_uid["PARTNER-CDR-1"].status == "mismatched"
    assert by_partner_uid["PARTNER-CDR-2"].status == "matched"


def test_reconciliation_job_flags_unmatched_partner_cdr_as_pending():
    results = reconcile_cdr_batch({}, [("PARTNER-CDR-99", None, 10.0)])

    assert results[0].status == "pending"


def test_reconciliation_csv_export_matches_filtered_view():
    local_totals = {"CDR-1": 100.0, "CDR-2": 50.0, "CDR-3": 20.0}
    partner_reports = [
        ("PARTNER-CDR-1", "CDR-1", 105.0),  # mismatched
        ("PARTNER-CDR-2", "CDR-2", 50.5),  # matched
        ("PARTNER-CDR-3", "CDR-3", 21.0),  # mismatched (5%)
    ]
    all_entries = reconcile_cdr_batch(local_totals, partner_reports)

    filtered_view = filter_reconciliation_entries(all_entries, status="mismatched")
    csv_text = export_reconciliation_csv(filtered_view)

    rows = csv_text.strip().splitlines()
    assert rows[0] == "local_cdr_id,partner_cdr_uid,status,delta_fraction"
    data_rows = rows[1:]
    assert len(data_rows) == len(filtered_view) == 2
    for entry, row in zip(filtered_view, data_rows):
        assert entry.partner_cdr_uid in row
        assert entry.status in row
