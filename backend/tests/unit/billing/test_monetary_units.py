"""Task 3.1's explicitly named AC: monetary values are stored as integer
minor units, never float — verified both at the calculator boundary and the
ORM schema boundary (Task 6.1)."""

from __future__ import annotations

from evagg.billing.tariff_calculator import TariffComponentInput, calculate_session_cost
from evagg.models.billing import TariffComponent


def test_monetary_values_stored_as_integer_minor_units():
    components = [TariffComponentInput(type="energy", price_minor_units=150, step_size=1)]

    total = calculate_session_cost(components, duration_minutes=0, kwh=15)

    assert isinstance(total, int)
    assert total == 2250

    from sqlalchemy import Integer

    assert isinstance(TariffComponent.__table__.columns["price_minor_units"].type, Integer)
