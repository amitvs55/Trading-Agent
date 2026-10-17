"""User accounts: names, roles, disabling, deleting, password resets and the profile."""

import pytest
from sqlalchemy import create_engine, inspect, text

from options.admin.repo import AdminRepo, LastAdmin, UserExists
from options.storage import make_engine
from tests.options.test_admin import api, auth, fast_hashing, repo  # noqa: F401  (pytest fixtures)

PW = "correct horse battery"


def test_old_users_table_gains_the_new_columns_in_place(tmp_path):
    url = f"sqlite:///{tmp_path}/old.db"
    old = create_engine(url)
    with old.begin() as conn:                       # the table as it existed in production before this change
        conn.execute(text("CREATE TABLE users (id INTEGER PRIMARY KEY, username VARCHAR(64) NOT NULL UNIQUE, "
                          "password_hash TEXT NOT NULL, role VARCHAR(16) NOT NULL, created_at DATETIME NOT NULL, "
                          "last_login_at DATETIME)"))
        conn.execute(text("INSERT INTO users (username, password_hash, role, created_at) "
                          "VALUES ('admin', 'x', 'admin', '2026-10-16 12:27:54')"))
    engine = make_engine(url)
    cols = {c["name"] for c in inspect(engine).get_columns("users")}
    assert {"full_name", "disabled"} <= cols
    [u] = AdminRepo(engine, secret_key="k").list_users()
    assert u["username"] == "admin" and u["full_name"] is None and u["disabled"] is False
    make_engine(url)                                # running it again changes nothing


def test_users_have_names_roles_and_guards(repo):
    admin = repo.create_user("admin", PW)
    amit = repo.create_user("Amit", PW, role="admin", full_name=" Amit Shinde ")
    assert repo.get_user(amit)["full_name"] == "Amit Shinde" and repo.get_user(amit)["username"] == "amit"
    with pytest.raises(UserExists):
        repo.create_user("AMIT", PW)
    with pytest.raises(ValueError):
        repo.create_user("guest", PW, role="superuser")

    viewer = repo.create_user("viewer1", PW, role="viewer")
    token = repo.create_session(viewer)
    repo.update_user(viewer, disabled=True)
    assert repo.resolve_session(token) is None and repo.authenticate("viewer1", PW) is None
    repo.update_user(viewer, disabled=False)
    assert repo.authenticate("viewer1", PW)["role"] == "viewer"

    repo.update_user(admin, role="viewer")          # amit is still an admin, so this is allowed
    with pytest.raises(LastAdmin):
        repo.update_user(amit, disabled=True)
    with pytest.raises(LastAdmin):
        repo.delete_user(amit)
    repo.delete_user(viewer)
    assert [u["username"] for u in repo.list_users()] == ["admin", "amit"]


def test_users_api(api, repo):
    me = repo.create_user("admin", PW)
    token = repo.create_session(me)
    h = auth(token)

    assert api.post("/api/admin/users", headers=h, json={"full_name": "Amit Shinde", "username": "amit",
                                                          "password": "short", "role": "admin"}).status_code == 422
    made = api.post("/api/admin/users", headers=h, json={"full_name": "Amit Shinde", "username": "amit",
                                                          "password": PW, "role": "admin"}).json()
    assert made["full_name"] == "Amit Shinde" and made["role"] == "admin" and "password" not in str(made)
    assert api.post("/api/admin/users", headers=h, json={"full_name": "X", "username": "amit", "password": PW,
                                                          "acknowledged_personal_use": True}).status_code == 409
    listed = api.get("/api/admin/users", headers=h).json()
    assert [u["username"] for u in listed["users"]] == ["admin", "amit"] and listed["roles"] == ["admin", "viewer"]

    # the new account signs in on its own and sees its name
    login = api.post("/api/auth/login", json={"username": "AMIT", "password": PW}).json()
    assert api.get("/api/auth/me", headers=auth(login["token"])).json()["full_name"] == "Amit Shinde"

    assert api.patch(f"/api/admin/users/{me}", headers=h, json={"disabled": True}).status_code == 422   # not yourself
    assert api.delete(f"/api/admin/users/{me}", headers=h).status_code == 422
    unconfirmed = api.post("/api/admin/users", headers=h, json={"full_name": "Guest", "username": "guest",
                                                                 "password": PW, "role": "viewer"})
    assert unconfirmed.status_code == 422 and unconfirmed.json()["detail"]["code"] == "personal_use"
    viewer = api.post("/api/admin/users", headers=h, json={"full_name": "Guest", "username": "guest", "password": PW,
                                                            "role": "viewer", "acknowledged_personal_use": True}).json()
    vt = api.post("/api/auth/login", json={"username": "guest", "password": PW}).json()["token"]
    assert api.get("/api/admin/users", headers=auth(vt)).status_code == 403                # viewers can't manage users
    assert api.patch(f"/api/admin/users/{viewer['id']}", headers=h, json={"role": "admin"}).json()["role"] == "admin"

    new_pw = "another long passphrase"
    assert api.post(f"/api/admin/users/{made['id']}/password", headers=h, json={"new_password": new_pw}).json()["ok"]
    assert api.get("/api/auth/me", headers=auth(login["token"])).status_code == 401           # signed out everywhere
    assert api.post("/api/auth/login", json={"username": "amit", "password": new_pw}).status_code == 200

    assert api.delete(f"/api/admin/users/{viewer['id']}", headers=h).json()["ok"]
    assert api.patch("/api/auth/profile", headers=h, json={"full_name": "Site Admin"}).json()["full_name"] == "Site Admin"
