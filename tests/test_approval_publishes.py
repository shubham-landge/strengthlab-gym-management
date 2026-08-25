"""Approving a plan must change what the member and staff screens display."""

import app as gym_app
from conftest import csrf_for


def prepared_member():
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            """
            UPDATE members SET wake_time='06:30', workout_time='18:30', sleep_time='23:00',
                   workout_plan='STALE WORKOUT', diet_plan='STALE DIET' WHERE id = ?
            """,
            (member["id"],),
        )
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        gym_app.execute(
            """
            UPDATE member_health_profiles SET kidney_disease=0, liver_disease=0,
                   medications='', pregnancy_lactation_status='' WHERE member_id = ?
            """,
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        gym_app.generate_plans(member, prefer_ai=False)
        return member


def approve(client, member_id, plan_type):
    with gym_app.app.app_context():
        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = ? AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (member_id, plan_type),
        )
    token = csrf_for(client, f"/members/{member_id}/plan/review")
    return client.post(
        f"/members/{member_id}/plan-versions/{version['id']}/approve",
        data={"csrf_token": token, "note": "ok"},
    ), version


def test_approving_replaces_the_stale_plan_text(admin):
    """The screens read members.workout_plan, which approval never updated."""
    member = prepared_member()
    response, _ = approve(admin, member["id"], "workout")
    assert response.status_code == 302

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT workout_plan FROM members WHERE id = ?", (member["id"],))
    assert after["workout_plan"] != "STALE WORKOUT", "approving must update what is displayed"
    assert after["workout_plan"].strip(), "and must not blank it"


def test_the_published_text_matches_the_approved_items(admin):
    member = prepared_member()
    _, version = approve(admin, member["id"], "workout")

    with gym_app.app.app_context():
        items = gym_app.query_all(
            "SELECT * FROM plan_items WHERE plan_version_id = ? ORDER BY position ASC", (version["id"],)
        )
        after = gym_app.query_one("SELECT workout_plan FROM members WHERE id = ?", (member["id"],))
    assert items
    assert items[0]["title"] in after["workout_plan"], "item titles should appear"
    assert "Why:" in after["workout_plan"], "reasons travel with the plan"


def test_the_member_profile_shows_the_approved_plan(admin):
    member = prepared_member()
    approve(admin, member["id"], "workout")
    body = admin.get(f"/members/{member['id']}").get_data(as_text=True)
    assert "STALE WORKOUT" not in body
    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT workout_plan FROM members WHERE id = ?", (member["id"],))
    assert after["workout_plan"].splitlines()[0] in body


def test_diet_approval_publishes_independently(admin):
    member = prepared_member()
    approve(admin, member["id"], "diet")
    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT workout_plan, diet_plan FROM members WHERE id = ?", (member["id"],))
    assert after["diet_plan"] != "STALE DIET", "the diet plan should be published"
    assert after["workout_plan"] == "STALE WORKOUT", "approving diet must not touch the workout plan"


def test_publishing_is_a_no_op_without_an_approved_version(admin):
    member = prepared_member()
    with gym_app.app.app_context():
        assert gym_app.publish_approved_plan_text(member["id"], "workout") is None
        after = gym_app.query_one("SELECT workout_plan FROM members WHERE id = ?", (member["id"],))
    assert after["workout_plan"] == "STALE WORKOUT", "drafts must never be published"


def test_approve_route_still_requires_a_role(client):
    """A refactor once moved the decorators onto a helper, leaving this open."""
    response = client.post("/members/1/plan-versions/1/approve", data={})
    assert response.status_code in (302, 400), "must not be reachable anonymously"
    assert response.status_code != 200


def test_helpers_are_not_registered_as_routes():
    endpoints = {rule.endpoint for rule in gym_app.app.url_map.iter_rules()}
    assert "render_plan_items_as_text" not in endpoints
    assert "publish_approved_plan_text" not in endpoints
    assert "approve_plan_version" in endpoints, "the real route must be registered"
