"""Money formatting and dues reconciliation."""

import pytest

import app as gym_app


@pytest.mark.parametrize(
    "value,expected",
    [
        (0, "0"),
        (2000.0, "2,000"),
        (999, "999"),
        (100000, "1,00,000"),
        (2500000, "25,00,000"),
        (-1500, "-1,500"),
        (None, "0"),
        ("not a number", "0"),
    ],
)
def test_format_money_uses_indian_grouping(value, expected):
    assert gym_app.format_money(value) == expected


def test_format_money_keeps_requested_decimals():
    assert gym_app.format_money(1234.5, decimals=2) == "1,234.50"


def test_plan_amount_falls_back_to_first_plan():
    assert gym_app.plan_amount("Quarterly") == 5500
    assert gym_app.plan_amount("Nonexistent") == gym_app.MEMBERSHIP_PLANS[0]["amount"]


def test_unpaid_members_without_invoices_still_count_as_dues(admin):
    """Regression: reports showed "N unpaid members" beside "Rs 0 outstanding"."""
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM payments")
        gym_app.execute("UPDATE members SET payment_status = 'Due', plan_name = 'Monthly'")
        unpaid = gym_app.query_one(
            "SELECT COUNT(*) AS count FROM members WHERE payment_status = 'Due'"
        )["count"]
        total = gym_app.outstanding_dues_total()

    assert unpaid > 0
    assert total == unpaid * 2000, "each uninvoiced unpaid member should contribute their plan fee"


def test_frozen_members_are_not_counted_as_dues(admin):
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM payments")
        gym_app.execute("UPDATE members SET payment_status = 'Frozen'")
        assert gym_app.outstanding_dues_total() == 0
