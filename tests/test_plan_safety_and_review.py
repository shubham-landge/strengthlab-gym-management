"""Phase 4 — Safety gate and approval tests.

Covers:
- Safety gate blocks plan generation for high-risk health profiles
- Blocked plans return 403 on approve for admin and owner
- No force/override bypass exists
- Approve supersedes prior approved version
- Reject requires a note and writes audit row
- Edit writes audit row with before/after JSON
- Member-facing plan retrieval reads approved versions only
- Honest empty state when no approved version exists
- Recommendation review approve/reject append audit rows
"""

import json
import pytest

import app as gym_app
from conftest import csrf_for


def post(client, path, source="/login", **fields):
    fields["csrf_token"] = csrf_for(client, source)
    return client.post(path, data=fields, follow_redirects=False)


@pytest.fixture(autouse=True)
def clean_plan_versions(admin):
    """Remove all plan_versions and plan_reviews before each test."""
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "DELETE FROM plan_items WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ?)",
            (member["id"],),
        )
        gym_app.execute(
            "DELETE FROM plan_reviews WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ?)",
            (member["id"],),
        )
        gym_app.execute(
            "DELETE FROM plan_versions WHERE member_id = ?",
            (member["id"],),
        )
        gym_app.execute(
            "DELETE FROM recommendation_reviews WHERE recommendation_id IN (SELECT id FROM member_recommendations WHERE member_id = ?)",
            (member["id"],),
        )
        gym_app.execute(
            "DELETE FROM member_recommendations WHERE member_id = ?",
            (member["id"],),
        )


# --- safety gate during plan generation ---------------------------------------

def test_pregnancy_blocks_plan_generation(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        from services.clinical_recommendation_service import get_or_create_health_profile
        get_or_create_health_profile(gym_app.db(), member["id"])
        gym_app.execute(
            "UPDATE member_health_profiles SET pregnancy_lactation_status = 'Yes' WHERE member_id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        gym_app.generate_rule_based_plans(member)

        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
    assert version is not None
    assert version["status"] == "blocked"
    assert "clinician clearance" in (version["blocked_reason"] or "")


def test_kidney_disease_blocks_plan_generation(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE member_health_profiles SET kidney_disease = 1 WHERE member_id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        gym_app.generate_rule_based_plans(member)

        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'diet' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
    assert version is not None
    assert version["status"] == "blocked"
    assert "kidney" in (version["blocked_reason"] or "").lower()


def test_healthy_member_gets_draft_plan(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE member_health_profiles SET pregnancy_lactation_status = '', kidney_disease = 0, liver_disease = 0, medications = '' WHERE member_id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        gym_app.generate_rule_based_plans(member)

        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
    assert version is not None
    assert version["status"] == "draft"
    assert version["blocked_reason"] is None


# --- blocked plan approval returns 403 ----------------------------------------

def test_admin_cannot_approve_blocked_plan(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at, blocked_reason) VALUES (?, 'workout', 'blocked', 'rule', datetime('now'), 'Blocked for safety')",
            (member["id"],),
        )
        version = gym_app.query_one("SELECT * FROM plan_versions WHERE member_id = ? AND status = 'blocked'", (member["id"],))

    response = post(admin, f"/members/{member['id']}/plan-versions/{version['id']}/approve", source="/members")
    assert response.status_code == 403

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT status FROM plan_versions WHERE id = ?", (version["id"],))
    assert after["status"] == "blocked"


def test_owner_cannot_approve_blocked_plan(admin):
    # Sign in as owner using a fresh client
    gym_app.app.config["TESTING"] = True
    client = gym_app.app.test_client()
    with gym_app.app.app_context():
        owner = gym_app.query_one("SELECT * FROM users WHERE role = 'owner' LIMIT 1")
        # Ensure owner can log in with the seeded password
        gym_app.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0, active = 1 WHERE id = ?",
            (gym_app.generate_password_hash("owner123"), owner["id"]),
        )
    token = csrf_for(client)
    client.post(
        "/login",
        data={"username": owner["username"], "password": "owner123", "csrf_token": token},
        follow_redirects=False,
    )

    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at, blocked_reason) VALUES (?, 'workout', 'blocked', 'rule', datetime('now'), 'Blocked for safety')",
            (member["id"],),
        )
        version = gym_app.query_one("SELECT * FROM plan_versions WHERE member_id = ? AND status = 'blocked'", (member["id"],))

    response = post(client, f"/members/{member['id']}/plan-versions/{version['id']}/approve", source="/members")
    assert response.status_code == 403

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT status FROM plan_versions WHERE id = ?", (version["id"],))
    assert after["status"] == "blocked"


