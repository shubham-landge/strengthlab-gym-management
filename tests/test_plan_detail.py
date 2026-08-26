"""Structured prescription fields: schema, backfill, generation, and survival."""

import os
import shutil
import sqlite3
import tempfile

import pytest

import app as gym_app
from services import programming


def table_columns(db_path, table_name):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        return {row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()}


def table_exists(db_path, table_name):
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None


def index_exists(db_path, index_name):
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = ?",
            (index_name,),
        ).fetchone()
        return row is not None


# --- schema on fresh database ------------------------------------------------

def test_plan_items_prescription_columns_exist_on_fresh_database():
    cols = table_columns(gym_app.DB_PATH, "plan_items")
    expected = {
        "sets", "set_count", "reps", "rpe", "tempo", "rest_seconds",
        "load_note", "muscle_group", "superset_group", "week", "coach_note",
    }
    assert expected.issubset(cols)


def test_set_logs_table_exists():
    assert table_exists(gym_app.DB_PATH, "set_logs")


def test_set_logs_index_exists():
    assert index_exists(gym_app.DB_PATH, "idx_set_logs_member_plan_item")


# --- backfill ----------------------------------------------------------------

def test_backfill_populates_parseable_strength_detail():
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        # Seed a legacy plan item with a parseable strength detail
        gym_app.execute(
            "DELETE FROM plan_items WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND plan_type = 'workout')",
            (member["id"],),
        )
        gym_app.execute(
            "DELETE FROM plan_reviews WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND plan_type = 'workout')",
            (member["id"],),
        )
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ? AND plan_type = 'workout'", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, position)
            VALUES (?, 'Day 1', 'exercise', 'Bench Press', '3-4 sets × 6-10 reps · RPE 6-7 · tempo 3-1-1-0 · rest 2-3 min.', 'Test', 0)
            """,
            (version_id,),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

        # Clear backfill marker and run init_db to trigger backfill
        gym_app.execute("UPDATE plan_items SET sets = NULL, set_count = NULL, reps = NULL WHERE id = ?", (item_id,))
        gym_app.init_db()

        item = gym_app.query_one("SELECT * FROM plan_items WHERE id = ?", (item_id,))
        assert item["sets"] == "3-4"
        assert item["set_count"] == 4
        assert item["reps"] == "6-10"
        assert item["rpe"] == "6-7"
        assert item["tempo"] == "3-1-1-0"
        assert item["rest_seconds"] == 150
        assert "tempo" in item["detail"]
        assert "rest" in item["detail"]


def test_backfill_leaves_unparseable_detail_intact():
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        # Remove any existing approved versions to avoid unique-index clash
        gym_app.execute(
            "DELETE FROM plan_items WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND plan_type = 'workout')",
            (member["id"],),
        )
        gym_app.execute(
            "DELETE FROM plan_reviews WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND plan_type = 'workout')",
            (member["id"],),
        )
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ? AND plan_type = 'workout'", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        legacy_detail = "Cycle: 3-4 sets x 8-12 reps"
        gym_app.execute(
            """
            INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, position)
            VALUES (?, 'Day 1', 'exercise', 'Cycle', ?, 'Test', 0)
            """,
            (version_id, legacy_detail),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

        gym_app.execute("UPDATE plan_items SET sets = NULL, set_count = NULL, reps = NULL WHERE id = ?", (item_id,))
        gym_app.init_db()

        item = gym_app.query_one("SELECT * FROM plan_items WHERE id = ?", (item_id,))
        assert item["detail"] == legacy_detail
        assert item["sets"] is None
        assert item["set_count"] is None
        assert item["reps"] is None


def test_backfill_marks_conditioning_as_recovery():
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "DELETE FROM plan_items WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND plan_type = 'workout')",
            (member["id"],),
        )
        gym_app.execute(
            "DELETE FROM plan_reviews WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND plan_type = 'workout')",
            (member["id"],),
        )
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ? AND plan_type = 'workout'", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, position)
            VALUES (?, 'Day 1', 'exercise', 'Conditioning', 'Finish 12-20 min treadmill incline walk.', 'Test', 0)
            """,
            (version_id,),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]

        gym_app.execute("UPDATE plan_items SET sets = NULL, set_count = NULL, reps = NULL WHERE id = ?", (item_id,))
        gym_app.init_db()

        item = gym_app.query_one("SELECT * FROM plan_items WHERE id = ?", (item_id,))
        assert item["item_type"] == "recovery"
        assert item["muscle_group"] == "full body"
        assert item["rest_seconds"] is None
        assert item["set_count"] is None


