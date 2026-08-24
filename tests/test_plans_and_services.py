"""Plan generation, the safety gate, and trainer-assignment flows.

These paths carry clinical and staffing consequences but had no coverage.
"""

import datetime

import pytest

import app as gym_app
from conftest import csrf_for
from services import supplement_recommendation_service as supplements


def post(client, path, source="/members", **fields):
    fields["csrf_token"] = csrf_for(client, source)
    return client.post(path, data=fields)


def member_row(**overrides):
    base = {
        "id": 1, "name": "Plan Person", "age": 30, "gender": "Male",
        "height_cm": 175, "weight_kg": 75, "goal": "Fat loss",
        "primary_fitness_goal": None, "activity_level": "Lightly Active",
        "fitness_level": "Beginner", "premium": 0,
        "workout_subscription": "Regular", "diet_subscription": "Regular",
        "medical_notes": "", "injury_notes": "", "food_preference": "",
        "dietary_style": "", "food_exclusions": "", "workout_plan": "", "diet_plan": "",
    }
    base.update(overrides)
    return base


# --- nutrition maths --------------------------------------------------------

def test_fat_loss_and_muscle_gain_shift_calories_in_opposite_directions():
    maintenance = gym_app.nutrition_targets(member_row(), "general fitness")[0]
    cutting = gym_app.nutrition_targets(member_row(), "fat loss")[0]
    bulking = gym_app.nutrition_targets(member_row(), "muscle gain")[0]
    assert cutting < maintenance < bulking


def test_protein_and_macros_are_positive_and_consistent():
    calories, protein, carbs, fat = gym_app.nutrition_targets(member_row(), "muscle gain")
    assert calories > 0 and protein > 0 and carbs > 0 and fat > 0
    assert protein >= 90, "there is a documented protein floor"


def test_activity_level_raises_the_calorie_target():
    sedentary = gym_app.nutrition_targets(member_row(activity_level="Sedentary"), "maintain")[0]
    very_active = gym_app.nutrition_targets(member_row(activity_level="Very Active"), "maintain")[0]
    assert very_active > sedentary


def test_bmi_handles_missing_measurements():
    assert gym_app.bmi(None, 70) is None
    assert gym_app.bmi(175, None) is None
    assert gym_app.bmi(175, 75) == pytest.approx(24.5, abs=0.1)


# --- rule-based plan generation --------------------------------------------

def test_rule_based_plans_are_produced_without_any_ai_configured(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        workout, diet = gym_app.generate_rule_based_plans(member)
    assert workout and diet
    assert len(workout) > 100, "a plan should have real content"


def test_generate_plans_falls_back_when_ai_is_unavailable(admin, monkeypatch):
    """No API key is configured in CI, so this must not raise or return empty."""
    monkeypatch.setattr(gym_app, "configured_ai_providers", lambda: [])
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        workout, diet = gym_app.generate_plans(member, prefer_ai=True)
    assert workout and "no workout" not in workout.lower()


def test_a_member_without_a_diet_subscription_gets_no_diet_plan(admin):
    with gym_app.app.app_context():
        member_id = gym_app.query_one("SELECT id FROM members LIMIT 1")["id"]
        gym_app.execute(
            "UPDATE members SET diet_subscription = 'None', workout_subscription = 'Regular' WHERE id = ?",
            (member_id,),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member_id,))
        _, diet = gym_app.generate_plans(member, prefer_ai=False)
    assert "subscription" in diet.lower()


def test_injuries_are_reflected_in_the_workout_blueprint():
    plain = gym_app.workout_blueprint("Beginner", "muscle gain", "")
    injured = gym_app.workout_blueprint("Beginner", "muscle gain", "knee pain")
    assert plain != injured, "an injury note should change the plan"


# --- supplement safety gate -------------------------------------------------

def test_pregnancy_always_requires_clinician_clearance():
    warnings = supplements.safety_gate(member_row(), {"pregnancy_lactation_status": "Yes"}, "Magnesium")
    assert any("clinician" in w.lower() for w in warnings)


@pytest.mark.parametrize("supplement", ["Magnesium", "Creatine monohydrate", "Electrolytes", "Calcium", "Iron"])
def test_kidney_disease_flags_renally_cleared_supplements(supplement):
    warnings = supplements.safety_gate(member_row(), {"kidney_disease": 1}, supplement)
    assert any("kidney" in w.lower() for w in warnings)


@pytest.mark.parametrize("supplement", ["Caffeine", "Creatine monohydrate", "Iron"])
def test_liver_disease_flags_hepatotoxic_risk(supplement):
    warnings = supplements.safety_gate(member_row(), {"liver_disease": 1}, supplement)
    assert any("liver" in w.lower() for w in warnings)


def test_a_healthy_member_on_no_medication_gets_no_red_flags():
    assert supplements.safety_gate(member_row(), {}, "Magnesium") == []


