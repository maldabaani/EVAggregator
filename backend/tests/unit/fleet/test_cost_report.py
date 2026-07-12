"""Task 4.4 unit tests — all isolated (in-memory rollup store)."""

from __future__ import annotations

import inspect
import uuid
from datetime import date, datetime, timezone

import pytest

from evagg.fleet.cost_report import CostReportService, export_cost_report_csv
from evagg.fleet.rollup import InMemoryRollupStore, SessionUsageRecord, run_daily_rollup

TEAM_ID = uuid.uuid4()
DRIVER_A = uuid.uuid4()
DRIVER_B = uuid.uuid4()
SITE_1 = uuid.uuid4()
SITE_2 = uuid.uuid4()

DAY_1 = date(2026, 6, 1)
DAY_2 = date(2026, 6, 2)


def _sessions() -> list[SessionUsageRecord]:
    return [
        SessionUsageRecord(TEAM_ID, DRIVER_A, SITE_1, datetime(2026, 6, 1, 9, tzinfo=timezone.utc), kwh=10, cost_minor_units=1500),
        SessionUsageRecord(TEAM_ID, DRIVER_A, SITE_1, datetime(2026, 6, 1, 18, tzinfo=timezone.utc), kwh=5, cost_minor_units=800),
        SessionUsageRecord(TEAM_ID, DRIVER_B, SITE_2, datetime(2026, 6, 1, 12, tzinfo=timezone.utc), kwh=20, cost_minor_units=3000),
        SessionUsageRecord(TEAM_ID, DRIVER_A, SITE_1, datetime(2026, 6, 2, 8, tzinfo=timezone.utc), kwh=8, cost_minor_units=1200),
    ]


@pytest.mark.asyncio
async def test_cost_report_per_driver_totals_match_underlying_sessions():
    store = InMemoryRollupStore()
    sessions = _sessions()
    await run_daily_rollup(store, sessions, DAY_1)
    await run_daily_rollup(store, sessions, DAY_2)
    service = CostReportService(store)

    report = await service.generate_report(TEAM_ID, DAY_1, DAY_2, group_by="driver")

    rows_by_key = {row.key: row for row in report.rows}
    driver_a_expected_kwh = 10 + 5 + 8
    driver_a_expected_cost = 1500 + 800 + 1200
    driver_b_expected_kwh = 20
    driver_b_expected_cost = 3000

    assert rows_by_key[str(DRIVER_A)].kwh_total == driver_a_expected_kwh
    assert rows_by_key[str(DRIVER_A)].cost_total_minor_units == driver_a_expected_cost
    assert rows_by_key[str(DRIVER_B)].kwh_total == driver_b_expected_kwh
    assert rows_by_key[str(DRIVER_B)].cost_total_minor_units == driver_b_expected_cost
    assert report.total_kwh == sum(s.kwh for s in sessions)
    assert report.total_cost_minor_units == sum(s.cost_minor_units for s in sessions)


@pytest.mark.asyncio
async def test_group_by_site_returns_correct_aggregation():
    store = InMemoryRollupStore()
    sessions = _sessions()
    await run_daily_rollup(store, sessions, DAY_1)
    await run_daily_rollup(store, sessions, DAY_2)
    service = CostReportService(store)

    report = await service.generate_report(TEAM_ID, DAY_1, DAY_2, group_by="site")

    rows_by_key = {row.key: row for row in report.rows}
    # Site 1 covers driver A's three sessions; site 2 covers driver B's one session.
    assert rows_by_key[str(SITE_1)].kwh_total == 10 + 5 + 8
    assert rows_by_key[str(SITE_2)].kwh_total == 20


@pytest.mark.asyncio
async def test_csv_export_matches_filtered_dashboard_data():
    store = InMemoryRollupStore()
    sessions = _sessions()
    await run_daily_rollup(store, sessions, DAY_1)
    service = CostReportService(store)
    report = await service.generate_report(TEAM_ID, DAY_1, DAY_1, group_by="driver")

    csv_text = export_cost_report_csv(report)

    rows = csv_text.strip().splitlines()
    assert rows[0] == "driver,session_count,kwh_total,cost_total_minor_units"
    assert len(rows) - 1 == len(report.rows)
    for row_line, report_row in zip(rows[1:], report.rows):
        assert report_row.key in row_line
        assert str(report_row.kwh_total) in row_line


@pytest.mark.asyncio
async def test_rollup_job_failure_flags_incomplete_data_for_that_day():
    store = InMemoryRollupStore()
    sessions = _sessions()
    await run_daily_rollup(store, sessions, DAY_1, failing_dates={DAY_1})
    await run_daily_rollup(store, sessions, DAY_2)
    service = CostReportService(store)

    report = await service.generate_report(TEAM_ID, DAY_1, DAY_2, group_by="driver")

    assert DAY_1 in report.incomplete_dates
    # DAY_1's sessions never got rolled up -> only DAY_2's contribute to the totals,
    # so the dashboard doesn't silently show a plausible-looking (but wrong) full total.
    rows_by_key = {row.key: row for row in report.rows}
    assert rows_by_key[str(DRIVER_A)].kwh_total == 8  # only the DAY_2 session


def test_report_reads_from_rollup_table_not_raw_sessions():
    """Structural check: CostReportService has no dependency capable of
    reading raw session records at all — only a RollupStore."""
    signature = inspect.signature(CostReportService.__init__)
    param_names = list(signature.parameters.keys())

    assert param_names == ["self", "rollup_store"]