def test_no_force_parameter_bypasses_block(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at, blocked_reason) VALUES (?, 'workout', 'blocked', 'rule', datetime('now'), 'Blocked for safety')",
            (member["id"],),
        )
        version = gym_app.query_one("SELECT * FROM plan_versions WHERE member_id = ? AND status = 'blocked'", (member["id"],))

    response = post(admin, f"/members/{member['id']}/plan-versions/{version['id']}/approve", source="/members", force="1", override="true")
    assert response.status_code == 403


def test_blocked_reason_non_null_blocks_approve_even_if_status_changed(admin):
    """Canonical guard is blocked_reason, not status. If status is manually
    changed to draft but blocked_reason remains set, approval must still 403.
    """
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at, blocked_reason) VALUES (?, 'workout', 'draft', 'rule', datetime('now'), 'Pregnancy/lactation')",
            (member["id"],),
        )
        version = gym_app.query_one("SELECT * FROM plan_versions WHERE member_id = ? AND status = 'draft'", (member["id"],))

    response = post(admin, f"/members/{member['id']}/plan-versions/{version['id']}/approve", source="/members", note="Trying anyway")
    assert response.status_code == 403

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT status FROM plan_versions WHERE id = ?", (version["id"],))
    assert after["status"] == "draft"


# --- approve, supersede, and audit --------------------------------------------

def test_approve_supersedes_prior_approved_version(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        # Seed an older approved version
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        old_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        # Seed a draft to approve
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'draft', 'rule', datetime('now'))",
            (member["id"],),
        )
        new_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(admin, f"/members/{member['id']}/plan-versions/{new_id}/approve", source="/members", note="Looks good")
    assert response.status_code == 302

    with gym_app.app.app_context():
        old = gym_app.query_one("SELECT status FROM plan_versions WHERE id = ?", (old_id,))
        new = gym_app.query_one("SELECT status FROM plan_versions WHERE id = ?", (new_id,))
        approved_count = gym_app.query_one(
            "SELECT COUNT(*) AS count FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' AND status = 'approved'",
            (member["id"],),
        )["count"]
    assert old["status"] == "superseded"
    assert new["status"] == "approved"
    assert approved_count == 1


