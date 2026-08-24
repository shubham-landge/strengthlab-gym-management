"""Phase 6 — AI with mandatory reasoning.

Covers:
- Prompt includes circadian slots and equipment list
- All-or-nothing validation rejects missing/short rationale, invalid slots, unavailable equipment
- Accepted AI output persists with provenance=ai, model, status=draft
- Rejected AI falls back to rule-based generation with refusal note
- Multi-provider fallback order is preserved
- AI output is never auto-approved
"""

import json

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
        "primary_location": "",
        "activity_level": "Lightly Active",
        "fitness_level": "Beginner",
        "premium": 1,
        "workout_subscription": "Premium",
        "diet_subscription": "Premium",
        "medical_notes": "",
        "injury_notes": "",
        "food_preference": "",
        "dietary_style": "",
        "food_exclusions": "",
        "other_foods_avoided": "",
        "meals_per_day": 3,
        "cooking_preference": "",
        "medical_conditions": "",
        "supplements": "",
        "plan_name": "Monthly",
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
    """Remove draft and blocked plan_versions before each test."""
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "DELETE FROM plan_items WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND status IN ('draft', 'blocked'))",
            (member["id"],),
        )
        gym_app.execute(
            "DELETE FROM plan_reviews WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND status IN ('draft', 'blocked'))",
            (member["id"],),
        )
        gym_app.execute(
            "DELETE FROM plan_versions WHERE member_id = ? AND status IN ('draft', 'blocked')",
            (member["id"],),
        )


# --- prompt schema -----------------------------------------------------------

def test_ai_prompt_includes_circadian_slots():
    member = member_row()
    prompt = gym_app.ai_plan_prompt(member, plan_type="workout")
    assert "circadian_slots" in prompt
    slots = prompt["circadian_slots"]
    assert len(slots) > 0
    assert all("slot_time" in s and "purpose" in s for s in slots)


def test_ai_prompt_includes_equipment_list():
    member = member_row()
    prompt = gym_app.ai_plan_prompt(member, plan_type="workout")
    assert "available_gym_equipment" in prompt
    assert isinstance(prompt["available_gym_equipment"], list)
    assert len(prompt["available_gym_equipment"]) > 0


def test_ai_prompt_demands_rationale_in_requirements():
    member = member_row()
    prompt = gym_app.ai_plan_prompt(member, plan_type="workout")
    reqs = " ".join(prompt["requirements"])
    assert "rationale" in reqs.lower()
    assert "40 characters" in reqs


def test_ai_prompt_includes_response_schema():
    member = member_row()
    prompt = gym_app.ai_plan_prompt(member, plan_type="workout")
    assert "response_schema" in prompt
    assert "workout" in prompt["response_schema"]


# --- data minimization / security --------------------------------------------

DIRECT_IDENTIFIERS = ("name", "phone", "email", "address", "emergency_contact")


def test_ai_prompt_member_payload_excludes_direct_identifiers():
    member = member_row(
        name="Alice Smith",
        phone="555-1234",
        email="alice@example.com",
        address="123 Main St",
        emergency_contact="Bob 555-5678",
    )
    prompt = gym_app.ai_plan_prompt(member, plan_type="workout")
    member_payload = prompt["member"]
    for field in DIRECT_IDENTIFIERS:
        assert field not in member_payload, f"PII field '{field}' must not be in AI payload"


def test_ai_prompt_json_does_not_contain_identifier_values():
    member = member_row(
        name="Alice Smith",
        phone="555-1234",
        email="alice@example.com",
        address="123 Main St",
        emergency_contact="Bob 555-5678",
    )
    prompt = gym_app.ai_plan_prompt(member, plan_type="workout")
    serialized = json.dumps(prompt)
    for value in ("Alice Smith", "555-1234", "alice@example.com", "123 Main St", "Bob 555-5678"):
        assert value not in serialized, f"Identifier value '{value}' must not appear in serialized AI prompt"


def test_ai_prompt_retains_required_fitness_health_facts():
    member = member_row(
        goal="Fat loss",
        fitness_level="Beginner",
        injury_notes="Knee pain",
        medical_notes="Asthma",
        primary_fitness_goal="Strength",
        activity_level="Lightly Active",
        medical_conditions="Hypertension",
        dietary_style="Vegetarian",
        food_exclusions="Dairy",
    )
    prompt = gym_app.ai_plan_prompt(member, plan_type="workout")
    payload = prompt["member"]
    assert payload["goal"] == "Fat loss"
    assert payload["fitness_level"] == "Beginner"
    assert payload["injury_notes"] == "Knee pain"
    assert payload["medical_notes"] == "Asthma"
    assert payload["primary_fitness_goal"] == "Strength"
    assert payload["activity_level"] == "Lightly Active"
    assert payload["medical_conditions"] == ["Hypertension"]
    assert payload["dietary_style"] == "Vegetarian"
    assert payload["food_exclusions"] == ["Dairy"]
    assert "age" in payload
    assert "height_cm" in payload
    assert "weight_kg" in payload
    assert "bmi" in payload
    assert "circadian_slots" in prompt
    assert "available_gym_equipment" in prompt


