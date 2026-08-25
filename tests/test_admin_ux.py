import pytest
from app import app, db, query_one

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["WTF_CSRF_ENABLED"] = False
    with app.test_client() as client:
        with client.session_transaction() as sess:
            sess["user_id"] = 1  # Logged in as admin user
        yield client

def test_dashboard_today_queue_renders(client):
    rv = client.get("/")
    assert rv.status_code == 200
    html = rv.data.decode("utf-8")
    assert "Today&#39;s Action Queue" in html or "Today's Action Queue" in html
    assert "Plans Awaiting Approval" in html
    assert "Outstanding Dues" in html
    assert "Fast Check-In Member" in html
    assert "global-search-input" in html

def test_grouped_sidebar_navigation(client):
    rv = client.get("/")
    assert rv.status_code == 200
    html = rv.data.decode("utf-8")
    assert "nav-section-title" in html
    assert "Today" in html
    assert "People" in html
    assert "Money" in html
    assert "Programme" in html
    assert "Setup" in html

def test_member_hub_tabs(client):
    rv = client.get("/members/1")
    assert rv.status_code == 200
    html = rv.data.decode("utf-8")
    assert "member-hub-tabs" in html
    assert "Overview &amp; Today" in html or "Overview & Today" in html
    assert "Plans &amp; Review" in html or "Plans & Review" in html
    assert "Payments &amp; Renewals" in html or "Payments & Renewals" in html
