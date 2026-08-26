"""The local catalogue: what the gym owns, what the member can eat.

This exists so generation is grounded before any AI is involved. The rule
engine and the prompt read the same filtered list, so a provider being down
changes availability, not correctness.
"""

import pytest

import app as gym_app
from services import content_library


# --- seed integrity ---------------------------------------------------------

def test_every_seed_row_matches_its_field_list():
    for row in content_library.EXERCISES:
        assert len(row) == len(content_library.EXERCISE_FIELDS), f"malformed exercise: {row[0]}"
    for row in content_library.FOODS:
        assert len(row) == len(content_library.FOOD_FIELDS), f"malformed food: {row[0]}"


def test_seed_names_are_unique():
    names = [r[0] for r in content_library.EXERCISES]
    assert len(names) == len(set(names))
    foods = [r[0] for r in content_library.FOODS]
    assert len(foods) == len(set(foods))


def test_every_food_carries_a_source():
    """Nutrition numbers a trainer cannot check are numbers they should not trust."""
    source_index = content_library.FOOD_FIELDS.index("source")
    for row in content_library.FOODS:
        assert row[source_index], f"{row[0]} has no source"


def test_macros_are_physically_plausible():
    f = content_library.FOOD_FIELDS
    for row in content_library.FOODS:
        item = dict(zip(f, row))
        kcal_from_macros = item["protein_100g"] * 4 + item["carb_100g"] * 4 + item["fat_100g"] * 9
        assert item["kcal_100g"] > 0, f"{item['name']} has no calories"
        # Atwater factors are approximations and water content varies, so allow
        # a wide band - this catches transposed or mistyped values, not rounding.
        assert abs(kcal_from_macros - item["kcal_100g"]) < item["kcal_100g"] * 0.45 + 60, \
            f"{item['name']}: macros imply {kcal_from_macros:.0f} kcal but row says {item['kcal_100g']}"


def test_vegan_foods_are_also_vegetarian():
    f = content_library.FOOD_FIELDS
    for row in content_library.FOODS:
        item = dict(zip(f, row))
        if item["vegan"]:
            assert item["vegetarian"], f"{item['name']} is vegan but not marked vegetarian"


def test_dairy_and_meat_are_not_marked_vegan():
    f = content_library.FOOD_FIELDS
    for row in content_library.FOODS:
        item = dict(zip(f, row))
        if "dairy" in (item["allergens"] or "") or item["category"] == "protein" and item["name"] in {"Chicken breast", "Fish (rohu)"}:
            assert not item["vegan"], f"{item['name']} must not be vegan"


def test_exercise_cues_are_present_and_split_cleanly():
    cue_index = content_library.EXERCISE_FIELDS.index("cues")
    for row in content_library.EXERCISES:
        cues = [c for c in row[cue_index].split("|") if c.strip()]
        assert len(cues) >= 2, f"{row[0]} needs at least two coaching cues"


def test_seed_text_is_english():
    """A stray non-English character once reached a coaching cue."""
    for row in content_library.EXERCISES:
        for field in row:
            if isinstance(field, str):
                assert all(ord(ch) < 0x2E80 for ch in field), f"non-latin text in {row[0]}: {field[:40]}"


# --- seeding ----------------------------------------------------------------

def test_the_catalogue_is_seeded(admin):
    with gym_app.app.app_context():
        exercises = gym_app.query_one("SELECT COUNT(*) AS n FROM exercise_library")["n"]
        foods = gym_app.query_one("SELECT COUNT(*) AS n FROM food_library")["n"]
    assert exercises == len(content_library.EXERCISES)
    assert foods == len(content_library.FOODS)


def test_reseeding_does_not_overwrite_a_curated_edit(admin):
    """A gym correcting a macro must not have it reverted on next boot."""
    with gym_app.app.app_context():
        gym_app.execute("UPDATE food_library SET protein_100g = 99 WHERE name = 'Paneer'")
        gym_app.init_db()
        after = gym_app.query_one("SELECT protein_100g FROM food_library WHERE name = 'Paneer'")
    assert after["protein_100g"] == 99


# --- filtering --------------------------------------------------------------

def blank_member():
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            """
            UPDATE members SET dietary_style='', food_preference='', food_exclusions='',
                   other_foods_avoided='', injury_notes='', medical_notes='' WHERE id = ?
            """,
            (member["id"],),
        )
        return gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))


def test_an_unrestricted_member_sees_everything(admin):
    member = blank_member()
    with gym_app.app.app_context():
        assert len(gym_app.available_foods(member)) == len(content_library.FOODS)


def test_a_vegan_is_never_offered_dairy_or_meat(admin):
    member = blank_member()
    with gym_app.app.app_context():
        gym_app.execute("UPDATE members SET dietary_style='vegan' WHERE id = ?", (member["id"],))
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        names = {r["name"] for r in gym_app.available_foods(member)}
    for banned in ("Paneer", "Curd (dahi)", "Whey protein", "Egg (whole)", "Chicken breast", "Ghee"):
        assert banned not in names, f"a vegan was offered {banned}"
    assert "Tofu" in names, "a usable protein must remain"


def test_an_allergy_removes_the_food(admin):
    member = blank_member()
    with gym_app.app.app_context():
        gym_app.execute("UPDATE members SET food_exclusions='nuts' WHERE id = ?", (member["id"],))
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        names = {r["name"] for r in gym_app.available_foods(member)}
    assert "Peanuts" not in names and "Almonds" not in names
    assert "Pumpkin seeds" in names, "a non-nut fat source should survive"


def test_an_injury_removes_contraindicated_movements(admin):
    member = blank_member()
    with gym_app.app.app_context():
        gym_app.execute("UPDATE members SET injury_notes='lower back pain' WHERE id = ?", (member["id"],))
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        names = {r["name"] for r in gym_app.available_exercises(member)}
    assert "Dumbbell Romanian Deadlift" not in names
    assert "Back Extension" not in names
    assert "Lat Pulldown" in names, "safe movements must remain"


def test_only_movements_the_gym_owns_are_offered(admin):
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM equipment WHERE lower(name) LIKE '%lat pulldown%'")
        names = {r["name"] for r in gym_app.available_exercises(None)}
    assert "Lat Pulldown" not in names, "a movement needs its machine on the floor"


# --- what the model is handed ----------------------------------------------

def test_the_prompt_carries_the_filtered_catalogue(admin):
    member = blank_member()
    with gym_app.app.app_context():
        gym_app.execute("UPDATE members SET dietary_style='vegan' WHERE id = ?", (member["id"],))
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        payload = gym_app.ai_plan_prompt(member)

    assert payload["available_exercises"], "the model needs a movement list"
    assert payload["available_foods"], "the model needs a food list"
    food_names = {f["name"] for f in payload["available_foods"]}
    assert "Paneer" not in food_names, "the model must not be able to suggest it at all"


def test_the_prompt_tells_the_model_to_select_not_invent(admin):
    member = blank_member()
    with gym_app.app.app_context():
        requirements = " ".join(gym_app.ai_plan_prompt(member)["requirements"])
    assert "available_exercises" in requirements
    assert "available_foods" in requirements
    assert "do not estimate macros" in requirements.lower()


def test_every_offered_food_carries_macros_for_the_model(admin):
    member = blank_member()
    with gym_app.app.app_context():
        payload = gym_app.ai_plan_prompt(member)
    for food in payload["available_foods"]:
        assert food["per_100g"]["protein"] is not None
        assert food["typical_portion"], f"{food['name']} has no portion label"
