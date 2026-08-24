"""Phase 1 schema and migration tests for the plan engine.

Covers new tables, member time columns, index creation, legacy plan migration,
and idempotence against both a fresh database and a copy of the real one.
"""

import os
import shutil
import sqlite3
import tempfile

import pytest

import app as gym_app


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

def test_member_time_columns_exist_on_fresh_database():
    cols = table_columns(gym_app.DB_PATH, "members")
    assert {"wake_time", "sleep_time", "workout_time"}.issubset(cols)


def test_plan_versions_table_exists():
    assert table_exists(gym_app.DB_PATH, "plan_versions")


def test_plan_items_table_exists():
    assert table_exists(gym_app.DB_PATH, "plan_items")


def test_plan_reviews_table_exists():
    assert table_exists(gym_app.DB_PATH, "plan_reviews")


def test_plan_versions_index_exists():
    assert index_exists(gym_app.DB_PATH, "idx_plan_versions_member_type_status")


# --- migration logic ---------------------------------------------------------

def test_legacy_workout_plan_migrated_to_approved_version():
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        # Seed a legacy plan if the demo member is empty
        if not member["workout_plan"]:
            gym_app.execute(
                "UPDATE members SET workout_plan = ? WHERE id = ?",
                ("Legacy workout text", member["id"]),
            )
            member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

        # Clear any previously migrated versions so the migration runs fresh
        gym_app.execute("DELETE FROM plan_items WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ?)", (member["id"],))
        gym_app.execute("DELETE FROM plan_reviews WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ?)", (member["id"],))
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ?", (member["id"],))

        gym_app.init_db()

        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'workout'",
            (member["id"],),
        )
        assert version is not None
        assert version["status"] == "approved"
        assert version["provenance"] == "admin"

        item = gym_app.query_one(
            "SELECT * FROM plan_items WHERE plan_version_id = ?",
            (version["id"],),
        )
        assert item is not None
        assert item["detail"] == member["workout_plan"]
        assert "Migrated from members.workout_plan" in item["rationale"]


def test_legacy_diet_plan_migrated_to_approved_version():
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        if not member["diet_plan"]:
            gym_app.execute(
                "UPDATE members SET diet_plan = ? WHERE id = ?",
                ("Legacy diet text", member["id"]),
            )
            member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member["id"],))

        gym_app.execute("DELETE FROM plan_items WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ?)", (member["id"],))
        gym_app.execute("DELETE FROM plan_reviews WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ?)", (member["id"],))
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ?", (member["id"],))

        gym_app.init_db()

        version = gym_app.query_one(
            "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = 'diet'",
            (member["id"],),
        )
        assert version is not None
        assert version["status"] == "approved"
        assert version["provenance"] == "admin"

        item = gym_app.query_one(
            "SELECT * FROM plan_items WHERE plan_version_id = ?",
            (version["id"],),
        )
        assert item is not None
        assert item["detail"] == member["diet_plan"]
        assert item["item_type"] == "meal"


def test_migration_is_idempotent():
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        gym_app.execute(
            "UPDATE members SET workout_plan = ? WHERE id = ?",
            ("Idempotence test plan", member["id"]),
        )

        # Clear and run once
        gym_app.execute("DELETE FROM plan_items WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ?)", (member["id"],))
        gym_app.execute("DELETE FROM plan_reviews WHERE plan_version_id IN (SELECT id FROM plan_versions WHERE member_id = ?)", (member["id"],))
        gym_app.execute("DELETE FROM plan_versions WHERE member_id = ?", (member["id"],))
        gym_app.init_db()

        first_count = gym_app.query_one(
            "SELECT COUNT(*) AS count FROM plan_versions WHERE member_id = ? AND plan_type = 'workout'",
            (member["id"],),
        )["count"]
        assert first_count == 1

        # Run again — must not duplicate
        gym_app.init_db()

        second_count = gym_app.query_one(
            "SELECT COUNT(*) AS count FROM plan_versions WHERE member_id = ? AND plan_type = 'workout'",
            (member["id"],),
        )["count"]
        assert second_count == 1


# --- real database copy ------------------------------------------------------

