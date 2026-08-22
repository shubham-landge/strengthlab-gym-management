"""Shared pytest fixtures.

Every test runs against a throwaway SQLite file seeded by the app's own
``init_db()``, so tests never touch the working ``gym_manager.db``.
"""

import os
import sys
import tempfile

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Configure the app before importing it: both settings are read at import time.
_TMP_DB = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_TMP_DB.close()
os.environ["GYM_DB_PATH"] = _TMP_DB.name
os.environ["DISABLE_PAYMENT_AUTOMATION"] = "1"
os.environ["SECRET_KEY"] = "test-secret-key"

sys.path.insert(0, BASE_DIR)

import app as gym_app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    with gym_app.app.app_context():
        gym_app.init_db()
    yield
    os.unlink(_TMP_DB.name)


@pytest.fixture()
def client():
    gym_app.app.config["TESTING"] = True
    with gym_app.app.test_client() as test_client:
        yield test_client


def csrf_for(client, path="/login"):
    """Prime the session and pull the CSRF token out of a rendered form."""
    body = client.get(path).get_data(as_text=True)
    marker = 'name="csrf_token" value="'
    start = body.index(marker) + len(marker)
    return body[start:body.index('"', start)]


@pytest.fixture()
def admin(client):
    """A client logged in as the seeded admin."""
    token = csrf_for(client)
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123", "csrf_token": token},
        follow_redirects=False,
    )
    assert response.status_code == 302, "admin login should redirect"
    return client