def test_migration_against_copy_of_real_database():
    """A copy of the real gym_manager.db must survive init_db() and backfill."""
    real_db = os.path.join(gym_app.BASE_DIR, "gym_manager.db")
    if not os.path.exists(real_db):
        pytest.skip("Real gym_manager.db not found")

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    shutil.copy(real_db, tmp.name)

    try:
        with sqlite3.connect(tmp.name) as conn:
            conn.row_factory = sqlite3.Row
            member_id = conn.execute("SELECT id FROM members LIMIT 1").fetchone()["id"]
            # Remove any existing workout versions to avoid unique-index clash
            conn.execute(
                "DELETE FROM plan_items WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND plan_type = 'workout')",
                (member_id,),
            )
            conn.execute(
                "DELETE FROM plan_reviews WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ? AND plan_type = 'workout')",
                (member_id,),
            )
            conn.execute("DELETE FROM plan_versions WHERE member_id = ? AND plan_type = 'workout'", (member_id,))
            # Seed legacy parseable and unparseable items for this member
            conn.execute(
                "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
                (member_id,),
            )
            version_id = conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"]
            conn.executemany(
                """
                INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, position)
                VALUES (?, 'Day 1', 'exercise', ?, ?, 'Test', 0)
                """,
                [
                    (version_id, "Bench Press", "3-4 sets × 6-10 reps · RPE 6-7 · tempo 3-1-1-0 · rest 2-3 min."),
                    (version_id, "Cycle", "Cycle: 3-4 sets x 8-12 reps"),
                    (version_id, "Conditioning", "Finish 12-20 min treadmill incline walk."),
                ],
            )
            conn.commit()

        original_db_path = gym_app.DB_PATH
        gym_app.DB_PATH = tmp.name
        try:
            gym_app.init_db()
        finally:
            gym_app.DB_PATH = original_db_path

        with sqlite3.connect(tmp.name) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM plan_items WHERE plan_version_id = ? ORDER BY title",
                (version_id,),
            ).fetchall()
            by_title = {r["title"]: r for r in rows}

            # Parseable strength item
            bench = by_title["Bench Press"]
            assert bench["sets"] == "3-4"
            assert bench["set_count"] == 4
            assert bench["rest_seconds"] == 150
            assert "tempo" in bench["detail"]
            assert "rest" in bench["detail"]

            # Unparseable legacy item
            cycle = by_title["Cycle"]
            assert cycle["detail"] == "Cycle: 3-4 sets x 8-12 reps"
            assert cycle["sets"] is None

            # Conditioning-like item
            cond = by_title["Conditioning"]
            assert cond["item_type"] == "recovery"
            assert cond["muscle_group"] == "full body"
            assert cond["rest_seconds"] is None
            assert cond["set_count"] is None
    finally:
        os.unlink(tmp.name)


# --- generator field population ----------------------------------------------

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


def test_no_exercise_has_null_set_count(admin):
    items = generated_workout_items()
    exercises = [i for i in items if i["item_type"] == "exercise"]
    assert exercises
    for item in exercises:
        assert item["set_count"] is not None, f"{item['title']} has null set_count"


def test_no_conditioning_row_has_rest_seconds_or_set_and_rep_reps(admin):
    items = generated_workout_items()
    conditioning = [i for i in items if i["title"] == "Conditioning" or (i["muscle_group"] == "full body" and i["item_type"] == "recovery")]
    assert conditioning
    for item in conditioning:
        assert item["rest_seconds"] is None, f"{item['title']} has rest_seconds"
        assert item["set_count"] is None, f"{item['title']} has set_count"
        if item["reps"]:
            assert "min" in item["reps"] or "sec" in item["reps"], f"{item['title']} has set-and-rep reps: {item['reps']}"


