"""Exactly one approved plan version may be live per member and plan type."""

import sqlite3

import pytest

import app as gym_app


def make_version(member_id, plan_type, status):
    gym_app.execute(
        """
        INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at)
        VALUES (?, ?, ?, 'rule', '2026-01-01')
        """,
        (member_id, plan_type, status),
    )
    return gym_app.query_one("SELECT last_insert_rowid() AS id")["id"]


def test_a_second_approved_version_is_rejected_by_the_database(admin):
    with gym_app.app.app_context():
        member_id = gym_app.query_one("SELECT id FROM members LIMIT 1")["id"]
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        make_version(member_id, "diet", "approved")
        with pytest.raises(sqlite3.IntegrityError):
            make_version(member_id, "diet", "approved")


def test_different_plan_types_can_both_be_approved(admin):
    with gym_app.app.app_context():
        member_id = gym_app.query_one("SELECT id FROM members LIMIT 1")["id"]
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        make_version(member_id, "diet", "approved")
        make_version(member_id, "workout", "approved")
        count = gym_app.query_one(
            "SELECT COUNT(*) AS c FROM plan_versions WHERE status = 'approved'"
        )["c"]
    assert count == 2


def test_many_superseded_versions_are_allowed(admin):
    """The guard is on 'approved' only - history must not be constrained."""
    with gym_app.app.app_context():
        member_id = gym_app.query_one("SELECT id FROM members LIMIT 1")["id"]
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        for _ in range(4):
            make_version(member_id, "diet", "superseded")
        for _ in range(3):
            make_version(member_id, "diet", "draft")
        make_version(member_id, "diet", "approved")
        counts = dict(
            (r["status"], r["n"])
            for r in gym_app.query_all(
                "SELECT status, COUNT(*) AS n FROM plan_versions GROUP BY status"
            )
        )
    assert counts == {"superseded": 4, "draft": 3, "approved": 1}


def test_approving_supersedes_the_previous_version(admin):
    """The normal approval path must not trip the new unique index."""
    with gym_app.app.app_context():
        member_id = gym_app.query_one("SELECT id FROM members LIMIT 1")["id"]
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        first = make_version(member_id, "diet", "approved")
        second = make_version(member_id, "diet", "draft")

    from conftest import csrf_for
    token = csrf_for(admin, "/members")
    response = admin.post(
        f"/members/{member_id}/plan-versions/{second}/approve",
        data={"csrf_token": token, "note": "newer plan"},
    )
    assert response.status_code in (200, 302)

    with gym_app.app.app_context():
        rows = {
            r["id"]: r["status"]
            for r in gym_app.query_all("SELECT id, status FROM plan_versions")
        }
    assert rows[second] == "approved"
    assert rows[first] == "superseded", "the previous approval must be retired"


def test_migration_retires_duplicate_approved_versions(admin, tmp_path):
    """A database that already has several approved versions is repaired, not rejected."""
    db_path = tmp_path / "legacy.db"

    original = gym_app.DB_PATH
    gym_app.DB_PATH = str(db_path)
    try:
        with gym_app.app.app_context():
            gym_app.init_db()
        # Drop the guard so we can plant the bad historical state.
        conn = sqlite3.connect(db_path)
        conn.execute("DROP INDEX IF EXISTS idx_plan_versions_one_approved")
        for _ in range(4):
            conn.execute(
                """
                INSERT INTO plan_versions (member_id, plan_type, status, provenance, generated_at)
                VALUES (1, 'diet', 'approved', 'rule', '2026-01-01')
                """
            )
        conn.commit()
        before = conn.execute(
            "SELECT COUNT(*) FROM plan_versions WHERE status='approved' AND plan_type='diet' AND member_id=1"
        ).fetchone()[0]
        conn.close()
        assert before == 4

        # Re-running the migration must repair rather than fail.
        with gym_app.app.app_context():
            gym_app.init_db()

        conn = sqlite3.connect(db_path)
        after = conn.execute(
            "SELECT COUNT(*) FROM plan_versions WHERE status='approved' AND plan_type='diet' AND member_id=1"
        ).fetchone()[0]
        superseded = conn.execute(
            "SELECT COUNT(*) FROM plan_versions WHERE status='superseded'"
        ).fetchone()[0]
        conn.close()
    finally:
        gym_app.DB_PATH = original

    assert after == 1, "only the newest approval survives"
    assert superseded >= 3, "the older ones are retired, not deleted"
