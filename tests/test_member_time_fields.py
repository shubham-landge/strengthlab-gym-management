"""Tests that wake_time, sleep_time, and workout_time are persisted on member create and edit."""

import app as gym_app
from conftest import csrf_for


def post(client, path, **fields):
    fields["csrf_token"] = csrf_for(client, "/members")
    return client.post(path, data=fields)


def test_add_member_persists_time_fields(admin):
    post(
        admin,
        "/members/add",
        name="Time Member",
        phone="9000000200",
        plan_name="Monthly",
        fitness_level="Beginner",
        wake_time="06:00",
        sleep_time="22:00",
        workout_time="07:00",
    )
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members WHERE phone = ?", ("9000000200",))
    assert member["wake_time"] == "06:00"
    assert member["sleep_time"] == "22:00"
    assert member["workout_time"] == "07:00"


def test_add_member_without_time_fields_still_works(admin):
    post(
        admin,
        "/members/add",
        name="No Time Member",
        phone="9000000201",
        plan_name="Monthly",
        fitness_level="Beginner",
    )
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members WHERE phone = ?", ("9000000201",))
    assert member["wake_time"] is None
    assert member["sleep_time"] is None
    assert member["workout_time"] is None


def test_edit_member_persists_time_fields(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
    post(
        admin,
        f"/members/{member['id']}/edit",
        name=member["name"],
        phone=member["phone"],
        plan_name=member["plan_name"] or "Monthly",
        fitness_level="Beginner",
        wake_time="05:30",
        sleep_time="21:30",
        workout_time="06:30",
    )
    with gym_app.app.app_context():
        updated = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
    assert updated["wake_time"] == "05:30"
    assert updated["sleep_time"] == "21:30"
    assert updated["workout_time"] == "06:30"


def test_edit_member_without_time_fields_still_works(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
    post(
        admin,
        f"/members/{member['id']}/edit",
        name=member["name"],
        phone=member["phone"],
        plan_name=member["plan_name"] or "Monthly",
        fitness_level="Beginner",
    )
    with gym_app.app.app_context():
        updated = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
    # Time fields should be cleared when omitted on edit (form sends empty string -> None via .get())
    assert updated["wake_time"] is None
    assert updated["sleep_time"] is None
    assert updated["workout_time"] is None
