"""Smoke tests: every page renders, every export builds, auth is enforced.

These exist because a missing database column silently broke the diet-plan PDF
(it returned HTTP 500 for every member) without anything failing loudly.
"""

import pytest

from conftest import csrf_for

PAGES = [
    "/",
    "/members",
    "/trainer-assignments",
    "/attendance",
    "/payments",
    "/reports",
    "/trainers",
    "/equipment",
    "/equipment/guide",
    "/announcements",
    "/content-insights",
    "/supplements",
    "/change-password",
]

MEMBER_PAGES = [
    "/members/{id}",
    "/members/{id}/edit",
    "/members/{id}/recommendations",
    "/members/{id}/recommendations/review",
]

BINARY_EXPORTS = [
    ("/members/{id}/diet.pdf", b"%PDF"),
    ("/members/{id}/recommendations.pdf", b"%PDF"),
]


@pytest.mark.parametrize("path", PAGES)
def test_pages_render(admin, path):
    assert admin.get(path).status_code == 200


@pytest.mark.parametrize("template", MEMBER_PAGES)
def test_member_pages_render(admin, template):
    assert admin.get(template.format(id=1)).status_code == 200


@pytest.mark.parametrize("template,magic", BINARY_EXPORTS)
def test_member_exports_build(admin, template, magic):
    response = admin.get(template.format(id=1))
    assert response.status_code == 200
    assert response.data.startswith(magic)


def test_payments_excel_export(admin):
    response = admin.get("/payments/export.xlsx")
    assert response.status_code == 200
    # xlsx files are zip archives.
    assert response.data.startswith(b"PK")


def test_owner_and_accountant_land_on_their_dashboards(client):
    for username, password, destination in [
        ("owner", "owner123", "/owner"),
        ("accountant", "accountant123", "/accountant"),
    ]:
        token = csrf_for(client)
        client.post(
            "/login",
            data={"username": username, "password": password, "csrf_token": token},
        )
        response = client.get("/")
        assert response.status_code == 302
        assert response.headers["Location"].endswith(destination)
        client.get("/logout")


def test_anonymous_is_redirected_to_login(client):
    response = client.get("/members")
    assert response.status_code == 302
    assert "/login" in response.headers["Location"]


def test_bad_credentials_are_rejected(client):
    token = csrf_for(client)
    response = client.post(
        "/login",
        data={"username": "admin", "password": "wrong-password", "csrf_token": token},
    )
    assert response.status_code == 200
    assert "Invalid username or password" in response.get_data(as_text=True)


def test_missing_member_does_not_500(admin):
    assert admin.get("/members/999999").status_code in {302, 404}
