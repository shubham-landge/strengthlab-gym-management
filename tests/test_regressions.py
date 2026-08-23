"""Regression tests for the bugs found in the logic review.

Each test names the defect it locks down; all of them failed before the fix.
"""

import datetime

import pytest

import app as gym_app
from conftest import csrf_for


def post(client, path, **fields):
    fields["csrf_token"] = csrf_for(client, "/members")
    return client.post(path, data=fields)


# --- missing records must 404, not 500 -------------------------------------

@pytest.mark.parametrize(
    "path",
    [
        "/payments/999999/receipt.pdf",
        "/members/999999/edit",
        "/trainers/999999/edit",
        "/equipment/999999/edit",
    ],
)
def test_unknown_ids_return_404_not_500(admin, path):
    assert admin.get(path).status_code == 404


def test_editing_a_missing_equipment_item_cannot_silently_succeed(admin):
    """It used to render a blank form and report a successful save."""
    response = post(admin, "/equipment/999999/edit", name="Ghost", quantity="1")
    assert response.status_code == 404


# --- membership length must follow the chosen plan -------------------------

@pytest.mark.parametrize(
    "plan,expected_days",
    [("Monthly", 30), ("Quarterly", 90), ("Annual", 365)],
)
def test_subscription_length_matches_the_selected_plan(admin, plan, expected_days):
    phone = {"Monthly": "9000000101", "Quarterly": "9000000102", "Annual": "9000000103"}[plan]
    post(admin, "/members/add", name=f"{plan} Member", phone=phone, plan_name=plan, fitness_level="Beginner")
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members WHERE phone = ?", (phone,))
    start = datetime.date.fromisoformat(member["subscription_start"])
    end = datetime.date.fromisoformat(member["subscription_end"])
    assert (end - start).days + 1 == expected_days


# --- invoice numbers must never repeat -------------------------------------

def test_invoice_numbers_are_not_reused_after_a_deletion(admin):
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM payments")
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        first = gym_app.create_membership_renewal(member, {}, send_whatsapp=False)
        second = gym_app.create_membership_renewal(member, {}, send_whatsapp=False)
        gym_app.execute("DELETE FROM payments WHERE id = ?", (first["payment_id"],))
        third = gym_app.create_membership_renewal(member, {}, send_whatsapp=False)

    assert third["invoice_number"] != second["invoice_number"]
    assert third["invoice_number"] > second["invoice_number"]


def test_duplicate_invoice_numbers_are_rejected_by_the_database(admin):
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM payments")
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        issued = gym_app.create_membership_renewal(member, {}, send_whatsapp=False)
        with pytest.raises(Exception):
            gym_app.execute(
                "INSERT INTO payments (member_id, invoice_number, amount, status) VALUES (?, ?, ?, 'Received')",
                (member["id"], issued["invoice_number"], 100),
            )


# --- unfreeze must not leave an active membership marked unpaid ------------

def test_unfreeze_status_reflects_the_extended_expiry(admin):
    today = datetime.date.today()
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET subscription_end = ?, payment_status = 'Frozen' WHERE id = ?",
            ((today - datetime.timedelta(days=5)).isoformat(), member["id"]),
        )
        gym_app.execute("DELETE FROM membership_freezes WHERE member_id = ?", (member["id"],))
        gym_app.execute(
            "INSERT INTO membership_freezes (member_id, frozen_on, previous_status) VALUES (?, ?, 'Paid')",
            (member["id"], (today - datetime.timedelta(days=20)).isoformat()),
        )

    post(admin, f"/members/{member['id']}/unfreeze", extend_expiry="1")

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
    expiry = datetime.date.fromisoformat(after["subscription_end"])
    assert expiry >= today, "frozen days should be credited back"
    assert after["payment_status"] == "Paid", "an active membership must not read as unpaid"


