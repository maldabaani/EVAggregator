from __future__ import annotations

import uuid

from evagg.billing.payouts import PayoutRule, calculate_payout

OPERATOR_ID = uuid.uuid4()


def test_payout_split_percent_calculated_correctly():
    rule = PayoutRule(operator_id=OPERATOR_ID, site_id=None, split_type="percent", value=7500)  # 75%

    payout = calculate_payout(gross_revenue_minor_units=10000, rule=rule)

    assert payout == 7500


def test_payout_split_flat_fee_calculated_correctly():
    rule = PayoutRule(operator_id=OPERATOR_ID, site_id=None, split_type="flat_fee", value=2000)

    payout = calculate_payout(gross_revenue_minor_units=99999, rule=rule)

    assert payout == 2000  # flat fee is independent of gross revenue


def test_payout_split_percent_rounds_to_nearest_minor_unit():
    rule = PayoutRule(operator_id=OPERATOR_ID, site_id=None, split_type="percent", value=3333)  # 33.33%

    payout = calculate_payout(gross_revenue_minor_units=100, rule=rule)

    assert payout == round(100 * 3333 / 10_000)
