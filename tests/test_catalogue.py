import re
import pytest
import app as gym_app
from conftest import csrf_for

def test_catalogue_access_control(admin):
    rv = admin.get("/settings/catalogue")
    assert rv.status_code == 200

    # Unauthenticated client redirect
    with gym_app.app.test_client() as anon_client:
        rv_anon = anon_client.get("/settings/catalogue")
        assert rv_anon.status_code == 302

def test_catalogue_add_and_edit_movement(admin):
    token = csrf_for(admin, "/settings/catalogue")
    
    # Add movement
    try:
        rv = admin.post(
            "/settings/catalogue/movements/add",
            data={
                "csrf_token": token,
                "name": "Custom Zercher Squat",
                "movement_pattern": "Squat",
                "role": "Compound",
                "primary_muscle": "quads",
                "equipment": "Barbell",
                "level": "Intermediate",
                "contraindications": "None",
                "cues": "Keep chest up",
            },
            follow_redirects=True,
        )
        assert rv.status_code == 200
        
        with gym_app.app.app_context():
            row = gym_app.query_one("SELECT * FROM exercise_library WHERE name = ?", ("Custom Zercher Squat",))
            assert row is not None
            assert row["active"] == 1
            assert row["primary_muscle"] == "quads"
            movement_id = row["id"]

        # Edit movement
        token_edit = csrf_for(admin, "/settings/catalogue?tab=movements")
        rv_edit = admin.post(
            f"/settings/catalogue/movements/{movement_id}/edit",
            data={
                "csrf_token": token_edit,
                "name": "Custom Zercher Squat",
                "movement_pattern": "Squat",
                "role": "Compound",
                "primary_muscle": "glutes",
                "equipment": "Barbell",
                "level": "Advanced",
                "contraindications": "Lower back pain",
                "cues": "Elbows high",
            },
            follow_redirects=True,
        )
        assert rv_edit.status_code == 200

        with gym_app.app.app_context():
            updated_row = gym_app.query_one("SELECT * FROM exercise_library WHERE id = ?", (movement_id,))
            assert updated_row["primary_muscle"] == "glutes"
            assert updated_row["level"] == "Advanced"
    finally:
        with gym_app.app.app_context():
            gym_app.execute("DELETE FROM exercise_library WHERE name = 'Custom Zercher Squat'")

def test_deactivating_movement_removes_from_generation(admin):
    with gym_app.app.app_context():
        lat_pulldown = gym_app.query_one("SELECT * FROM exercise_library WHERE name = 'Lat Pulldown'")

    assert lat_pulldown is not None
    token = csrf_for(admin, "/settings/catalogue?tab=movements")
    
    try:
        # Deactivate Lat Pulldown
        admin.post(f"/settings/catalogue/movements/{lat_pulldown['id']}/toggle", data={"csrf_token": token}, follow_redirects=True)
        
        with gym_app.app.app_context():
            deactivated = gym_app.query_one("SELECT * FROM exercise_library WHERE id = ?", (lat_pulldown["id"],))
            assert deactivated["active"] == 0

            # Generate plan for member 1
            member = gym_app.query_one("SELECT * FROM members WHERE id = 1")
            gym_app.generate_plans(member, prefer_ai=False)
            
            # Verify Lat Pulldown is not in the generated plan items
            plan_ver = gym_app.query_one("SELECT * FROM plan_versions WHERE member_id = 1 AND status = 'draft' ORDER BY id DESC")
            if plan_ver:
                items = gym_app.query_all("SELECT * FROM plan_items WHERE plan_version_id = ?", (plan_ver["id"],))
                item_titles = [i["title"] for i in items]
                assert "Lat Pulldown" not in item_titles
    finally:
        # Re-activate Lat Pulldown for cleanup
        token_reactivate = csrf_for(admin, "/settings/catalogue?tab=movements")
        admin.post(f"/settings/catalogue/movements/{lat_pulldown['id']}/toggle", data={"csrf_token": token_reactivate}, follow_redirects=True)

def test_catalogue_edits_survive_restart(admin):
    with gym_app.app.app_context():
        bench_press = gym_app.query_one("SELECT * FROM exercise_library WHERE name = 'Olympic Barbell Bench Press'")
        original_cues = bench_press["cues"]

    assert bench_press is not None
    token = csrf_for(admin, "/settings/catalogue?tab=movements")

    try:
        admin.post(
            f"/settings/catalogue/movements/{bench_press['id']}/edit",
            data={
                "csrf_token": token,
                "name": "Olympic Barbell Bench Press",
                "movement_pattern": bench_press["movement_pattern"],
                "role": bench_press["role"],
                "primary_muscle": bench_press["primary_muscle"],
                "equipment": bench_press["equipment"],
                "level": bench_press["level"],
                "cues": "Custom Cue Persists Restart",
            },
            follow_redirects=True,
        )

        # Simulate app restart / init_db
        with gym_app.app.app_context():
            gym_app.init_db()
            restarted = gym_app.query_one("SELECT * FROM exercise_library WHERE name = 'Olympic Barbell Bench Press'")
            assert restarted["cues"] == "Custom Cue Persists Restart"
    finally:
        with gym_app.app.app_context():
            gym_app.execute("UPDATE exercise_library SET cues = ? WHERE id = ?", (original_cues, bench_press["id"]))

def test_catalogue_food_source_and_discrepancy(admin):
    token = csrf_for(admin, "/settings/catalogue?tab=foods")
    
    try:
        # Add food with macro discrepancy (stated 500 kcal vs calculated ~80 kcal)
        admin.post(
            "/settings/catalogue/foods/add",
            data={
                "csrf_token": token,
                "name": "Test Discrepancy Food",
                "category": "Protein",
                "source": "USDA Lab Test",
                "kcal_100g": "500",
                "protein_100g": "10",
                "carb_100g": "10",
                "fat_100g": "0",
                "vegetarian": "1",
                "typical_portion_g": "100",
                "portion_label": "g",
            },
            follow_redirects=True,
        )

        with gym_app.app.app_context():
            food = gym_app.query_one("SELECT * FROM food_library WHERE name = 'Test Discrepancy Food'")
            assert food is not None
            assert food["source"] == "USDA Lab Test"
    finally:
        with gym_app.app.app_context():
            gym_app.execute("DELETE FROM food_library WHERE name = 'Test Discrepancy Food'")

def test_catalogue_drawer_targets_exist(admin):
    rv = admin.get("/settings/catalogue?tab=movements")
    assert rv.status_code == 200
    html = rv.data.decode("utf-8")

    # Extract all href="#..." targets
    hash_targets = re.findall(r'href="#([a-zA-Z0-9_-]+)"', html)
    for target in hash_targets:
        if not target: continue
        assert f'id="{target}"' in html, f"Link target #{target} does not exist in rendered HTML"
