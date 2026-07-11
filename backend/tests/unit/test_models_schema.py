"""Task 6.1 unit tests: schema-level checks that don't require a live database.

Full migration-apply checks (empty DB, seed data, concurrent-read staging
verification) are integration tests against real Postgres — see
tests/integration/test_migrations.py.
"""

from __future__ import annotations

from sqlalchemy import ForeignKeyConstraint
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

import evagg.models  # noqa: F401  (populates Base.metadata)
from evagg.models.base import Base, TENANT_SCOPED_TABLES


def test_every_tenant_scoped_table_has_tenant_id_column():
    for table_name in TENANT_SCOPED_TABLES:
        table = Base.metadata.tables[table_name]
        assert "tenant_id" in table.columns, f"{table_name} is missing tenant_id"
        assert not table.columns["tenant_id"].nullable


def test_every_tenant_scoped_table_has_uuid_id_and_timestamps():
    for table_name in TENANT_SCOPED_TABLES:
        table = Base.metadata.tables[table_name]
        for expected in ("id", "created_at", "updated_at"):
            assert expected in table.columns, f"{table_name} is missing {expected}"


def test_organization_table_has_no_tenant_id_column():
    org = Base.metadata.tables["organization"]
    assert "tenant_id" not in org.columns


def test_all_foreign_keys_have_supporting_indexes():
    """Every FK column must be indexed (either standalone or as the leading
    column of a composite index), per the Task 6.1 indexing baseline."""
    unsupported = []
    for table in Base.metadata.tables.values():
        indexed_leading_columns = {idx.expressions[0].name for idx in table.indexes if idx.expressions}
        indexed_leading_columns |= {col.name for col in table.primary_key.columns}
        for constraint in table.constraints:
            if isinstance(constraint, ForeignKeyConstraint):
                fk_column = constraint.column_keys[0]
                if fk_column not in indexed_leading_columns:
                    unsupported.append(f"{table.name}.{fk_column}")
    assert not unsupported, f"FK columns missing a supporting index: {unsupported}"


def test_ddl_compiles_for_postgresql_dialect():
    """Every table's DDL must compile against the Postgres dialect — a cheap,
    network-free way to catch type/constraint mistakes before they ever reach
    a real database."""
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        ddl = str(CreateTable(table).compile(dialect=dialect))
        assert "CREATE TABLE" in ddl


def test_monetary_columns_are_integer_not_float():
    """Spot-check the billing tables: monetary values must be integer minor
    units, never float, per engineering standards."""
    from sqlalchemy import Integer

    monetary_columns = [
        ("tariff_component", "price_minor_units"),
        ("invoice", "total_minor_units"),
        ("invoice_adjustment", "amount_minor_units"),
        ("wallet", "balance_minor_units"),
        ("wallet_ledger", "amount_minor_units"),
        ("payout", "amount_minor_units"),
    ]
    for table_name, column_name in monetary_columns:
        column = Base.metadata.tables[table_name].columns[column_name]
        assert isinstance(column.type, Integer), f"{table_name}.{column_name} must be Integer, got {column.type}"