def test_restored_status_is_computed_from_the_expiry_passed_in():
    future = (datetime.date.today() + datetime.timedelta(days=5)).isoformat()
    past = (datetime.date.today() - datetime.timedelta(days=5)).isoformat()
    assert gym_app.restored_payment_status(future) == "Paid"
    assert gym_app.restored_payment_status(past) == "Due"
    assert gym_app.restored_payment_status(None) == "Due"
    assert gym_app.restored_payment_status("not-a-date") == "Due"


# --- settling one invoice must not clear other outstanding ones ------------

def test_member_stays_due_while_another_invoice_is_outstanding(admin):
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM payments")
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO payments (member_id, invoice_number, amount, status, due_on) VALUES (?, 'INV-A', 2000, 'Due', ?)",
            (member["id"], datetime.date.today().isoformat()),
        )
        gym_app.execute(
            "INSERT INTO payments (member_id, invoice_number, amount, status, due_on) VALUES (?, 'INV-B', 2000, 'Due', ?)",
            (member["id"], datetime.date.today().isoformat()),
        )
        paid_id = gym_app.query_one("SELECT id FROM payments WHERE invoice_number = 'INV-A'")["id"]

    post(admin, "/payments/batch-action", action="mark_paid", payment_ids=str(paid_id))

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT payment_status FROM members WHERE id = ?", (member["id"],))
    assert after["payment_status"] == "Due", "INV-B is still unpaid"


def test_member_becomes_paid_once_nothing_is_outstanding(admin):
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM payments")
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute("UPDATE members SET payment_status = 'Due' WHERE id = ?", (member["id"],))
        gym_app.execute(
            "INSERT INTO payments (member_id, invoice_number, amount, status) VALUES (?, 'INV-ONLY', 2000, 'Due')",
            (member["id"],),
        )
        only_id = gym_app.query_one("SELECT id FROM payments WHERE invoice_number = 'INV-ONLY'")["id"]

    post(admin, "/payments/batch-action", action="mark_paid", payment_ids=str(only_id))

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT payment_status FROM members WHERE id = ?", (member["id"],))
    assert after["payment_status"] == "Paid"


