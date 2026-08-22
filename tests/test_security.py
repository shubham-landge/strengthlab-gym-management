"""CSRF protection and session hardening."""

from conftest import csrf_for


def test_post_without_csrf_token_is_rejected(client):
    response = client.post("/login", data={"username": "admin", "password": "admin123"})
    assert response.status_code == 400


def test_post_with_wrong_csrf_token_is_rejected(client):
    csrf_for(client)  # establish a session token
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123", "csrf_token": "not-the-token"},
    )
    assert response.status_code == 400


def test_post_with_valid_csrf_token_succeeds(client):
    token = csrf_for(client)
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123", "csrf_token": token},
    )
    assert response.status_code == 302


def test_every_post_form_carries_a_csrf_field(admin):
    """A form without a token would break the moment it is submitted."""
    import re

    pages = ["/", "/members", "/payments", "/attendance", "/trainers", "/equipment"]
    form_tag = re.compile(r'<form\b[^>]*method="post"[^>]*>', re.IGNORECASE)
    for path in pages:
        body = admin.get(path).get_data(as_text=True)
        for match in form_tag.finditer(body):
            # The token input is emitted immediately after the opening tag.
            following = body[match.end():match.end() + 200]
            assert 'name="csrf_token"' in following, f"form without CSRF token on {path}"


def test_session_cookie_is_httponly(client):
    token = csrf_for(client)
    response = client.post(
        "/login",
        data={"username": "admin", "password": "admin123", "csrf_token": token},
    )
    cookies = response.headers.getlist("Set-Cookie")
    assert any("HttpOnly" in cookie for cookie in cookies)


def test_secret_key_is_not_the_old_hardcoded_default():
    import app as gym_app

    assert gym_app.app.config["SECRET_KEY"] != "local-gym-secret"