def test_medications_always_raise_an_interaction_warning():
    warnings = supplements.safety_gate(member_row(), {"medications": "metformin"}, "Magnesium")
    assert any("interaction" in w.lower() for w in warnings)


def test_contraindicated_supplements_are_never_recommended():
    level = supplements.get_recommendation_level(99, ["some warning"], is_contraindicated=True)
    assert "recommend" not in str(level).lower() or "not" in str(level).lower()


# --- trainer assignment flows ----------------------------------------------

@pytest.fixture()
def trainer_client():
    """A separate client signed in as a trainer.

    It must not reuse the `client` fixture: the `admin` fixture builds on the same
    instance, so a test needing both would end up with one session.
    """
    gym_app.app.config["TESTING"] = True
    client = gym_app.app.test_client()
    with gym_app.app.app_context():
        user = gym_app.query_one("SELECT * FROM users WHERE role = 'trainer' AND trainer_id IS NOT NULL LIMIT 1")
        gym_app.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0, active = 1 WHERE id = ?",
            (gym_app.generate_password_hash("trainerpass1"), user["id"]),
        )
    token = csrf_for(client)
    response = client.post(
        "/login",
        data={"username": user["username"], "password": "trainerpass1", "csrf_token": token},
    )
    assert response.status_code == 302
    client.trainer_id = user["trainer_id"]
    return client


def test_admin_can_assign_a_trainer_directly(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        trainer = gym_app.query_one("SELECT * FROM trainers LIMIT 1")
        gym_app.execute("UPDATE members SET trainer_id = NULL WHERE id = ?", (member["id"],))

    post(admin, "/trainer-assignments/direct", member_id=str(member["id"]), trainer_id=str(trainer["id"]))

    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT trainer_id FROM members WHERE id = ?", (member["id"],))
    assert after["trainer_id"] == trainer["id"]


def test_an_assignment_request_can_be_approved(trainer_client, admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute("UPDATE members SET trainer_id = NULL WHERE id = ?", (member["id"],))
        gym_app.execute("DELETE FROM trainer_assignment_requests")

    post(trainer_client, "/trainer-assignments/request", member_id=str(member["id"]))
    with gym_app.app.app_context():
        request_row = gym_app.query_one("SELECT * FROM trainer_assignment_requests ORDER BY id DESC LIMIT 1")
    assert request_row is not None, "the request should be recorded"

    post(admin, f"/trainer-assignments/{request_row['id']}/approve")
    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT trainer_id FROM members WHERE id = ?", (member["id"],))
        decided = gym_app.query_one(
            "SELECT status FROM trainer_assignment_requests WHERE id = ?", (request_row["id"],)
        )
    assert after["trainer_id"] == trainer_client.trainer_id
    assert decided["status"].lower() != "pending"


def test_a_rejected_request_does_not_assign_the_trainer(trainer_client, admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute("UPDATE members SET trainer_id = NULL WHERE id = ?", (member["id"],))
        gym_app.execute("DELETE FROM trainer_assignment_requests")

    post(trainer_client, "/trainer-assignments/request", member_id=str(member["id"]))
    with gym_app.app.app_context():
        request_row = gym_app.query_one("SELECT * FROM trainer_assignment_requests ORDER BY id DESC LIMIT 1")

    post(admin, f"/trainer-assignments/{request_row['id']}/reject")
    with gym_app.app.app_context():
        after = gym_app.query_one("SELECT trainer_id FROM members WHERE id = ?", (member["id"],))
    assert after["trainer_id"] is None, "a rejected request must not assign anyone"


# --- attendance streak ------------------------------------------------------

def test_attendance_streak_counts_consecutive_days(admin):
    today = datetime.date.today()
    with gym_app.app.app_context():
        member_id = gym_app.query_one("SELECT id FROM members LIMIT 1")["id"]
        gym_app.execute("DELETE FROM attendance WHERE member_id = ?", (member_id,))
        for days_ago in (0, 1, 2):
            gym_app.execute(
                "INSERT INTO attendance (member_id, check_in) VALUES (?, ?)",
                (member_id, f"{today - datetime.timedelta(days=days_ago)} 08:00:00"),
            )
        streak = gym_app.attendance_streak(member_id)
    assert streak == 3


def test_a_gap_breaks_the_attendance_streak(admin):
    today = datetime.date.today()
    with gym_app.app.app_context():
        member_id = gym_app.query_one("SELECT id FROM members LIMIT 1")["id"]
        gym_app.execute("DELETE FROM attendance WHERE member_id = ?", (member_id,))
        for days_ago in (0, 3, 4):  # yesterday and the day before are missing
            gym_app.execute(
                "INSERT INTO attendance (member_id, check_in) VALUES (?, ?)",
                (member_id, f"{today - datetime.timedelta(days=days_ago)} 08:00:00"),
            )
        streak = gym_app.attendance_streak(member_id)
    assert streak == 1