def test_migration_against_copy_of_real_database():
    """A temporary copy of gym_manager.db must survive init_db() and migrate plans."""
    real_db = os.path.join(gym_app.BASE_DIR, "gym_manager.db")
    if not os.path.exists(real_db):
        pytest.skip("Real gym_manager.db not found")

    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    shutil.copy(real_db, tmp.name)

    try:
        with sqlite3.connect(tmp.name) as conn:
            conn.row_factory = sqlite3.Row
            members_with_plans = conn.execute(
                "SELECT id, workout_plan, diet_plan FROM members WHERE COALESCE(workout_plan, '') != '' OR COALESCE(diet_plan, '') != ''"
            ).fetchall()
            if not members_with_plans:
                pytest.skip("Real database has no members with legacy plans")

        # Patch DB_PATH, run init_db, then restore
        original_db_path = gym_app.DB_PATH
        gym_app.DB_PATH = tmp.name
        try:
            gym_app.init_db()
        finally:
            gym_app.DB_PATH = original_db_path

        with sqlite3.connect(tmp.name) as conn:
            conn.row_factory = sqlite3.Row
            for row in members_with_plans:
                member_id = row["id"]
                for plan_type in ("workout", "diet"):
                    text = row[f"{plan_type}_plan"]
                    if not text or not text.strip():
                        continue
                    version = conn.execute(
                        "SELECT * FROM plan_versions WHERE member_id = ? AND plan_type = ? AND status = 'approved'",
                        (member_id, plan_type),
                    ).fetchone()
                    assert version is not None, f"member {member_id} {plan_type} was not migrated"
                    item = conn.execute(
                        "SELECT * FROM plan_items WHERE plan_version_id = ?",
                        (version["id"],),
                    ).fetchone()
                    assert item is not None
                    assert item["detail"] == text
    finally:
        os.unlink(tmp.name)


# --- member time fields persistence ------------------------------------------

def test_add_member_persists_wake_sleep_workout_times(admin):
    from conftest import csrf_for
    token = csrf_for(admin, "/members")
    response = admin.post(
        "/members/add",
        data={
            "name": "Time Test Member",
            "phone": "+919988776655",
            "plan_name": "Monthly",
            "fitness_level": "Beginner",
            "wake_time": "06:30",
            "sleep_time": "23:00",
            "workout_time": "18:30",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members WHERE phone = ?", ("+919988776655",))
    assert member["wake_time"] == "06:30"
    assert member["sleep_time"] == "23:00"
    assert member["workout_time"] == "18:30"


def test_edit_member_persists_wake_sleep_workout_times(admin):
    from conftest import csrf_for
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        member_id = member["id"]
    token = csrf_for(admin, f"/members/{member_id}/edit")
    response = admin.post(
        f"/members/{member_id}/edit",
        data={
            "name": member["name"],
            "phone": member["phone"],
            "plan_name": member["plan_name"],
            "fitness_level": member["fitness_level"],
            "wake_time": "07:00",
            "sleep_time": "22:30",
            "workout_time": "17:00",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with gym_app.app.app_context():
        updated = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member_id,))
    assert updated["wake_time"] == "07:00"
    assert updated["sleep_time"] == "22:30"
    assert updated["workout_time"] == "17:00"


def test_edit_member_clears_times_when_empty_string_submitted(admin):
    from conftest import csrf_for
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members LIMIT 1")
        member_id = member["id"]
        gym_app.execute(
            "UPDATE members SET wake_time = ?, sleep_time = ?, workout_time = ? WHERE id = ?",
            ("06:00", "23:00", "18:00", member_id),
        )
    token = csrf_for(admin, f"/members/{member_id}/edit")
    response = admin.post(
        f"/members/{member_id}/edit",
        data={
            "name": member["name"],
            "phone": member["phone"],
            "plan_name": member["plan_name"],
            "fitness_level": member["fitness_level"],
            "wake_time": "",
            "sleep_time": "",
            "workout_time": "",
            "csrf_token": token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 302
    with gym_app.app.app_context():
        updated = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member_id,))
    assert updated["wake_time"] is None or updated["wake_time"] == ""
    assert updated["sleep_time"] is None or updated["sleep_time"] == ""
    assert updated["workout_time"] is None or updated["workout_time"] == ""