# --- validation helpers ------------------------------------------------------

def _valid_slot_times():
    slots = circadian_service.build_day_slots("06:30", "18:30", "23:00")
    return {s["slot_time"] for s in slots}


def _make_workout_ai_response(**item_overrides):
    item = {
        "slot_time": "18:30",
        "item_type": "exercise",
        "title": "Lat Pulldown",
        "detail": "3 sets x 10 reps",
        "rationale": "This exercise is selected because it matches the member's goal and experience level, providing a safe back-focused movement.",
        "evidence": {"grade": "B", "source": "ACSM guidelines"},
        "confidence": "High",
    }
    item.update(item_overrides)
    return {
        "workout": {
            "plan_type": "workout",
            "days": [{"day_label": "Day 1", "items": [item]}],
        }
    }


def _make_diet_ai_response(**item_overrides):
    item = {
        "slot_time": "07:45",
        "item_type": "meal",
        "title": "Breakfast",
        "detail": "Oats and eggs",
        "rationale": "Front-loading protein supports the daily target across multiple feedings rather than two large ones.",
        "evidence": {"grade": "A", "source": "ISSN position stand"},
        "confidence": "High",
    }
    item.update(item_overrides)
    return {
        "diet": {
            "plan_type": "diet",
            "days": [{"day_label": "Every day", "items": [item]}],
        }
    }


# --- all-or-nothing validation -----------------------------------------------

def test_validate_rejects_missing_rationale():
    data = _make_workout_ai_response(rationale="")
    result, reason = gym_app.validate_ai_plan_data(
        data, "workout", _valid_slot_times(), set(gym_app.equipment_names())
    )
    assert result is None
    assert "missing rationale" in reason.lower() or "rationale" in reason.lower()


def test_validate_rejects_short_rationale():
    data = _make_workout_ai_response(rationale="Too short.")
    result, reason = gym_app.validate_ai_plan_data(
        data, "workout", _valid_slot_times(), set(gym_app.equipment_names())
    )
    assert result is None
    assert "under 40 characters" in reason.lower()


def test_validate_rejects_invalid_slot_time():
    data = _make_workout_ai_response(slot_time="99:99")
    result, reason = gym_app.validate_ai_plan_data(
        data, "workout", _valid_slot_times(), set(gym_app.equipment_names())
    )
    assert result is None
    assert "slot_time" in reason.lower()


def test_validate_rejects_unavailable_exercise():
    data = _make_workout_ai_response(title="Nonexistent Machine")
    result, reason = gym_app.validate_ai_plan_data(
        data, "workout", _valid_slot_times(), set(gym_app.equipment_names())
    )
    assert result is None
    assert "not in available equipment" in reason.lower()


def test_validate_accepts_valid_ai_response():
    data = _make_workout_ai_response()
    result, reason = gym_app.validate_ai_plan_data(
        data, "workout", _valid_slot_times(), set(gym_app.equipment_names())
    )
    assert result is not None
    assert reason is None
    assert "workout" in result


def test_validate_rejects_entire_response_on_first_invalid_item():
    good_item = {
        "slot_time": "18:30",
        "item_type": "exercise",
        "title": "Lat Pulldown",
        "detail": "3x10",
        "rationale": "This is a good rationale that explains why this exercise suits the member based on their goals and experience level.",
        "confidence": "High",
    }
    bad_item = {
        "slot_time": "18:30",
        "item_type": "exercise",
        "title": "Leg Press",
        "detail": "3x10",
        "rationale": "short",
        "confidence": "High",
    }
    data = {
        "workout": {
            "plan_type": "workout",
            "days": [
                {"day_label": "Day 1", "items": [good_item, bad_item]}
            ],
        }
    }
    result, reason = gym_app.validate_ai_plan_data(
        data, "workout", _valid_slot_times(), set(gym_app.equipment_names())
    )
    assert result is None
    assert "under 40 characters" in reason.lower()


# --- generation flow: accepted AI output -------------------------------------