def test_exercise_detail_contains_tempo_and_rest(admin):
    items = generated_workout_items()
    exercises = [i for i in items if i["item_type"] == "exercise" and "Day" in (i["day_label"] or "")]
    assert exercises
    detailed = [i for i in exercises if "tempo" in (i["detail"] or "") and "rest" in (i["detail"] or "")]
    assert detailed, "prescriptions should state tempo and rest"


def test_exercise_muscle_group_is_from_closed_list(admin):
    items = generated_workout_items()
    exercises = [i for i in items if i["item_type"] == "exercise" and i["muscle_group"]]
    assert exercises
    closed = {
        "chest", "back", "lats", "front delts", "side delts", "rear delts",
        "biceps", "triceps", "quads", "hamstrings", "glutes", "calves",
        "abs", "lower back", "full body",
    }
    for item in exercises:
        assert item["muscle_group"] in closed, f"{item['title']} has invalid muscle_group: {item['muscle_group']}"


# --- coach_note survival -----------------------------------------------------

def test_coach_note_survives_regeneration(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        gym_app.execute(
            "UPDATE members SET workout_time = '18:30' WHERE id = ?",
            (member["id"],),
        )
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

        # Generate once to discover which day_label Leg Press lands on.
        gym_app.generate_rule_based_plans(member)
        draft = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
        first_leg_press = gym_app.query_one(
            "SELECT * FROM plan_items WHERE plan_version_id = ? AND title = 'Leg Press' ORDER BY position",
            (draft["id"],),
        )
        assert first_leg_press is not None
        target_day = first_leg_press["day_label"]
        target_time = first_leg_press["slot_time"]

        # Clear drafts and create an approved version with a coach_note on that slot.
        gym_app.execute("DELETE FROM plan_items WHERE plan_version_id = ?", (draft["id"],))
        gym_app.execute("DELETE FROM plan_versions WHERE id = ?", (draft["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'admin', datetime('now'))",
            (member["id"],),
        )
        approved_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO plan_items (plan_version_id, day_label, slot_time, item_type, title, detail, rationale, position, coach_note)
            VALUES (?, ?, ?, 'exercise', 'Leg Press', '3x5', 'Legacy', 1, 'Keep feet high on platform')
            """,
            (approved_id, target_day, target_time),
        )

        # Regenerate
        gym_app.generate_rule_based_plans(member)

        new_draft = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout' AND status = 'draft' ORDER BY id DESC LIMIT 1",
            (member["id"],),
        )
        assert new_draft is not None
        new_item = gym_app.query_one(
            "SELECT * FROM plan_items WHERE plan_version_id = ? AND title = 'Leg Press' ORDER BY position",
            (new_draft["id"],),
        )
        assert new_item is not None
        assert new_item["coach_note"] == "Keep feet high on platform"


# --- helpers -----------------------------------------------------------------

def test_normalize_muscle_group_maps_lower_chest_to_chest():
    assert gym_app._normalize_muscle_group("lower chest") == "chest"


def test_normalize_muscle_group_passes_through_closed_list():
    for mg in gym_app._CLOSED_MUSCLE_GROUPS:
        assert gym_app._normalize_muscle_group(mg) == mg


def test_render_detail_from_fields_reproduces_legacy_shape():
    item = {
        "item_type": "exercise",
        "sets": "3-4",
        "reps": "6-10",
        "rpe": "7-8",
        "tempo": "3-1-1-0",
        "rest_seconds": 150,
    }
    detail = gym_app.render_detail_from_fields(item)
    assert detail == "3-4 sets × 6-10 reps · RPE 7-8 · tempo 3-1-1-0 · rest 2.5 min."


def test_render_detail_from_fields_returns_detail_for_recovery():
    item = {"item_type": "recovery", "detail": "10 min easy walk"}
    assert gym_app.render_detail_from_fields(item) == "10 min easy walk"
# --- weekly_volume -----------------------------------------------------------

def test_weekly_volume_sums_set_count_per_muscle_group_and_excludes_recovery():
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
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ?", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        conn = gym_app.db()
        conn.executemany(
            """
            INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, set_count, muscle_group, position)
            VALUES (?, 'Day 1', ?, ?, ?, 'Test', ?, ?, ?)
            """,
            [
                (version_id, "exercise", "Bench Press", "detail", 4, "chest", 0),
                (version_id, "exercise", "Fly", "detail", 3, "chest", 1),
                (version_id, "exercise", "Squat", "detail", 5, "quads", 2),
                (version_id, "recovery", "Cycle", "detail", None, "full body", 3),
            ],
        )
        conn.commit()
        result = gym_app.weekly_volume(member["id"], version_id)
        by_mg = {r["muscle_group"]: r for r in result}
        assert "chest" in by_mg
        assert by_mg["chest"]["sets"] == 7
        assert by_mg["chest"]["min"] == 10
        assert by_mg["chest"]["max"] == 25
        assert "quads" in by_mg
        assert by_mg["quads"]["sets"] == 5
        assert by_mg["quads"]["max"] == 25
        assert "full body" not in by_mg
        assert result == sorted(result, key=lambda x: x["muscle_group"])


def test_weekly_volume_defaults_to_max_20_for_small_muscles():
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
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ?", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, set_count, muscle_group, position)
            VALUES (?, 'Day 1', 'exercise', 'Curl', 'detail', 'Test', 3, 'biceps', 0)
            """,
            (version_id,),
        )
        result = gym_app.weekly_volume(member["id"], version_id)
        assert result[0]["max"] == 20


# --- weekly_volume -----------------------------------------------------------

def test_weekly_volume_sums_set_count_per_muscle_group_and_excludes_recovery():
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
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ?", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        conn = gym_app.db()
        conn.executemany(
            """
            INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, set_count, muscle_group, position)
            VALUES (?, 'Day 1', ?, ?, ?, 'Test', ?, ?, ?)
            """,
            [
                (version_id, "exercise", "Bench Press", "detail", 4, "chest", 0),
                (version_id, "exercise", "Fly", "detail", 3, "chest", 1),
                (version_id, "exercise", "Squat", "detail", 5, "quads", 2),
                (version_id, "recovery", "Cycle", "detail", None, "full body", 3),
            ],
        )
        conn.commit()
        result = gym_app.weekly_volume(member["id"], version_id)
        by_mg = {r["muscle_group"]: r for r in result}
        assert "chest" in by_mg
        assert by_mg["chest"]["sets"] == 7
        assert by_mg["chest"]["min"] == 10
        assert by_mg["chest"]["max"] == 25
        assert "quads" in by_mg
        assert by_mg["quads"]["sets"] == 5
        assert by_mg["quads"]["max"] == 25
        assert "full body" not in by_mg
        assert result == sorted(result, key=lambda x: x["muscle_group"])


def test_weekly_volume_defaults_to_max_20_for_small_muscles():
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
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ?", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, set_count, muscle_group, position)
            VALUES (?, 'Day 1', 'exercise', 'Curl', 'detail', 'Test', 3, 'biceps', 0)
            """,
            (version_id,),
        )
        result = gym_app.weekly_volume(member["id"], version_id)
        assert result[0]["max"] == 20


# --- propose_next_load -------------------------------------------------------

def test_propose_next_load_returns_none_when_no_logs():
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
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ?", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, reps, position)
            VALUES (?, 'Day 1', 'exercise', 'Bench Press', 'detail', 'Test', '6-10', 0)
            """,
            (version_id,),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        result = gym_app.propose_next_load(item_id)
        assert result["plan_item_id"] == item_id
        assert result["last_load_kg"] is None
        assert result["suggested_load_kg"] is None
        assert "No sets logged yet" in result["reason"]


def test_propose_next_load_increases_by_2_5_when_reps_at_top():
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
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ?", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, reps, position)
            VALUES (?, 'Day 1', 'exercise', 'Bench Press', 'detail', 'Test', '6-10', 0)
            """,
            (version_id,),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO set_logs (plan_item_id, member_id, set_number, reps_done, load_kg, logged_at)
            VALUES (?, ?, 1, 10, 80.0, datetime('now'))
            """,
            (item_id, member["id"]),
        )
        result = gym_app.propose_next_load(item_id)
        assert result["last_load_kg"] == 80.0
        assert result["suggested_load_kg"] == 82.5
        assert "2.5" in result["reason"]


