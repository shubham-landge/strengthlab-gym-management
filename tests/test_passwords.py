"""Temporary passwords must be random, single-use, and never phone-derived."""

import datetime
import re

import app as gym_app
from conftest import csrf_for


def post(client, path, **fields):
    fields["csrf_token"] = csrf_for(client, "/members")
    return client.post(path, data=fields)


def test_generated_passwords_are_random_and_long_enough():
    passwords = {gym_app.generate_temp_password() for _ in range(200)}
    assert len(passwords) == 200, "generated passwords must not repeat"
    assert all(len(p) >= 10 for p in passwords)


def test_generated_passwords_avoid_ambiguous_characters():
    sample = "".join(gym_app.generate_temp_password() for _ in range(200))
    for character in "0O1lI":
        assert character not in sample, f"{character!r} is easily misread"


def test_password_is_not_derived_from_the_phone_number(admin):
    """The old scheme was the last 4 digits of the mobile number."""
    phone = "+919000000401"
    post(admin, "/members/add", name="Random Pw Member", phone=phone,
         plan_name="Monthly", fitness_level="Beginner")
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members WHERE phone = ?", (phone,))
        user = gym_app.query_one(
            "SELECT * FROM users WHERE role = 'member' AND member_id = ?", (member["id"],)
        )
        assert user is not None
        assert not gym_app.check_password_hash(user["password_hash"], "0401")
        assert not gym_app.check_password_hash(user["password_hash"], phone[-4:])


def test_new_credentials_are_shown_once_then_cleared(admin):
    phone = "+919000000402"
    response = admin.post(
        "/members/add",
        data={"csrf_token": csrf_for(admin, "/members"), "name": "Shown Once",
              "phone": phone, "plan_name": "Monthly", "fitness_level": "Beginner"},
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert "shown once" in body.lower()
    match = re.search(r"password <code>([^<]+)</code>", body)
    assert match, "the issued password should be displayed"
    issued_password = match.group(1)

    # The credential must not appear again on a subsequent page load.
    again = admin.get("/members").get_data(as_text=True)
    assert issued_password not in again


def test_the_shown_password_actually_works(client, admin):
    phone = "+919000000403"
    response = admin.post(
        "/members/add",
        data={"csrf_token": csrf_for(admin, "/members"), "name": "Works Once",
              "phone": phone, "plan_name": "Monthly", "fitness_level": "Beginner"},
        follow_redirects=True,
    )
    issued = re.search(r"password <code>([^<]+)</code>", response.get_data(as_text=True)).group(1)
    login_id = gym_app.mobile_login_id(phone)

    token = csrf_for(client)
    signed_in = client.post(
        "/login", data={"username": login_id, "password": issued, "csrf_token": token}
    )
    assert signed_in.status_code == 302
    # First sign-in must force a password change.
    assert signed_in.headers["Location"].endswith("/change-password")


def test_reset_issues_a_new_password_and_invalidates_the_old(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        login = gym_app.get_member_login(member["id"])
        if login is None:
            gym_app.create_member_user(member["id"], member["phone"])
            login = gym_app.get_member_login(member["id"])
        first = gym_app.reset_user_password(login["id"], login["username"])
        second = gym_app.reset_user_password(login["id"], login["username"])
        refreshed = gym_app.query_one("SELECT * FROM users WHERE id = ?", (login["id"],))

    assert first != second
    assert not gym_app.check_password_hash(refreshed["password_hash"], first)
    assert gym_app.check_password_hash(refreshed["password_hash"], second)
    assert refreshed["must_change_password"] == 1


def test_seeding_outside_a_request_does_not_crash():
    """init_db() creates logins at startup with no session to stash them in."""
    assert not gym_app.has_request_context(), "this test needs a bare context"
    gym_app.remember_issued_credential("someone", "secret123")  # must be a no-op
    assert gym_app.take_issued_credentials() == []


# --- reset token expiry ------------------------------------------------------

def test_expired_reset_token_is_rejected(client):
    with gym_app.app.app_context():
        user = gym_app.query_one("SELECT * FROM users WHERE role = 'member' LIMIT 1")
        old_token = "expired-test-token"
        expired_at = (datetime.datetime.now() - datetime.timedelta(hours=gym_app.RESET_TOKEN_HOURS + 1)).strftime("%Y-%m-%d %H:%M:%S")
        gym_app.execute(
            "UPDATE users SET reset_token = ?, reset_token_created_at = ? WHERE id = ?",
            (old_token, expired_at, user["id"]),
        )
    response = client.get(f"/reset-password/{old_token}")
    assert b"Invalid or expired reset link" in response.data


def test_fresh_reset_token_is_accepted(client):
    with gym_app.app.app_context():
        user = gym_app.query_one("SELECT * FROM users WHERE role = 'member' LIMIT 1")
        fresh_token = "fresh-test-token"
        fresh_at = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        gym_app.execute(
            "UPDATE users SET reset_token = ?, reset_token_created_at = ? WHERE id = ?",
            (fresh_token, fresh_at, user["id"]),
        )
    response = client.get(f"/reset-password/{fresh_token}")
    assert response.status_code == 200
    assert b"Invalid or expired reset link" not in response.data
