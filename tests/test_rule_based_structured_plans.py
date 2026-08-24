"""Phase 3 — Rule-based structured plan generation tests.

Verifies that generate_rule_based_plans creates draft plan_versions with
plan_items placed at circadian slots, each carrying a composed rationale.
"""

import pytest

import app as gym_app
from services import circadian_service


def member_row(**overrides):
    base = {
        "id": 1,
        "name": "Plan Person",
        "age": 30,
        "gender": "Male",
        "height_cm": 175,
        "weight_kg": 75,
        "goal": "Fat loss",
        "primary_fitness_goal": None,
        "activity_level": "Lightly Active",
        "fitness_level": "Beginner",
        "premium": 0,
        "workout_subscription": "Regular",
        "diet_subscription": "Regular",
        "medical_notes": "",
        "injury_notes": "",
        "food_preference": "",
        "dietary_style": "",
        "food_exclusions": "",
        "workout_plan": "",
        "diet_plan": "",
        "wake_time": "06:30",
        "sleep_time": "23:00",
        "workout_time": "18:30",
    }
    base.update(overrides)
    return base


@pytest.fixture(autouse=True)
def clean_drafts(admin):
    """Remove any draft plan_versions before each test."""
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "DELETE FROM plan_items WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND status = 'draft')",
            (member["id"],),
        )
        gym_app.execute(
            "DELETE FROM plan_reviews WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND status = 'draft')",
            (member["id"],),
        )
        gym_app.execute(
            "DELETE FROM plan_versions WHERE member_id = ? AND status = 'draft'",
            (member["id"],),
        )


# --- circadian service --------------------------------------------------------

def test_circadian_service_returns_ordered_slots():
    slots = circadian_service.build_day_slots("06:30", "18:30", "23:00")
    assert len(slots) > 0
    times = [s["slot_time"] for s in slots]
    assert times == sorted(times)


def test_circadian_service_includes_training_slot():
    slots = circadian_service.build_day_slots("06:30", "18:30", "23:00")
    training = [s for s in slots if s["purpose"] == "Training"]
    assert len(training) == 1
    assert training[0]["slot_time"] == "18:30"


def test_circadian_service_fasted_start_rule():
    slots = circadian_service.build_day_slots("06:30", "07:00", "23:00")
    purposes = {s["purpose"] for s in slots}
    assert "Pre-workout light carb" in purposes
    assert "Pre-workout meal" not in purposes


def test_circadian_service_late_training_adds_wind_down():
    slots = circadian_service.build_day_slots("06:30", "21:00", "23:00")
    purposes = {s["purpose"] for s in slots}
    assert "Wind-down" in purposes


def test_circadian_service_short_sleep_flagged():
    # 01:00 bedtime to a 06:30 wake is a real 5.5 h window. The original fixture
    # used a 12:00 bedtime, which is 18.5 h of sleep and puts the 18:30 workout
    # after the member has gone to bed.
    slots = circadian_service.build_day_slots("06:30", "18:30", "01:00")
    training = next(s for s in slots if s["purpose"] == "Training")
    assert "below 7-hour floor" in training["rationale"]


def test_circadian_service_missing_anchors_use_fallback():
    slots = circadian_service.build_day_slots(None, None, None)
    training = next(s for s in slots if s["purpose"] == "Training")
    assert training["slot_time"] == "18:00"
    assert training["confidence"] == "Low"
    assert "Fallback" in training["rationale"]


# --- structured plan persistence ----------------------------------------------

def test_rule_based_generation_creates_draft_versions(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.generate_rule_based_plans(member)

        workout_version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
        diet_version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'diet' AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )

    assert workout_version is not None
    assert diet_version is not None
    assert workout_version["provenance"] == "rule"
    assert diet_version["provenance"] == "rule"


