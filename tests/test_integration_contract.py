"""Guards on the seams between the two tracks.

Both tracks independently implemented weekly_volume; Python silently took the
later definition and the other became dead code with a failing test. These
tests are about the joins, not either track's own work.
"""

import app as gym_app
from services.content_library import EXERCISES


def test_weekly_volume_is_defined_once():
    """Two definitions meant the contract-owning one was silently discarded."""
    import inspect
    source = inspect.getsource(gym_app)
    assert source.count("\ndef weekly_volume(") == 1, "weekly_volume is defined more than once"


def test_weekly_volume_returns_the_agreed_shape(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        gym_app.generate_rule_based_plans(member)
        version = gym_app.query_one(
            "SELECT id FROM plan_versions WHERE plan_type='workout' ORDER BY id DESC LIMIT 1"
        )
        rows = gym_app.weekly_volume(member["id"], version["id"])

    assert rows, "a generated plan should produce volume"
    for row in rows:
        assert set(row) == {"muscle_group", "sets", "min", "max", "status"}
        assert row["muscle_group"], "a nameless muscle group must never be reported"
        assert row["status"] in {"under", "optimal", "over"}
        assert row["min"] <= row["max"]


def test_every_generated_movement_resolves_to_the_catalogue(admin):
    """Session templates once used names the catalogue did not carry, so those
    movements had no muscle group, no cues and no contraindications."""
    library = {e[0] for e in EXERCISES}
    used = set()
    for split in ("Push / Pull / Legs", "Upper / Lower", "Full Body"):
        for _day, exercises in gym_app.session_templates(split):
            used.update(exercises)
    missing = sorted(used - library)
    assert not missing, f"movements missing from the catalogue: {missing}"


def test_generated_exercises_carry_the_contract_fields(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        gym_app.generate_rule_based_plans(member)
        items = gym_app.query_all(
            "SELECT * FROM plan_items WHERE item_type = 'exercise'"
        )

    assert items
    for item in items:
        assert item["set_count"] is not None, f"{item['title']} has no set_count"
        assert item["muscle_group"], f"{item['title']} has no muscle_group"
        assert item["sets"] and item["reps"], f"{item['title']} has no prescription"


def test_set_logs_is_created_once_and_matches_the_contract(admin):
    with gym_app.app.app_context():
        cols = {r[1] for r in gym_app.db().execute("PRAGMA table_info(set_logs)")}
    expected = {"id", "plan_item_id", "member_id", "set_number",
                "reps_done", "load_kg", "rpe_reported", "logged_at"}
    assert expected <= cols, f"set_logs is missing {expected - cols}"


def test_conditioning_never_gets_a_set_and_rep_prescription(admin):
    """The legacy data still contains 'Cycle: 3-4 sets x 8-12 reps'."""
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        gym_app.generate_rule_based_plans(member)
        conditioning = gym_app.query_all(
            "SELECT * FROM plan_items WHERE lower(title) IN ('cycle', 'treadmill incline walk')"
        )
    for item in conditioning:
        assert "sets" not in (item["detail"] or "").lower(), \
            f"{item['title']} was given a set prescription: {item['detail']}"
