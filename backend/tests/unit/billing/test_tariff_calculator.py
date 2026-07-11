"""Task 3.1 unit tests for the pure tariff cost calculator."""

from __future__ import annotations

import pytest

from evagg.billing.tariff_calculator import TariffComponentInput, calculate_session_cost


def test_tariff_preview_calculates_correct_total_for_sample_session():
    # "30 min, 15 kWh" sample session per the backlog's own example.
    components = [
        TariffComponentInput(type="energy", price_minor_units=150, step_size=1),  # 1.50/kWh
        TariffComponentInput(type="time", price_minor_units=10, step_size=1),  # 0.10/min
        TariffComponentInput(type="flat", price_minor_units=200, step_size=1),  # startup fee
    ]

    total = calculate_session_cost(components, duration_minutes=30, kwh=15)

    # 15 * 150 + 30 * 10 + 200 = 2250 + 300 + 200 = 2750
    assert total == 2750


def test_idle_fee_zero_within_grace_period():
    components = [
        TariffComponentInput(type="energy", price_minor_units=150, step_size=1),
        TariffComponentInput(type="idle", price_minor_units=50, step_size=1, applies_after_minutes=10),
    ]

    total = calculate_session_cost(components, duration_minutes=30, kwh=15, idle_minutes=8)

    # idle_minutes (8) < grace period (10) -> idle contributes $0
    assert total == 15 * 150


def test_idle_fee_accrues_correctly_after_grace_period():
    components = [
        TariffComponentInput(type="energy", price_minor_units=150, step_size=1),
        TariffComponentInput(type="idle", price_minor_units=50, step_size=1, applies_after_minutes=10),
    ]

    total = calculate_session_cost(components, duration_minutes=30, kwh=15, idle_minutes=25)

    # billable idle = 25 - 10 = 15 minutes * 50 = 750
    assert total == 15 * 150 + 15 * 50


def test_idle_fee_exactly_at_grace_period_boundary_is_zero():
    components = [TariffComponentInput(type="idle", price_minor_units=50, step_size=1, applies_after_minutes=10)]

    total = calculate_session_cost(components, duration_minutes=0, kwh=0, idle_minutes=10)

    assert total == 0


def test_flat_component_applies_regardless_of_usage():
    components = [TariffComponentInput(type="flat", price_minor_units=500, step_size=1)]

    total = calculate_session_cost(components, duration_minutes=0, kwh=0)

    assert total == 500


def test_energy_component_respects_step_size():
    # price is per 5 kWh block
    components = [TariffComponentInput(type="energy", price_minor_units=100, step_size=5)]

    total = calculate_session_cost(components, duration_minutes=0, kwh=10)

    assert total == 200  # 10 kWh / 5 = 2 blocks * 100


def test_zero_step_size_raises():
    components = [TariffComponentInput(type="energy", price_minor_units=100, step_size=0)]

    with pytest.raises(ValueError):
        calculate_session_cost(components, duration_minutes=0, kwh=10)


def test_calculated_total_is_always_an_integer_minor_units_value():
    """Task 3.1's AC: monetary values stored as integer minor units, never
    float — the calculator itself must never hand back a float total."""
    components = [
        TariffComponentInput(type="energy", price_minor_units=133, step_size=1),
        TariffComponentInput(type="time", price_minor_units=7, step_size=3),
    ]

    total = calculate_session_cost(components, duration_minutes=10, kwh=3.7)

    assert isinstance(total, int)
