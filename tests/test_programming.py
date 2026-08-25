"""Coach-grade prescription: movement-specific loading, block progression, swaps."""

import pytest

import app as gym_app
from services import programming as prog


# --- movement classification -----------------------------------------------

@pytest.mark.parametrize("exercise,expected", [
    ("Dumbbell Flat Bench Press", prog.COMPOUND),
    ("Leg Press", prog.COMPOUND),
    ("Chin-Up or Lat Pulldown", prog.COMPOUND),
    ("Preacher Curl", prog.ISOLATION),
    ("Pec Deck Fly", prog.ISOLATION),
    ("Seated Lateral Raise Machine", prog.ISOLATION),
    ("Standing Calf Raise", prog.ISOLATION),
    ("Hanging Knee Raise", prog.CORE),
    ("Treadmill Incline Walk", prog.CONDITIONING),
    ("Cycle", prog.CONDITIONING),
])
def test_movements_are_classified(exercise, expected):
    assert prog.classify_exercise(exercise) == expected


def test_an_unknown_movement_defaults_to_compound():
    assert prog.classify_exercise("Some New Machine") == prog.COMPOUND


# --- prescriptions differ by movement --------------------------------------

def test_compound_and_isolation_get_different_prescriptions():
    """Every exercise previously got one identical line."""
    compound = prog.prescribe("Leg Press", "Muscle gain")
    isolation = prog.prescribe("Preacher Curl", "Muscle gain")
    assert compound["reps"] != isolation["reps"]
    assert compound["rest"] != isolation["rest"]
    assert compound["tempo"] != isolation["tempo"]


def test_rest_is_longer_for_strength_than_endurance():
    strength = prog.prescribe("Leg Press", "build maximal strength")
    endurance = prog.prescribe("Leg Press", "improve stamina and endurance")
    assert strength["reps"] != endurance["reps"]
    assert "min" in strength["rest"]


@pytest.mark.parametrize("goal,expected", [
    ("get stronger, add to my 1RM", "strength"),
    ("build muscle and size", "hypertrophy"),
    ("improve stamina", "endurance"),
    ("", "hypertrophy"),
])
def test_goal_text_maps_to_a_training_intent(goal, expected):
    assert prog.goal_bucket(goal) == expected


def test_every_prescription_carries_a_progression_rule():
    for exercise in ("Leg Press", "Preacher Curl", "Hanging Knee Raise", "Cycle"):
        rule = prog.prescribe(exercise, "Muscle gain")["progression"]
        assert rule and len(rule) > 30, f"{exercise} has no usable progression rule"


# --- the four week block ----------------------------------------------------

def test_the_block_is_four_weeks_with_a_deload():
    assert len(prog.BLOCK_WEEKS) == 4
    assert [w["week"] for w in prog.BLOCK_WEEKS] == [1, 2, 3, 4]
    assert "deload" in prog.BLOCK_WEEKS[3]["name"].lower()


def test_intensity_climbs_then_backs_off():
    rpes = [w["rpe"] for w in prog.BLOCK_WEEKS]
    assert "6-7" in rpes[0] and "8-9" in rpes[2], "week 3 must be the heaviest"
    assert "5-6" in rpes[3], "week 4 must be lighter than week 1"


def test_the_deload_week_removes_a_set():
    week3 = prog.prescribe("Leg Press", "Muscle gain", week=3)
    week4 = prog.prescribe("Leg Press", "Muscle gain", week=4)
    assert week3["sets"] != week4["sets"]


def test_an_unknown_week_falls_back_to_week_one():
    assert prog.prescribe("Leg Press", "Muscle gain", week=99)["rpe"] == prog.BLOCK_WEEKS[0]["rpe"]


# --- diet swaps -------------------------------------------------------------

def test_swaps_are_offered_for_a_common_meal():
    swaps = prog.swaps_for("Paneer 150 g, rice 1 portion")
    assert any("paneer" in s for s in swaps)


def test_vegan_style_removes_dairy_alternatives():
    swaps = prog.swaps_for("Paneer 150 g", dietary_style="vegan")
    joined = " ".join(swaps)
    assert "curd" not in joined and "yoghurt" not in joined
    assert "tofu" in joined, "a usable alternative must remain"


def test_an_allergy_removes_that_food_from_alternatives():
    swaps = prog.swaps_for("Peanuts 20 g", exclusions=["almond", "walnut"])
    joined = " ".join(swaps)
    assert "almond" not in joined and "walnut" not in joined


def test_swaps_stay_short_enough_to_read_on_a_phone():
    swaps = prog.swaps_for("Paneer, rice, banana, curd, oats, chicken")
    assert len(swaps) <= 3


def test_unknown_ingredients_produce_no_swaps():
    assert prog.swaps_for("Something the library has never heard of") == []


# --- integration with the generator ----------------------------------------

def generated_workout_items():
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET wake_time='06:30', workout_time='18:30', sleep_time='23:00', goal='Muscle gain' WHERE id = ?",
            (member["id"],),
        )
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        gym_app.generate_rule_based_plans(member)
        version = gym_app.query_one(
            "SELECT id FROM plan_versions WHERE plan_type='workout' ORDER BY id DESC LIMIT 1"
        )
        return gym_app.query_all(
            "SELECT * FROM plan_items WHERE plan_version_id = ? ORDER BY id", (version["id"],)
        )


def test_the_plan_opens_with_the_block_overview(admin):
    items = generated_workout_items()
    block = [i for i in items if i["day_label"].startswith("Programme block")]
    assert len(block) == 4, "all four weeks should be described"
    assert any("Deload" in i["title"] for i in block)


def test_no_exercise_is_listed_twice_in_a_session(admin):
    items = generated_workout_items()
    by_day = {}
    for item in items:
        if item["item_type"] != "exercise":
            continue
        by_day.setdefault(item["day_label"], []).append(item["title"])
    for day, titles in by_day.items():
        assert len(titles) == len(set(titles)), f"{day} repeats an exercise: {titles}"


def test_sessions_carry_tempo_and_rest(admin):
    items = generated_workout_items()
    exercises = [i for i in items if i["item_type"] == "exercise" and "Day" in i["day_label"]]
    assert exercises
    detailed = [i for i in exercises if "tempo" in (i["detail"] or "") and "rest" in (i["detail"] or "")]
    assert detailed, "prescriptions should state tempo and rest"


def test_exercise_rationales_explain_when_to_add_load(admin):
    items = generated_workout_items()
    exercises = [i for i in items if i["item_type"] == "exercise" and "Day" in i["day_label"]]
    assert any("Progression:" in (i["rationale"] or "") for i in exercises)
