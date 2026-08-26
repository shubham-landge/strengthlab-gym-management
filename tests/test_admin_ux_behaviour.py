"""Behavioural cover for the admin UX work.

The original tests asserted that strings appeared in the HTML. That passes
whether or not the feature works: the "Plans & Review" label rendered while its
tab pointed at an element that did not exist, and the check-in box rendered
while submitting it wrote a row belonging to nobody.
"""

import re

import app as gym_app
from conftest import csrf_for


def member_id():
    with gym_app.app.app_context():
        return gym_app.query_one("SELECT id FROM members LIMIT 1")["id"]


def attendance_count():
    with gym_app.app.app_context():
        return gym_app.query_one("SELECT COUNT(*) AS n FROM attendance")["n"]


# --- check-in must never write a row belonging to nobody --------------------

def test_check_in_without_a_resolved_member_writes_nothing(admin):
    before = attendance_count()
    token = csrf_for(admin, "/")
    response = admin.post("/attendance", data={"csrf_token": token, "member_id": "", "action": "in"})
    assert response.status_code == 302
    assert attendance_count() == before, "an unresolved check-in must not create a row"


def test_check_in_with_an_unknown_member_writes_nothing(admin):
    before = attendance_count()
    token = csrf_for(admin, "/")
    admin.post("/attendance", data={"csrf_token": token, "member_id": "999999", "action": "in"})
    assert attendance_count() == before


def test_no_attendance_row_belongs_to_a_missing_member(admin):
    """Guards the data itself, whatever route wrote it."""
    with gym_app.app.app_context():
        orphans = gym_app.query_one(
            """
            SELECT COUNT(*) AS n FROM attendance
            WHERE member_id IS NULL OR member_id = ''
               OR member_id NOT IN (SELECT id FROM members)
            """
        )["n"]
    assert orphans == 0


def test_a_real_check_in_still_works(admin):
    before = attendance_count()
    token = csrf_for(admin, "/")
    admin.post("/attendance", data={"csrf_token": token, "member_id": str(member_id()), "action": "in"})
    assert attendance_count() == before + 1


# --- the member hub tabs must point at something ---------------------------

def test_every_hub_tab_has_a_target_on_the_page(admin):
    """Four of five tabs were anchors to ids that were never rendered."""
    html = admin.get(f"/members/{member_id()}").get_data(as_text=True)
    targets = re.findall(r'href="#(hub-[a-z-]+)"', html)
    assert targets, "the hub tabs should exist"
    for target in targets:
        assert f'id="{target}"' in html, f'tab "{target}" points at nothing'


# --- the approval screen must be reachable by clicking ---------------------

def test_the_dashboard_links_to_the_plan_approval_screen(admin):
    with gym_app.app.app_context():
        member = gym_app.query_one("SELECT * FROM members WHERE id = ?", (member_id(),))
        gym_app.execute("DELETE FROM plan_items")
        gym_app.execute("DELETE FROM plan_versions")
        gym_app.generate_rule_based_plans(member)

    html = admin.get("/").get_data(as_text=True)
    assert f"/members/{member_id()}/plan/review" in html, \
        "a pending plan must link to the screen that approves it"


def test_the_member_record_links_to_the_plan_approval_screen(admin):
    html = admin.get(f"/members/{member_id()}").get_data(as_text=True)
    assert f"/members/{member_id()}/plan/review" in html


def test_the_approval_screen_is_reachable_from_those_links(admin):
    assert admin.get(f"/members/{member_id()}/plan/review").status_code == 200
