import re
import pytest
import app as gym_app
from conftest import csrf_for

def test_logging_a_set_creates_set_logs_row(admin):
    # Setup approved plan and item for member 1
    with gym_app.app.app_context():
        gym_app.ensure_plan_views_schema()
        # Insert test approved plan version
        cursor = gym_app.db().execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance) VALUES (1, 'workout', 'approved', 'admin')"
        )
        version_id = cursor.lastrowid
        cursor_item = gym_app.db().execute(
            "INSERT INTO plan_items (plan_version_id, item_type, title, sets, set_count, reps, rest_seconds, rationale, provenance) VALUES (?, 'exercise', 'Bench Press', '3', 3, '8-12', 90, 'Test rationale', 'admin')",
            (version_id,)
        )
        item_id = cursor_item.lastrowid
        gym_app.db().commit()

    token = csrf_for(admin, "/members/1/plan")
    rv = admin.post(
        "/members/1/log-set",
        data={
            "csrf_token": token,
            "plan_item_id": item_id,
            "set_number": 1,
            "load_kg": "55.5",
            "reps_done": "10",
        },
        follow_redirects=True,
    )
    assert rv.status_code == 200

    with gym_app.app.app_context():
        log_row = gym_app.query_one("SELECT * FROM set_logs WHERE plan_item_id = ? AND set_number = 1", (item_id,))
        assert log_row is not None
        assert log_row["load_kg"] == 55.5
        assert log_row["reps_done"] == 10
        assert log_row["member_id"] == 1

def test_editing_a_cell_changes_column_and_marks_provenance_admin(admin):
    with gym_app.app.app_context():
        gym_app.ensure_plan_views_schema()
        cursor = gym_app.db().execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance) VALUES (1, 'workout', 'draft', 'ai')"
        )
        version_id = cursor.lastrowid
        cursor_item = gym_app.db().execute(
            "INSERT INTO plan_items (plan_version_id, item_type, title, sets, reps, rpe, rationale, provenance) VALUES (?, 'exercise', 'Incline Press', '3', '8-12', '7', 'Initial', 'ai')",
            (version_id,)
        )
        item_id = cursor_item.lastrowid
        gym_app.db().commit()

    token = csrf_for(admin, "/members/1/plan/review")
    rv = admin.post(
        f"/members/1/plan-items/{item_id}/update-cell",
        data={
            "csrf_token": token,
            "field": "rpe",
            "value": "8-9",
        },
        follow_redirects=True,
    )
    assert rv.status_code == 200

    with gym_app.app.app_context():
        updated = gym_app.query_one("SELECT * FROM plan_items WHERE id = ?", (item_id,))
        assert updated["rpe"] == "8-9"
        assert updated["provenance"] == "admin"

def test_weekly_volume_renders_range_and_flags_out_of_range(admin):
    with gym_app.app.app_context():
        gym_app.ensure_plan_views_schema()
        cursor = gym_app.db().execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance) VALUES (1, 'workout', 'draft', 'ai')"
        )
        version_id = cursor.lastrowid
        # Add 3 chest sets (min is 10, so should flag 'under')
        gym_app.db().execute(
            "INSERT INTO plan_items (plan_version_id, item_type, title, sets, set_count, muscle_group, rationale, provenance) VALUES (?, 'exercise', 'Chest Press', '3', 3, 'chest', 'Rationale', 'ai')",
            (version_id,)
        )
        gym_app.db().commit()

        vol = gym_app.weekly_volume(1, version_id)
        chest_vol = next(v for v in vol if v["muscle_group"] == "chest")
        assert chest_vol["sets"] == 3
        assert chest_vol["min"] == 10
        assert chest_vol["status"] == "under"

    rv = admin.get("/members/1/plan/review")
    assert rv.status_code == 200
    html = rv.data.decode("utf-8")
    assert "Weekly Sets Per Muscle Group" in html
    assert "chest" in html

def test_blocked_plan_renders_no_approve_control(admin):
    with gym_app.app.app_context():
        gym_app.ensure_plan_views_schema()
        cursor = gym_app.db().execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, blocked_reason, provenance) VALUES (1, 'workout', 'blocked', 'Cardiac contraindication', 'rule')"
        )
        version_id = cursor.lastrowid
        gym_app.db().commit()

    rv = admin.get("/members/1/plan/review")
    assert rv.status_code == 200
    html = rv.data.decode("utf-8")

    # Assert no approve form exists for this blocked plan version
    approve_form_action = f'/members/1/plan-versions/{version_id}/approve'
    assert approve_form_action not in html
    assert "Clinical Safety Gate Triggered — Plan Blocked" in html

def test_plan_views_anchor_targets_exist(admin):
    rv_member = admin.get("/members/1/plan")
    assert rv_member.status_code == 200
    html_member = rv_member.data.decode("utf-8")
    for target in re.findall(r'href="#([a-zA-Z0-9_-]+)"', html_member):
        if not target: continue
        assert f'id="{target}"' in html_member, f"Link target #{target} does not exist in member_plan.html"

    rv_review = admin.get("/members/1/plan/review")
    assert rv_review.status_code == 200
    html_review = rv_review.data.decode("utf-8")
    for target in re.findall(r'href="#([a-zA-Z0-9_-]+)"', html_review):
        if not target: continue
        assert f'id="{target}"' in html_review, f"Link target #{target} does not exist in plan_review.html"
