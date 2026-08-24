"""Adding an AI key through the UI: storage, secrecy, and access control."""

import pytest

import app as gym_app
from conftest import csrf_for
from services.secret_store import decrypt_secret, encrypt_secret, mask_secret

REAL_KEY = "AIzaSyFakeExampleKeyForTests123456789"


def post(client, **fields):
    fields["csrf_token"] = csrf_for(client, "/settings/ai")
    return client.post("/settings/ai", data=fields, follow_redirects=True)


def clear_credentials():
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM ai_credentials")


# --- encryption ------------------------------------------------------------

def test_round_trip_and_wrong_key():
    blob = encrypt_secret(REAL_KEY, "secret-one")
    assert blob != REAL_KEY, "must not be stored in the clear"
    assert decrypt_secret(blob, "secret-one") == REAL_KEY
    assert decrypt_secret(blob, "secret-two") is None, "a rotated key must not decrypt"


def test_mask_keeps_only_the_ends():
    masked = mask_secret(REAL_KEY)
    assert masked.startswith("AIza") and masked.endswith(REAL_KEY[-4:])
    assert REAL_KEY not in masked


def test_decrypt_of_rubbish_returns_none_rather_than_raising():
    assert decrypt_secret("not-a-token", "secret") is None


# --- storage ---------------------------------------------------------------

def test_saved_key_is_encrypted_at_rest(admin):
    clear_credentials()
    post(admin, action="add", provider="gemini", api_key=REAL_KEY, models="gemini-flash-latest")

    with gym_app.app.app_context():
        row = gym_app.query_one("SELECT * FROM ai_credentials ORDER BY id DESC LIMIT 1")
    assert row is not None
    assert REAL_KEY not in row["encrypted_key"], "the raw key must never hit the database"
    assert decrypt_secret(row["encrypted_key"], gym_app.app.config["SECRET_KEY"]) == REAL_KEY


def test_the_key_is_never_shown_back_on_the_page(admin):
    clear_credentials()
    post(admin, action="add", provider="gemini", api_key=REAL_KEY, models="gemini-flash-latest")
    body = admin.get("/settings/ai").get_data(as_text=True)
    assert REAL_KEY not in body, "the full key must never be rendered"
    assert mask_secret(REAL_KEY) in body, "the masked hint should be shown"


def test_a_saved_key_enables_ai_generation(admin):
    clear_credentials()
    with gym_app.app.app_context():
        assert gym_app.ai_generation_enabled() is False

    post(admin, action="add", provider="gemini", api_key=REAL_KEY, models="gemini-flash-latest")

    with gym_app.app.app_context():
        assert gym_app.ai_generation_enabled() is True
        providers = gym_app.configured_ai_providers()
    assert providers[0]["name"] == "gemini"
    assert REAL_KEY in providers[0]["keys"]


def test_paused_key_is_not_used(admin):
    clear_credentials()
    post(admin, action="add", provider="gemini", api_key=REAL_KEY, models="gemini-flash-latest")
    with gym_app.app.app_context():
        row = gym_app.query_one("SELECT id FROM ai_credentials ORDER BY id DESC LIMIT 1")
    post(admin, action="toggle", credential_id=str(row["id"]))
    with gym_app.app.app_context():
        assert gym_app.ai_generation_enabled() is False


def test_deleting_a_key_removes_it(admin):
    clear_credentials()
    post(admin, action="add", provider="gemini", api_key=REAL_KEY, models="gemini-flash-latest")
    with gym_app.app.app_context():
        row = gym_app.query_one("SELECT id FROM ai_credentials ORDER BY id DESC LIMIT 1")
    post(admin, action="delete", credential_id=str(row["id"]))
    with gym_app.app.app_context():
        assert gym_app.query_all("SELECT * FROM ai_credentials") == []


def test_an_unreadable_key_is_skipped_not_crashed(admin):
    """A rotated SECRET_KEY must degrade to rules, not take the app down."""
    clear_credentials()
    with gym_app.app.app_context():
        gym_app.execute(
            "INSERT INTO ai_credentials (provider, encrypted_key, key_hint, models) VALUES ('gemini', ?, 'AIza••••1234', 'gemini-flash-latest')",
            (encrypt_secret(REAL_KEY, "a-different-secret-key"),),
        )
        assert gym_app.ai_generation_enabled() is False
    assert admin.get("/settings/ai").status_code == 200


# --- validation and access control -----------------------------------------

def test_short_input_is_rejected(admin):
    clear_credentials()
    response = post(admin, action="add", provider="gemini", api_key="abc")
    assert "does not look like an API key" in response.get_data(as_text=True)
    with gym_app.app.app_context():
        assert gym_app.query_all("SELECT * FROM ai_credentials") == []


def test_unknown_provider_is_rejected(admin):
    clear_credentials()
    post(admin, action="add", provider="hackerprovider", api_key=REAL_KEY)
    with gym_app.app.app_context():
        assert gym_app.query_all("SELECT * FROM ai_credentials") == []


def test_members_and_trainers_cannot_reach_the_page(client, admin):
    """Only admin and owner may manage credentials."""
    with gym_app.app.app_context():
        user = gym_app.query_one("SELECT * FROM users WHERE role = 'trainer' AND trainer_id IS NOT NULL LIMIT 1")
        gym_app.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
            (gym_app.generate_password_hash("trainerpass1"), user["id"]),
        )
    token = csrf_for(client)
    client.post("/login", data={"username": user["username"], "password": "trainerpass1", "csrf_token": token})
    assert client.get("/settings/ai").status_code == 302, "a trainer must be redirected away"


def test_anonymous_is_redirected(client):
    response = client.get("/settings/ai")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_the_page_states_the_encryption_limits(admin):
    """The page must not overclaim what encryption at rest protects."""
    body = admin.get("/settings/ai").get_data(as_text=True)
    assert "does" in body and "not</strong> protect" in body
