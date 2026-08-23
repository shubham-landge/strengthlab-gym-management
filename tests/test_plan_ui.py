"""
Tests for Plan UI screens: Admin Plan Review, Member Plan View, and audit logging.
"""
import pytest
import app as gym_app
from conftest import csrf_for


def get_member_id():
    with gym_app.app.app_context():
        return gym_app.query_one("SELECT id FROM members LIMIT 1")["id"]


def test_member_plan_renders_empty_state_when_unapproved(admin):
    member_id = get_member_id()
    res = admin.get(f"/members/{member_id}/plan")
    assert res.status_code == 200
    assert b"Your coach is preparing your plan" in res.data
    assert b"Circadian Blueprint" in res.data


def test_admin_plan_review_renders_circadian_items(admin):
    member_id = get_member_id()
    res = admin.get(f"/members/{member_id}/plan/review")
    assert res.status_code == 200
    assert b"Review Plan:" in res.data
    assert b"Circadian Schedule" in res.data or b"Wake" in res.data
    assert b"Item Rationale" in res.data


def test_blocked_plan_returns_403_on_approve_attempt(admin, monkeypatch):
    member_id = get_member_id()

    orig_query_one = gym_app.query_one
    def mock_query(sql, args=()):
        if "plan_versions" in sql:
            return {
                "id": 99,
                "member_id": member_id,
                "plan_type": "workout",
                "status": "blocked",
                "blocked_reason": "Active kidney disease reported."
            }
        return orig_query_one(sql, args)

    monkeypatch.setattr(gym_app, "query_one", mock_query)

    token = csrf_for(admin, f"/members/{member_id}/plan/review")
    res = admin.post(
        f"/members/{member_id}/plan/review",
        data={"csrf_token": token, "action": "approve_all"}
    )
    assert res.status_code == 403
    assert b"Plan is blocked" in res.data