def test_sync_never_unfreezes_a_frozen_member(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute("DELETE FROM payments")
        gym_app.execute("UPDATE members SET payment_status = 'Frozen' WHERE id = ?", (member["id"],))
        gym_app.sync_member_payment_status(member["id"])
        after = gym_app.query_one("SELECT payment_status FROM members WHERE id = ?", (member["id"],))
    assert after["payment_status"] == "Frozen"


# --- notification dedup ----------------------------------------------------

def test_duplicate_event_keys_are_queued_only_once(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        key = "test-event:once"
        gym_app.execute("DELETE FROM notifications WHERE event_key = ?", (key,))
        first = gym_app.log_notification(member["id"], "first", event_key=key)
        second = gym_app.log_notification(member["id"], "second", event_key=key)
        count = gym_app.query_one(
            "SELECT COUNT(*) AS count FROM notifications WHERE event_key = ?", (key,)
        )["count"]
    assert first is True
    assert second is False
    assert count == 1


def test_notifications_without_an_event_key_are_never_deduped(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        before = gym_app.query_one("SELECT COUNT(*) AS count FROM notifications")["count"]
        gym_app.log_notification(member["id"], "ad-hoc broadcast")
        gym_app.log_notification(member["id"], "ad-hoc broadcast")
        after = gym_app.query_one("SELECT COUNT(*) AS count FROM notifications")["count"]
    assert after == before + 2


# --- lapsed members stop being chased --------------------------------------

def test_long_lapsed_members_are_no_longer_reminded(admin):
    long_ago = (datetime.date.today() - datetime.timedelta(days=400)).isoformat()
    recent = (datetime.date.today() - datetime.timedelta(days=3)).isoformat()
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM notifications")
        gym_app.execute("DELETE FROM payments")
        gym_app.execute("UPDATE members SET payment_status = 'Paid'")
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET payment_status = 'Due', subscription_end = ? WHERE id = ?",
            (long_ago, member["id"]),
        )
        gym_app.queue_payment_due_reminders()
        lapsed_count = gym_app.query_one(
            "SELECT COUNT(*) AS count FROM notifications WHERE member_id = ?", (member["id"],)
        )["count"]

        # A recently lapsed member should still be chased.
        gym_app.execute("DELETE FROM notifications")
        gym_app.execute(
            "UPDATE members SET subscription_end = ? WHERE id = ?", (recent, member["id"])
        )
        gym_app.queue_payment_due_reminders()
        recent_count = gym_app.query_one(
            "SELECT COUNT(*) AS count FROM notifications WHERE member_id = ?", (member["id"],)
        )["count"]

    assert lapsed_count == 0, "a member gone for 400 days should not be chased daily"
    assert recent_count > 0, "a recently lapsed member should still get a reminder"


# --- shared phone numbers must not steal a login ---------------------------

def test_second_member_on_a_shared_phone_does_not_steal_the_login(admin):
    phone = "+919000000201"
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM users WHERE username = ?", ("9000000201",))

    post(admin, "/members/add", name="First Sibling", phone=phone, plan_name="Monthly", fitness_level="Beginner")
    with gym_app.app.app_context():
        first = gym_app.query_one("SELECT * FROM members WHERE name = 'First Sibling'")
        login = gym_app.get_member_login(first["id"])
    assert login is not None, "the first member should own the mobile login"

    post(admin, "/members/add", name="Second Sibling", phone=phone, plan_name="Monthly", fitness_level="Beginner")
    with gym_app.app.app_context():
        second = gym_app.query_one("SELECT * FROM members WHERE name = 'Second Sibling'")
        first_login_after = gym_app.get_member_login(first["id"])
        second_login = gym_app.get_member_login(second["id"])

    assert first_login_after is not None, "the original member must keep their login"
    assert first_login_after["id"] == login["id"]
    assert second_login is None, "the newcomer must not take over the shared number"


def test_a_member_keeps_their_own_login_when_details_are_resaved(admin):
    phone = "+919000000202"
    post(admin, "/members/add", name="Solo Member", phone=phone, plan_name="Monthly", fitness_level="Beginner")
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members WHERE name = 'Solo Member'")
        before = gym_app.get_member_login(member["id"])
        # Re-running the sync for the same member must be a no-op, not a lockout.
        gym_app.create_member_user(member["id"], phone)
        after = gym_app.get_member_login(member["id"])
    assert before is not None and after is not None
    assert before["id"] == after["id"]


# --- renewals are written atomically ---------------------------------------

def test_failed_renewal_leaves_no_partial_record(admin):
    """The failure is injected *after* the payment row is written.

    Renaming renewal_history makes the final INSERT of the renewal fail, which is
    the realistic shape of a mid-operation error: money already recorded, the rest
    of the work still pending.
    """
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM payments")
        gym_app.execute("DELETE FROM renewal_history")
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET payment_status = 'Due', subscription_end = ? WHERE id = ?",
            ("2020-01-01", member["id"]),
        )
        gym_app.execute("ALTER TABLE renewal_history RENAME TO renewal_history_backup")
        try:
            with pytest.raises(Exception):
                gym_app.create_membership_renewal(member, {}, send_whatsapp=False)
            payments = gym_app.query_one("SELECT COUNT(*) AS count FROM payments")["count"]
            after = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        finally:
            gym_app.execute("ALTER TABLE renewal_history_backup RENAME TO renewal_history")

    assert payments == 0, "no orphan payment should survive a failed renewal"
    assert after["payment_status"] == "Due", "membership must not look renewed"
    assert after["subscription_end"] == "2020-01-01", "expiry must not move"


def test_successful_renewal_writes_all_three_records(admin):
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM payments")
        gym_app.execute("DELETE FROM renewal_history")
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        result = gym_app.create_membership_renewal(member, {}, send_whatsapp=False)
        payments = gym_app.query_one("SELECT COUNT(*) AS count FROM payments")["count"]
        history = gym_app.query_one("SELECT COUNT(*) AS count FROM renewal_history")["count"]
        after = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
    assert payments == 1 and history == 1
    assert after["payment_status"] == "Paid"
    assert after["subscription_end"] == result["renewal_end"]
