"""Plan UI screens: admin review, member view, and the approval gate as seen from the UI."""

import app as gym_app
from conftest import csrf_for


def get_member_id():
    with gym_app.app.app_context():
        return gym_app.query_one("SELECT id FROM members LIMIT 1")["id"]


def generate_plan(member_id):
    """Create a real draft plan version the way the app does."""
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member_id,))
        gym_app.generate_rule_based_plans(member)
        return gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? ORDER BY id DESC LIMIT 1",
            (member_id,),
        )


def test_member_plan_renders_empty_state_when_unapproved(admin):
    member_id = get_member_id()
    res = admin.get(f"/members/{member_id}/plan")
    assert res.status_code == 200
    assert b"Your coach is preparing your plan" in res.data


def test_review_screen_offers_generation_when_no_plan_exists(admin):
    """It must not fabricate a preview, and must not offer to approve nothing."""
    member_id = get_member_id()
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")

    res = admin.get(f"/members/{member_id}/plan/review")
    body = res.get_data(as_text=True)
    assert res.status_code == 200
    assert "No plan has been generated" in body
    assert "Generate plan" in body
    assert "Approve &amp; Publish Plan" not in body, "nothing exists to approve"


def test_review_screen_renders_real_generated_items(admin):
    member_id = get_member_id()
    version = generate_plan(member_id)

    res = admin.get(f"/members/{member_id}/plan/review")
    body = res.get_data(as_text=True)
    assert res.status_code == 200

    with gym_app.app.app_context():
        items = gym_app.query_all(
            "SELECT * FROM plan_items WHERE plan_version_id = ?", (version["id"],)
        )
    assert items, "generation should have produced items"
    assert items[0]["rationale"], "every item carries a rationale"


def test_blocked_plan_cannot_be_approved_from_the_ui(admin):
    """Posts to the real approve endpoint with a real blocked row - no mocks."""
    member_id = get_member_id()
    version = generate_plan(member_id)
    with gym_app.app.app_context():
        gym_app.execute(
            "UPDATE plan_versions SET status = 'blocked', blocked_reason = ? WHERE id = ?",
            ("Active kidney disease reported.", version["id"]),
        )

    token = csrf_for(admin, f"/members/{member_id}/plan/review")
    res = admin.post(
        f"/members/{member_id}/plan-versions/{version['id']}/approve",
        data={"csrf_token": token, "note": "trying anyway"},
    )
    assert res.status_code == 403

    with gym_app.app.app_context():
        after = gym_app.query_one(
            "SELECT status FROM plan_versions WHERE id = ?", (version["id"],)
        )
    assert after["status"] == "blocked", "it must stay blocked"


def test_blocked_plan_shows_no_approve_control(admin):
    member_id = get_member_id()
    version = generate_plan(member_id)
    with gym_app.app.app_context():
        gym_app.execute(
            "UPDATE plan_versions SET status = 'blocked', blocked_reason = ? WHERE id = ?",
            ("Pregnancy reported - clinician clearance required.", version["id"]),
        )

    body = admin.get(f"/members/{member_id}/plan/review").get_data(as_text=True)
    assert "Pregnancy reported" in body, "the reason must be visible"
    assert "Approve &amp; Publish Plan" not in body, "no action that cannot succeed"