def test_approve_writes_plan_reviews_audit_row(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'draft', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(admin, f"/members/{member['id']}/plan-versions/{version_id}/approve", source="/members", note="Approved by admin")
    assert response.status_code == 302

    with gym_app.app.app_context():
        audit = gym_app.query_one(
            "SELECT * FROM plan_reviews WHERE plan_version_id = ? ORDER BY id DESC LIMIT 1",
            (version_id,),
        )
    assert audit is not None
    assert audit["action"] == "approve"
    assert audit["note"] == "Approved by admin"
    assert json.loads(audit["before_json"]) == {"status": "draft"}
    assert json.loads(audit["after_json"]) == {"status": "approved"}


# --- reject and audit ---------------------------------------------------------

def test_reject_requires_note(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'draft', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(admin, f"/members/{member['id']}/plan-versions/{version_id}/reject", source="/members")
    assert response.status_code == 302  # redirects with flash error

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT status FROM plan_versions WHERE id = ?", (version_id,))
    assert after["status"] == "draft"


def test_reject_with_note_writes_audit_row(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'draft', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(admin, f"/members/{member['id']}/plan-versions/{version_id}/reject", source="/members", note="Too aggressive")
    assert response.status_code == 302

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT status FROM plan_versions WHERE id = ?", (version_id,))
        audit = gym_app.query_one(
            "SELECT * FROM plan_reviews WHERE plan_version_id = ? ORDER BY id DESC LIMIT 1",
            (version_id,),
        )
    assert after["status"] == "rejected"
    assert audit["action"] == "reject"
    assert audit["note"] == "Too aggressive"


# --- edit and audit -----------------------------------------------------------

def test_edit_writes_plan_reviews_audit_row_with_before_after(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at, review_note) VALUES (?, 'workout', 'draft', 'rule', datetime('now'), 'Old note')",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(admin, f"/members/{member['id']}/plan-versions/{version_id}/edit", source="/members", note="Updated rationale", status="pending_review")
    assert response.status_code == 302

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT status, review_note FROM plan_versions WHERE id = ?", (version_id,))
        audit = gym_app.query_one(
            "SELECT * FROM plan_reviews WHERE plan_version_id = ? ORDER BY id DESC LIMIT 1",
            (version_id,),
        )
    assert after["status"] == "pending_review"
    assert after["review_note"] == "Updated rationale"
    assert audit["action"] == "edit"
    before = json.loads(audit["before_json"])
    after_json = json.loads(audit["after_json"])
    assert before["status"] == "draft"
    assert before["review_note"] == "Old note"
    assert after_json["status"] == "pending_review"
    assert after_json["review_note"] == "Updated rationale"


def test_edit_cannot_approve_blocked_plan(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at, blocked_reason) VALUES (?, 'workout', 'draft', 'rule', datetime('now'), 'Pregnancy')",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(admin, f"/members/{member['id']}/plan-versions/{version_id}/edit", source="/members", note="Should fail", status="approved")
    assert response.status_code == 302

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT status FROM plan_versions WHERE id = ?", (version_id,))
    assert after["status"] == "draft"


# --- item edit ----------------------------------------------------------------

def test_item_edit_updates_title_detail_rationale(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'draft', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            "INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, position) VALUES (?, 'Day 1', 'exercise', 'Old Title', 'Old Detail', 'Old Rationale', 0)",
            (version_id,),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(
        admin,
        f"/members/{member['id']}/plan-versions/{version_id}/items/{item_id}/edit",
        source="/members",
        title="New Title",
        detail="New Detail",
        rationale="New Rationale",
    )
    assert response.status_code == 302

    with gym_app.app.app_context():
        item = gym_app.query_one("SELECT * FROM plan_items WHERE id = ?", (item_id,))
        version = gym_app.query_one("SELECT provenance FROM plan_versions WHERE id = ?", (version_id,))
    assert item["title"] == "New Title"
    assert item["detail"] == "New Detail"
    assert item["rationale"] == "New Rationale"
    assert item["provenance"] == "admin"
    assert version["provenance"] == "admin"


def test_item_edit_appends_audit_row_with_before_after(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'draft', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            "INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, position) VALUES (?, 'Day 1', 'exercise', 'Squat', '3x5', 'Build strength', 0)",
            (version_id,),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(
        admin,
        f"/members/{member['id']}/plan-versions/{version_id}/items/{item_id}/edit",
        source="/members",
        title="Goblet Squat",
        detail="3x8",
        rationale="Knee-friendly variation",
    )
    assert response.status_code == 302

    with gym_app.app.app_context():
        audit = gym_app.query_one(
            "SELECT * FROM plan_reviews WHERE plan_version_id = ? ORDER BY id DESC LIMIT 1",
            (version_id,),
        )
    assert audit is not None
    assert audit["action"] == "edit"
    before = json.loads(audit["before_json"])
    after = json.loads(audit["after_json"])
    assert before["title"] == "Squat"
    assert before["detail"] == "3x5"
    assert before["rationale"] == "Build strength"
    assert after["title"] == "Goblet Squat"
    assert after["detail"] == "3x8"
    assert after["rationale"] == "Knee-friendly variation"
    assert after.get("provenance") == "admin"


def test_item_edit_rejects_empty_rationale(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'draft', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            "INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, position) VALUES (?, 'Day 1', 'exercise', 'Squat', '3x5', 'Build strength', 0)",
            (version_id,),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(
        admin,
        f"/members/{member['id']}/plan-versions/{version_id}/items/{item_id}/edit",
        source="/members",
        title="Goblet Squat",
        detail="3x8",
        rationale="",
    )
    assert response.status_code == 302

    with gym_app.app.app_context():
        item = gym_app.query_one("SELECT * FROM plan_items WHERE id = ?", (item_id,))
    assert item["title"] == "Squat"
    assert item["detail"] == "3x5"
    assert item["rationale"] == "Build strength"


def test_edit_plan_version_with_item_id_updates_item_and_audit(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'draft', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            "INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, position) VALUES (?, 'Day 1', 'exercise', 'Squat', '3x5', 'Build strength', 0)",
            (version_id,),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(
        admin,
        f"/members/{member['id']}/plan-versions/{version_id}/edit",
        source="/members",
        item_id=str(item_id),
        title="Goblet Squat",
        detail="3x8",
        rationale="Knee-friendly variation",
    )
    assert response.status_code == 302

    with gym_app.app.app_context():
        item = gym_app.query_one("SELECT * FROM plan_items WHERE id = ?", (item_id,))
        audit = gym_app.query_one(
            "SELECT * FROM plan_reviews WHERE plan_version_id = ? ORDER BY id DESC LIMIT 1",
            (version_id,),
        )
    assert item["title"] == "Goblet Squat"
    assert item["detail"] == "3x8"
    assert item["rationale"] == "Knee-friendly variation"
    assert item["provenance"] == "admin"
    assert audit is not None
    assert audit["action"] == "edit"
    before = json.loads(audit["before_json"])
    after = json.loads(audit["after_json"])
    assert before["title"] == "Squat"
    assert before["detail"] == "3x5"
    assert before["rationale"] == "Build strength"
    assert after["title"] == "Goblet Squat"
    assert after["detail"] == "3x8"
    assert after["rationale"] == "Knee-friendly variation"
    assert after.get("provenance") == "admin"


def test_edit_plan_version_with_item_id_requires_rationale(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'draft', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            "INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, position) VALUES (?, 'Day 1', 'exercise', 'Squat', '3x5', 'Build strength', 0)",
            (version_id,),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(
        admin,
        f"/members/{member['id']}/plan-versions/{version_id}/edit",
        source="/members",
        item_id=str(item_id),
        title="Goblet Squat",
        detail="3x8",
        rationale="",
    )
    assert response.status_code == 302

    with gym_app.app.app_context():
        item = gym_app.query_one("SELECT * FROM plan_items WHERE id = ?", (item_id,))
    assert item["title"] == "Squat"
    assert item["detail"] == "3x5"
    assert item["rationale"] == "Build strength"


def test_item_edit_404_for_missing_item(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'draft', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(
        admin,
        f"/members/{member['id']}/plan-versions/{version_id}/items/99999/edit",
        source="/members",
        title="X",
        detail="Y",
        rationale="Z",
    )
    assert response.status_code == 404


# --- member-facing visibility -------------------------------------------------

def test_member_sees_approved_plan_items(admin):
    from datetime import date
    today = date.today().isoformat()
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        # Set beginner level and subscription start to today so focus is predictable
        gym_app.execute(
            "UPDATE members SET fitness_level = 'Beginner', subscription_start = ? WHERE id = ?",
            (today, member["id"]),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            "INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, position) VALUES (?, 'Day 1 - Full Body A', 'exercise', 'Squat', '3x5', 'Test', 0)",
            (version_id,),
        )

    plan = gym_app.personalized_today_plan(member)
    assert any("Squat" in item for item in plan["workout_items"])


def test_member_sees_honest_empty_state_when_no_approved_plan(admin):
    from datetime import date
    today = date.today().isoformat()
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute("UPDATE members SET subscription_start = ? WHERE id = ?", (today, member["id"]))
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

    plan = gym_app.personalized_today_plan(member)
    assert any("No approved workout plan" in item for item in plan["workout_items"])


# --- recommendation review audit fix ------------------------------------------

def test_recommendation_approve_writes_audit_row(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            """
            INSERT INTO member_recommendations
            (member_id, title, recommendation_type, why_appeared, confidence_score, first_step, supplement_candidate, food_first_alternative, suggested_lab, safety_notes, recommendation_level, status)
            VALUES (?, 'Test Rec', 'supplement', 'Test', 'High', 'Eat food', 'None', 'Food', 'None', 'Safe', 'food_first', 'pending_review')
            """,
            (member["id"],),
        )
        rec_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(admin, f"/members/{member['id']}/recommendations/review", source="/members", action="approve", rec_id=str(rec_id), note="Good to go")
    assert response.status_code == 302

    with gym_app.app.app_context():
        audit = gym_app.query_one(
            "SELECT * FROM recommendation_reviews WHERE recommendation_id = ? ORDER BY id DESC LIMIT 1",
            (rec_id,),
        )
    assert audit is not None
    assert audit["status"] == "approved"
    assert audit["review_note"] == "Good to go"


def test_recommendation_reject_writes_audit_row(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            """
            INSERT INTO member_recommendations
            (member_id, title, recommendation_type, why_appeared, confidence_score, first_step, supplement_candidate, food_first_alternative, suggested_lab, safety_notes, recommendation_level, status)
            VALUES (?, 'Test Rec', 'supplement', 'Test', 'High', 'Eat food', 'None', 'Food', 'None', 'Safe', 'food_first', 'pending_review')
            """,
            (member["id"],),
        )
        rec_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(admin, f"/members/{member['id']}/recommendations/review", source="/members", action="reject", rec_id=str(rec_id), note="Not suitable")
    assert response.status_code == 302

    with gym_app.app.app_context():
        audit = gym_app.query_one(
            "SELECT * FROM recommendation_reviews WHERE recommendation_id = ? ORDER BY id DESC LIMIT 1",
            (rec_id,),
        )
    assert audit is not None
    assert audit["status"] == "rejected"
    assert audit["review_note"] == "Not suitable"


def test_recommendation_reject_without_note_fails(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            """
            INSERT INTO member_recommendations
            (member_id, title, recommendation_type, why_appeared, confidence_score, first_step, supplement_candidate, food_first_alternative, suggested_lab, safety_notes, recommendation_level, status)
            VALUES (?, 'Test Rec', 'supplement', 'Test', 'High', 'Eat food', 'None', 'Food', 'None', 'Safe', 'food_first', 'pending_review')
            """,
            (member["id"],),
        )
        rec_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

    response = post(admin, f"/members/{member['id']}/recommendations/review", source="/members", action="reject", rec_id=str(rec_id))
    assert response.status_code == 302

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT status FROM member_recommendations WHERE id = ?", (rec_id,))
    assert after["status"] == "pending_review"