def test_generate_ai_plans_persists_structured_items_with_ai_provenance(admin, monkeypatch):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        # Ensure premium and set circadian anchors so 18:30 is a valid slot
        gym_app.execute(
            "UPDATE members SET premium = 1, workout_subscription = 'Premium', diet_subscription = 'Premium', wake_time = '06:30', sleep_time = '23:00', workout_time = '18:30' WHERE id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

    valid_response = _make_workout_ai_response()
    monkeypatch.setattr(
        gym_app, "generate_openai_plans", lambda *a, **k: valid_response
    )
    monkeypatch.setattr(
        gym_app, "configured_ai_providers", lambda: [
            {"name": "openai", "keys": ["test-key"], "models": ["gpt-4o"]}
        ]
    )

    with gym_app.app.app_context():
        result = gym_app.generate_ai_plans(member, plan_type="workout")

    assert result is not None
    workout_text, _ = result
    assert "STRENGTHLAB AI WORKOUT BLUEPRINT" in workout_text

    with gym_app.app.app_context():
        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
        items = gym_app.query_all(
            "SELECT * FROM plan_items WHERE plan_version_id = ?",
            (version["id"],),
        )

    assert version is not None
    assert version["provenance"] == "ai"
    assert version["model"] == "gpt-4o"
    assert version["status"] == "draft"
    assert len(items) == 1
    assert items[0]["title"] == "Lat Pulldown"
    assert items[0]["rationale"] == valid_response["workout"]["days"][0]["items"][0]["rationale"]


def test_ai_output_never_auto_approves(admin, monkeypatch):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET premium = 1, workout_subscription = 'Premium', diet_subscription = 'Premium', wake_time = '06:30', sleep_time = '23:00', workout_time = '18:30' WHERE id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

    valid_response = _make_workout_ai_response()
    monkeypatch.setattr(
        gym_app, "generate_openai_plans", lambda *a, **k: valid_response
    )
    monkeypatch.setattr(
        gym_app, "configured_ai_providers", lambda: [
            {"name": "openai", "keys": ["test-key"], "models": ["gpt-4o"]}
        ]
    )

    with gym_app.app.app_context():
        gym_app.generate_ai_plans(member, plan_type="workout")

    with gym_app.app.app_context():
        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
    assert version["status"] == "draft"
    assert version["status"] != "approved"


# --- generation flow: safety gate on accepted AI output ----------------------

def test_generate_ai_plans_blocks_on_pregnancy(admin, monkeypatch):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET premium = 1, workout_subscription = 'Premium', diet_subscription = 'Premium', wake_time = '06:30', sleep_time = '23:00', workout_time = '18:30' WHERE id = ?",
            (member["id"],),
        )
        from services.clinical_recommendation_service import get_or_create_health_profile
        get_or_create_health_profile(gym_app.db(), member["id"])
        gym_app.execute(
            "UPDATE member_health_profiles SET pregnancy_lactation_status = 'Yes' WHERE member_id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

    valid_response = _make_workout_ai_response()
    monkeypatch.setattr(
        gym_app, "generate_openai_plans", lambda *a, **k: valid_response
    )
    monkeypatch.setattr(
        gym_app, "configured_ai_providers", lambda: [
            {"name": "openai", "keys": ["test-key"], "models": ["gpt-4o"]}
        ]
    )

    with gym_app.app.app_context():
        result = gym_app.generate_ai_plans(member, plan_type="workout")

    assert result is not None

    with gym_app.app.app_context():
        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )

    assert version is not None
    assert version["provenance"] == "ai"
    assert version["model"] == "gpt-4o"
    assert version["status"] == "blocked"
    assert version["blocked_reason"] is not None
    assert "clinician clearance" in version["blocked_reason"]


def test_generate_ai_plans_blocks_on_kidney_disease(admin, monkeypatch):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET premium = 1, workout_subscription = 'Premium', diet_subscription = 'Premium', wake_time = '06:30', sleep_time = '23:00', workout_time = '18:30' WHERE id = ?",
            (member["id"],),
        )
        from services.clinical_recommendation_service import get_or_create_health_profile
        get_or_create_health_profile(gym_app.db(), member["id"])
        gym_app.execute(
            "UPDATE member_health_profiles SET kidney_disease = 1 WHERE member_id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

    valid_response = _make_workout_ai_response()
    monkeypatch.setattr(
        gym_app, "generate_openai_plans", lambda *a, **k: valid_response
    )
    monkeypatch.setattr(
        gym_app, "configured_ai_providers", lambda: [
            {"name": "openai", "keys": ["test-key"], "models": ["gpt-4o"]}
        ]
    )

    with gym_app.app.app_context():
        result = gym_app.generate_ai_plans(member, plan_type="workout")

    assert result is not None

    with gym_app.app.app_context():
        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )

    assert version is not None
    assert version["provenance"] == "ai"
    assert version["model"] == "gpt-4o"
    assert version["status"] == "blocked"
    assert version["blocked_reason"] is not None
    assert "kidney" in version["blocked_reason"].lower()


