"""Generating a plan must produce a visible, non-duplicated result."""

import app as gym_app
from conftest import csrf_for


def premium_member():
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            """
            UPDATE members SET wake_time='06:30', workout_time='18:30', sleep_time='23:00',
                   workout_subscription='Premium', diet_subscription='Premium' WHERE id = ?
            """,
            (member["id"],),
        )
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        # Other test modules leave contraindications on this member's health
        # profile, which would make every generated plan come out 'blocked'
        # instead of 'draft'. Clear them so this file tests generation, not the gate.
        gym_app.execute(
            """
            UPDATE member_health_profiles
            SET kidney_disease = 0, liver_disease = 0, medications = '',
                pregnancy_lactation_status = ''
            WHERE member_id = ?
            """,
            (member["id"],),
        )
        return gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))


def test_generation_creates_one_version_per_plan_type(admin):
    """Each fallback used to persist both types, so one generation left four."""
    member = premium_member()
    with gym_app.app.app_context():
        gym_app.generate_plans(member, prefer_ai=True)
        rows = gym_app.query_all("SELECT plan_type, COUNT(*) AS n FROM plan_versions GROUP BY plan_type")
    counts = {r["plan_type"]: r["n"] for r in rows}
    assert counts == {"workout": 1, "diet": 1}, f"expected one each, got {counts}"


def test_regenerating_does_not_pile_up_drafts(admin):
    member = premium_member()
    with gym_app.app.app_context():
        for _ in range(3):
            gym_app.generate_plans(member, prefer_ai=True)
        drafts = gym_app.query_one(
            "SELECT COUNT(*) AS n FROM plan_versions WHERE status = 'draft'"
        )["n"]
    # Three generations of two plan types: six drafts, not twelve.
    assert drafts == 6, f"expected 6 drafts across 3 runs, got {drafts}"


def test_admin_is_told_when_no_ai_is_configured(admin, monkeypatch):
    """Silent fallback is why generation looked like it did nothing."""
    monkeypatch.setattr(gym_app, "ai_generation_enabled", lambda: False)
    member = premium_member()
    token = csrf_for(admin, "/members")
    response = admin.post(
        f"/members/{member['id']}/regenerate",
        data={"csrf_token": token},
        follow_redirects=True,
    )
    body = response.get_data(as_text=True)
    assert "No AI provider is configured" in body


def test_generation_lands_on_the_review_screen(admin):
    """It used to redirect to the profile, where the new draft is not shown."""
    member = premium_member()
    token = csrf_for(admin, "/members")
    response = admin.post(
        f"/members/{member['id']}/regenerate", data={"csrf_token": token}
    )
    assert response.status_code == 302
    assert response.headers["Location"].endswith(f"/members/{member['id']}/plan/review")


def test_review_screen_shows_both_plan_types(admin):
    """Only the first type was rendered, so the diet plan was invisible."""
    member = premium_member()
    with gym_app.app.app_context():
        gym_app.generate_plans(member, prefer_ai=True)

    body = admin.get(f"/members/{member['id']}/plan/review").get_data(as_text=True)
    assert "Workout plan" in body
    assert "Diet plan" in body
    assert "Approve &amp; publish workout" in body
    assert "Approve &amp; publish diet" in body


def test_every_rendered_item_shows_its_reason(admin):
    member = premium_member()
    with gym_app.app.app_context():
        gym_app.generate_plans(member, prefer_ai=True)
        items = gym_app.query_all("SELECT * FROM plan_items")

    body = admin.get(f"/members/{member['id']}/plan/review").get_data(as_text=True)
    assert "Why this, and why now" in body
    assert items, "generation should have produced items"
    for item in items[:5]:
        assert item["rationale"], "no item may lack a rationale"


def test_notes_are_shown_once_then_cleared(admin, monkeypatch):
    monkeypatch.setattr(gym_app, "ai_generation_enabled", lambda: False)
    member = premium_member()
    token = csrf_for(admin, "/members")
    first = admin.post(
        f"/members/{member['id']}/regenerate",
        data={"csrf_token": token}, follow_redirects=True,
    ).get_data(as_text=True)
    assert "No AI provider is configured" in first

    again = admin.get(f"/members/{member['id']}/plan/review").get_data(as_text=True)
    assert "No AI provider is configured" not in again, "the note must not persist"