def test_propose_next_load_increases_by_5_for_leg_press():
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
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ?", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, reps, position)
            VALUES (?, 'Day 1', 'exercise', 'Leg Press', 'detail', 'Test', '6-10', 0)
            """,
            (version_id,),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO set_logs (plan_item_id, member_id, set_number, reps_done, load_kg, logged_at)
            VALUES (?, ?, 1, 10, 100.0, datetime('now'))
            """,
            (item_id, member["id"]),
        )
        result = gym_app.propose_next_load(item_id)
        assert result["last_load_kg"] == 100.0
        assert result["suggested_load_kg"] == 105.0
        assert "5" in result["reason"]


def test_propose_next_load_holds_when_reps_below_top():
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
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ?", (member["id"],))
        gym_app.execute(
            "INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at) VALUES (?, 'workout', 'approved', 'rule', datetime('now'))",
            (member["id"],),
        )
        version_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO plan_items (plan_version_id, day_label, item_type, title, detail, rationale, reps, position)
            VALUES (?, 'Day 1', 'exercise', 'Bench Press', 'detail', 'Test', '6-10', 0)
            """,
            (version_id,),
        )
        item_id = gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]
        gym_app.execute(
            """
            INSERT INTO set_logs (plan_item_id, member_id, set_number, reps_done, load_kg, logged_at)
            VALUES (?, ?, 1, 8, 80.0, datetime('now'))
            """,
            (item_id, member["id"]),
        )
        result = gym_app.propose_next_load(item_id)
        assert result["last_load_kg"] == 80.0
        assert result["suggested_load_kg"] == 80.0
        assert "Hold" in result["reason"]


# --- diet_quality_notes ------------------------------------------------------

def test_diet_quality_notes_flags_low_protein_meal():
    member = {"weight_kg": 60, "height_cm": 170, "age": 30, "gender": "Male"}
    items = [
        {
            "item_type": "meal",
            "title": "Snack",
            "detail": "Ingredients: banana 1. Macros: ~100 kcal, protein 10 g, carbs 20 g.",
            "slot_time": "10:00",
        }
    ]
    notes = gym_app.diet_quality_notes(items, member)
    assert any("protein" in n and "20.0 g" in n for n in notes)


def test_diet_quality_notes_flags_feeding_gap_over_4_hours():
    member = {"weight_kg": 80, "height_cm": 170, "age": 30, "gender": "Male"}
    items = [
        {"item_type": "meal", "title": "Breakfast", "detail": "Macros: protein 30 g.", "slot_time": "08:00"},
        {"item_type": "meal", "title": "Lunch", "detail": "Macros: protein 40 g.", "slot_time": "13:00"},
    ]
    notes = gym_app.diet_quality_notes(items, member)
    assert any("Gap of 5 h 0 min" in n for n in notes)


def test_diet_quality_notes_returns_empty_when_all_fine():
    member = {"weight_kg": 80, "height_cm": 170, "age": 30, "gender": "Male"}
    items = [
        {"item_type": "meal", "title": "Breakfast", "detail": "Macros: protein 30 g.", "slot_time": "08:00"},
        {"item_type": "meal", "title": "Lunch", "detail": "Macros: protein 40 g.", "slot_time": "12:00"},
    ]
    assert gym_app.diet_quality_notes(items, member) == []


def test_diet_notes_appear_in_generated_diet_text():
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute("UPDATE members SET weight_kg = 50 WHERE id = ?", (member["id"],))
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        _, diet_text = gym_app.generate_rule_based_plans(member)
        assert "Nutrition notes:" in diet_text