def test_generate_ai_plans_both_blocked_on_flagged_profile(admin, monkeypatch):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET premium = 1, workout_subscription = 'Premium', diet_subscription = 'Premium', wake_time = '06:30', sleep_time = '23:00', workout_time = '18:30' WHERE id = ?",
            (member["id"],),
        )
        from services.clinical_recommendation_service import get_or_create_health_profile
        get_or_create_health_profile(gym_app.db(), member["id"])
        gym_app.execute(
            "UPDATE member_health_profiles SET liver_disease = 1 WHERE member_id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

    valid_response = {
        "workout": _make_workout_ai_response()["workout"],
        "diet": _make_diet_ai_response()["diet"],
    }
    monkeypatch.setattr(
        gym_app, "generate_openai_plans", lambda *a, **k: valid_response
    )
    monkeypatch.setattr(
        gym_app, "configured_ai_providers", lambda: [
            {"name": "openai", "keys": ["test-key"], "models": ["gpt-4o"]}
        ]
    )

    with gym_app.app.app_context():
        result = gym_app.generate_ai_plans(member, plan_type="both")

    assert result is not None

    with gym_app.app.app_context():
        workout_version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
        diet_version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'diet' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )

    assert workout_version["status"] == "blocked"
    assert diet_version["status"] == "blocked"
    assert workout_version["blocked_reason"] is not None
    assert diet_version["blocked_reason"] is not None
    assert workout_version["blocked_reason"] == diet_version["blocked_reason"]


# --- generation flow: rejected AI output falls back to rules -----------------

def test_generate_ai_plans_falls_back_to_rules_on_rejection(admin, monkeypatch):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET premium = 1, workout_subscription = 'Premium', diet_subscription = 'Premium', wake_time = '06:30', sleep_time = '23:00', workout_time = '18:30' WHERE id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

    invalid_response = _make_workout_ai_response(rationale="short")
    monkeypatch.setattr(
        gym_app, "generate_openai_plans", lambda *a, **k: invalid_response
    )
    monkeypatch.setattr(
        gym_app, "configured_ai_providers", lambda: [
            {"name": "openai", "keys": ["test-key"], "models": ["gpt-4o"]}
        ]
    )

    with gym_app.app.app_context():
        result = gym_app.generate_ai_plans(member, plan_type="workout")

    assert result is not None
    workout_text, _ = result
    assert "STRENGTHLAB" in workout_text

    with gym_app.app.app_context():
        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )

    assert version is not None
    assert version["provenance"] == "rule"


def test_fallback_records_refusal_reason(admin, monkeypatch):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET premium = 1, workout_subscription = 'Premium', diet_subscription = 'Premium', wake_time = '06:30', sleep_time = '23:00', workout_time = '18:30' WHERE id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

    invalid_response = _make_workout_ai_response(rationale="")
    monkeypatch.setattr(
        gym_app, "generate_openai_plans", lambda *a, **k: invalid_response
    )
    monkeypatch.setattr(
        gym_app, "configured_ai_providers", lambda: [
            {"name": "openai", "keys": ["test-key"], "models": ["gpt-4o"]}
        ]
    )

    with gym_app.app.app_context():
        gym_app.generate_ai_plans(member, plan_type="workout")

    with gym_app.app.app_context():
        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )

    assert version is not None
    assert version["review_note"] is not None
    assert "AI output refused" in version["review_note"]


# --- multi-provider fallback -------------------------------------------------

def test_multi_provider_fallback_tries_each_provider(admin, monkeypatch):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET premium = 1, workout_subscription = 'Premium', diet_subscription = 'Premium', wake_time = '06:30', sleep_time = '23:00', workout_time = '18:30' WHERE id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

    calls = []

    def fake_openai(*a, **k):
        calls.append("openai")
        return _make_workout_ai_response(rationale="short")

    def fake_gemini(*a, **k):
        calls.append("gemini")
        return _make_workout_ai_response()

    monkeypatch.setattr(gym_app, "generate_openai_plans", fake_openai)
    monkeypatch.setattr(gym_app, "generate_gemini_plans", fake_gemini)
    monkeypatch.setattr(
        gym_app, "configured_ai_providers", lambda: [
            {"name": "openai", "keys": ["k1"], "models": ["m1"]},
            {"name": "gemini", "keys": ["k1"], "models": ["m1"]},
        ]
    )

    with gym_app.app.app_context():
        result = gym_app.generate_ai_plans(member, plan_type="workout")

    assert result is not None
    assert "openai" in calls
    assert "gemini" in calls

    with gym_app.app.app_context():
        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
    assert version["provenance"] == "ai"


def test_generate_plans_falls_back_when_ai_is_unavailable(admin, monkeypatch):
    """Existing behavior: no API keys means rule-based fallback."""
    monkeypatch.setattr(gym_app, "configured_ai_providers", lambda: [])
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        workout, diet = gym_app.generate_plans(member, prefer_ai=True)
    assert workout and "no workout" not in workout.lower()
