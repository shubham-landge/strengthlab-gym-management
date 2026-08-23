"""Shared mobile numbers: staff must be told, and must be able to resolve it."""

import app as gym_app
from conftest import csrf_for


def post(client, path, **fields):
    fields["csrf_token"] = csrf_for(client, "/members")
    return client.post(path, data=fields, follow_redirects=False)


def add_member(client, name, phone):
    post(client, "/members/add", name=name, phone=phone, plan_name="Monthly", fitness_level="Beginner")
    with gym_app.app.app_context():
        return gym_app.query_one("SELECT * FROM members WHERE name = ?", (name,))


def make_shared_pair(client, phone, first_name, second_name):
    with gym_app.app.app_context():
        gym_app.execute("DELETE FROM users WHERE username = ?", (gym_app.mobile_login_id(phone),))
    first = add_member(client, first_name, phone)
    second = add_member(client, second_name, phone)
    return first, second


def test_conflict_is_reported_on_the_member_edit_page(admin):
    phone = "+919000000301"
    _, second = make_shared_pair(admin, phone, "Owner One", "Clashing Two")

    body = admin.get(f"/members/{second['id']}/edit").get_data(as_text=True)
    assert "No login could be created" in body
    assert "Owner One" in body, "the page should name who holds the number"
    assert gym_app.mobile_login_id(phone) in body


def test_no_conflict_means_no_warning(admin):
    member = add_member(admin, "Unique Person", "+919000000302")
    body = admin.get(f"/members/{member['id']}/edit").get_data(as_text=True)
    assert "No login could be created" not in body


def test_admin_can_assign_a_distinct_login_id(admin):
    phone = "+919000000303"
    first, second = make_shared_pair(admin, phone, "Holder Three", "Needs Login Three")

    with gym_app.app.app_context():
        assert gym_app.get_member_login(second["id"]) is None

    post(
        admin,
        f"/members/{second['id']}/edit",
        name=second["name"],
        phone=phone,
        login_id="needslogin3",
        plan_name="Monthly",
    )

    with gym_app.app.app_context():
        assigned = gym_app.get_member_login(second["id"])
        holder = gym_app.get_member_login(first["id"])
    assert assigned is not None and assigned["username"] == "needslogin3"
    assert holder["username"] == gym_app.mobile_login_id(phone), "the original login is untouched"


def test_assigned_login_id_survives_a_later_phone_sync(admin):
    phone = "+919000000304"
    _, second = make_shared_pair(admin, phone, "Holder Four", "Pinned Four")
    post(admin, f"/members/{second['id']}/edit", name=second["name"], phone=phone,
         login_id="pinnedfour", plan_name="Monthly")

    with gym_app.app.app_context():
        # Re-syncing from the phone must not rename the pinned login back.
        gym_app.create_member_user(second["id"], phone)
        after = gym_app.get_member_login(second["id"])
    assert after["username"] == "pinnedfour"


def test_duplicate_login_id_is_rejected_with_a_message(admin):
    member = add_member(admin, "Wants Admin Name", "+919000000305")
    response = post(
        admin,
        f"/members/{member['id']}/edit",
        name=member["name"],
        phone=member["phone"],
        login_id="admin",
        plan_name="Monthly",
    )
    assert response.status_code == 200, "should re-render the form, not redirect"
    assert "already taken" in response.get_data(as_text=True)

    with gym_app.app.app_context():
        admin_user = gym_app.query_one("SELECT * FROM users WHERE username = 'admin'")
    assert admin_user["role"] == "admin", "the real admin account must be untouched"


def test_short_login_id_is_rejected(admin):
    member = add_member(admin, "Short Id Person", "+919000000306")
    response = post(admin, f"/members/{member['id']}/edit", name=member["name"],
                    phone=member["phone"], login_id="ab", plan_name="Monthly")
    assert response.status_code == 200
    assert "at least 4 characters" in response.get_data(as_text=True)


def test_assigned_login_can_actually_sign_in(client, admin):
    phone = "+919000000307"
    _, second = make_shared_pair(admin, phone, "Holder Seven", "Signs In Seven")
    post(admin, f"/members/{second['id']}/edit", name=second["name"], phone=phone,
         login_id="signsin7", plan_name="Monthly")

    with gym_app.app.app_context():
        gym_app.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE username = 'signsin7'",
            (gym_app.generate_password_hash("letmein123"),),
        )

    token = csrf_for(client)
    response = client.post(
        "/login", data={"username": "signsin7", "password": "letmein123", "csrf_token": token}
    )
    assert response.status_code == 302
    assert "/login" not in response.headers["Location"]


def test_mobile_login_still_works_and_tolerates_formatting(client, admin):
    """The login lookup was changed to try the ID as typed first."""
    phone = "+91 90000 00309"
    member = add_member(admin, "Mobile Login Person", phone)
    with gym_app.app.app_context():
        login = gym_app.get_member_login(member["id"])
        gym_app.execute(
            "UPDATE users SET password_hash = ?, must_change_password = 0 WHERE id = ?",
            (gym_app.generate_password_hash("phonepass1"), login["id"]),
        )

    for typed in ["9000000309", "+91 90000 00309", "+91-90000-00309"]:
        token = csrf_for(client)
        response = client.post(
            "/login", data={"username": typed, "password": "phonepass1", "csrf_token": token}
        )
        assert response.status_code == 302, f"login failed for {typed!r}"
        assert "/login" not in response.headers["Location"]
        client.get("/logout")


def test_staff_logins_are_unaffected(client):
    for username, password in [("admin", "admin123"), ("owner", "owner123"), ("accountant", "accountant123")]:
        token = csrf_for(client)
        response = client.post(
            "/login", data={"username": username, "password": password, "csrf_token": token}
        )
        assert response.status_code == 302, f"{username} could not sign in"
        client.get("/logout")


def test_login_conflict_helper_ignores_a_members_own_number(admin):
    member = add_member(admin, "Self Check", "+919000000308")
    with gym_app.app.app_context():
        conflict = gym_app.login_conflict("member", member["phone"], member_id=member["id"])
    assert conflict is None
