"""Task 4.1 unit tests for the RLS audit script's pure logic (no live DB)."""

from __future__ import annotations

from evagg.scripts.audit_rls import EXEMPT_TABLES, find_tables_missing_rls, tables_requiring_rls


def _fully_compliant_state():
    tables = tables_requiring_rls()
    rowsecurity = {t: True for t in tables}
    policies = {t: 1 for t in tables}
    return rowsecurity, policies


def test_fully_compliant_state_reports_no_missing_tables():
    rowsecurity, policies = _fully_compliant_state()
    assert find_tables_missing_rls(rowsecurity, policies) == []


def test_table_missing_rowsecurity_flag_is_reported():
    rowsecurity, policies = _fully_compliant_state()
    some_table = next(iter(tables_requiring_rls()))
    rowsecurity[some_table] = False

    missing = find_tables_missing_rls(rowsecurity, policies)

    assert some_table in missing


def test_table_with_rls_enabled_but_zero_policies_is_reported():
    rowsecurity, policies = _fully_compliant_state()
    some_table = next(iter(tables_requiring_rls()))
    policies[some_table] = 0

    missing = find_tables_missing_rls(rowsecurity, policies)

    assert some_table in missing


def test_new_tenant_scoped_table_absent_from_db_state_is_reported():
    """Simulates a newly added tenant-scoped model that hasn't had its RLS
    migration written yet — the audit must flag it, closing the CI gap called
    out in Task 6.1's acceptance criteria."""
    missing = find_tables_missing_rls(rowsecurity_by_table={}, policy_count_by_table={})

    assert set(missing) == tables_requiring_rls()


def test_exempt_tables_are_never_reported_missing():
    rowsecurity, policies = {}, {}
    missing = find_tables_missing_rls(rowsecurity, policies)
    for exempt_table in EXEMPT_TABLES:
        assert exempt_table not in missing