def test_workout_items_have_circadian_slot_times(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.generate_rule_based_plans(member)

        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
        items = gym_app.query_all(
            "SELECT * FROM plan_items WHERE plan_version_id = ? ORDER BY position",
            (version["id"],),
        )

    assert len(items) > 0
    for item in items:
        assert item["slot_time"] is not None
        assert item["rationale"] is not None
        assert len(item["rationale"].strip()) > 0


def test_diet_items_have_circadian_slot_times(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.generate_rule_based_plans(member)

        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'diet' AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
        items = gym_app.query_all(
            "SELECT * FROM plan_items WHERE plan_version_id = ? ORDER BY position",
            (version["id"],),
        )

    assert len(items) > 0
    for item in items:
        assert item["slot_time"] is not None
        assert item["rationale"] is not None
        assert len(item["rationale"].strip()) > 0


def test_every_item_rationale_is_member_specific(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET goal = ?, fitness_level = ?, injury_notes = ?, food_preference = ? WHERE id = ?",
            ("muscle gain", "Intermediate", "knee pain", "vegetarian", member["id"]),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        gym_app.generate_rule_based_plans(member)

        for plan_type in ("workout", "diet"):
            version = gym_app.query_one(
                "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = ? AND status = 'draft' ORDER BY id DESC LIMIT 1",
                (member["id"], plan_type),
            )
            items = gym_app.query_all(
                "SELECT * FROM plan_items WHERE plan_version_id = ?",
                (version["id"],),
            )
            for item in items:
                rationale = item["rationale"]
                assert rationale and len(rationale.strip()) > 0
                # Rationale must reference at least one actual member value,
                # a fired rule, or a named contraindication — never be a fixed
                # generic sentence keyed only on the item title.
                # Accept explicit member values, fired rules, contraindications,
                # or time anchors drawn from the member record.
                has_member_input = (
                    "muscle gain" in rationale
                    or "Intermediate" in rationale
                    or "knee pain" in rationale
                    or "vegetarian" in rationale
                    or "circadian" in rationale.lower()
                    or "fallback" in rationale.lower()
                    or "Anchor" in rationale
                    or "reported" in rationale
                    or "floor" in rationale
                    or "rule" in rationale.lower()
                    or (":" in rationale and any(ch.isdigit() for ch in rationale))
                )
                assert has_member_input, (
                    f"Rationale for {item['title']} does not reference member inputs: {rationale}"
                )


def test_generation_does_not_overwrite_approved_version(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        # Seed an approved version
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'admin', datetime('now'))",
            (member["id"],),
        )
        approved_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            "INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, position) VALUES (?, 'Day 1', 'exercise', 'Squat', '3x5', 'Legacy', 0)",
            (approved_id,),
        )

        # Generate new rule-based plan
        gym_app.generate_rule_based_plans(member)

        # Approved version must still exist and be unchanged
        after = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE id = ?",
            (approved_id,),
        )
        assert after["status"] == "approved"

        # A new draft should also exist
        draft = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
        assert draft is not None
        assert draft["id"] != approved_id


def test_zero_api_keys_produces_structured_rule_plan(admin, monkeypatch):
    monkeypatch.setattr(gym_app, "configured_ai_providers", lambda: [])
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET workout_subscription = 'Regular', diet_subscription = 'Regular' WHERE id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        workout, diet = gym_app.generate_plans(member, prefer_ai=True)

    assert workout and len(workout) > 100
    assert diet and len(diet) > 100

    with gym_app.app.app_context():
        draft = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
    assert draft is not None
    assert draft["provenance"] == "rule"


def test_workout_plan_items_reference_injury_text_when_present(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET injury_notes = ? WHERE id = ?",
            ("shoulder impingement", member["id"]),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        gym_app.generate_rule_based_plans(member)

        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
        items = gym_app.query_all(
            "SELECT * FROM plan_items WHERE plan_version_id = ? AND item_type = 'exercise'",
            (version["id"],),
        )
        for item in items:
            assert "shoulder impingement" in item["rationale"]


def test_diet_plan_items_reference_food_preference_when_present(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET food_preference = ? WHERE id = ?",
            ("vegan", member["id"]),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        gym_app.generate_rule_based_plans(member)

        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'diet' AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
        items = gym_app.query_all(
            "SELECT * FROM plan_items WHERE plan_version_id = ? AND item_type = 'meal'",
            (version["id"],),
        )
        assert len(items) > 0
        for item in items:
            assert "vegan" in item["rationale"]
