"""Admin trash (V5-admin-trash; migration 0058): platform admins soft-delete, restore and purge users. A deleted user
cannot sign in (password, email code, token, session) and leaves the lists; self-delete and deleting the last owner
are refused; purge only from the trash."""
from __future__ import annotations

import uuid

from sqlalchemy import text

from app.models.platform_admin import PlatformAdmin
from app.services import email_delivery, login_code_service

A = "/api/v1/admin"
PASSWORD = "member-pass-12345"


def _grant(db, org):
    db.add(PlatformAdmin(user_id=uuid.UUID(org["user"]["id"]), organization_id=uuid.UUID(org["organization"]["id"])))
    db.flush()


def _member(client, h, role, name="Member"):
    r = client.post("/api/v1/users", headers=h, json={"email": f"{name.lower()}-{uuid.uuid4().hex[:6]}@example.com", "name": name,
                                                       "password": PASSWORD, "role": role})
    assert r.status_code in (200, 201), r.text
    return r.json()


def _login(client, email):
    return client.post("/api/v1/auth/login", data={"username": email, "password": PASSWORD})


def test_delete_hides_the_user_and_stops_sign_in_restore_brings_them_back(client, db_session, register_org):
    admin, org = register_org(), register_org()
    _grant(db_session, admin)
    m = _member(client, org["headers"], "editor", "Edith")
    token = _login(client, m["email"]).json()["access_token"]
    member_h = {"Authorization": f"Bearer {token}"}
    assert client.get("/api/v1/auth/me", headers=member_h).status_code == 200

    assert client.delete(f"{A}/users/{m['id']}", headers=admin["headers"]).status_code == 204
    assert client.get("/api/v1/auth/me", headers=member_h).status_code == 401            # the token stops working
    assert _login(client, m["email"]).status_code == 401                                 # same answer as a wrong password
    emails = lambda path, h: [u["email"] for u in client.get(path, headers=h).json()["items"]]
    assert m["email"] not in emails("/api/v1/users", org["headers"])
    assert m["email"] in emails("/api/v1/users?include_deleted=true", org["headers"])
    assert m["email"] not in emails(f"{A}/users?q={m['email']}", admin["headers"])
    trash = client.get(f"{A}/users?deleted_only=true&q={m['email']}", headers=admin["headers"]).json()["items"]
    assert [u["email"] for u in trash] == [m["email"]] and trash[0]["deleted_at"]
    row = db_session.execute(text("SELECT deleted_by_id FROM users WHERE id = :u"), {"u": m["id"]}).scalar_one()
    assert str(row) == admin["user"]["id"]

    r = client.post(f"{A}/users/{m['id']}/restore", headers=admin["headers"])
    assert r.status_code == 200 and r.json()["deleted_at"] is None
    assert _login(client, m["email"]).status_code == 200
    actions = db_session.execute(text("SELECT action FROM audit_logs WHERE resource_id = :u AND action LIKE 'user.%' ORDER BY created_at"),
                                 {"u": m["id"]}).scalars().all()
    assert actions[-2:] == ["user.deleted", "user.restored"]


def test_a_deleted_user_gets_no_sign_in_code(client, db_session, register_org, monkeypatch):
    sent = []
    monkeypatch.setattr(email_delivery, "is_configured", lambda: True)
    monkeypatch.setattr(email_delivery, "send", lambda **kw: sent.append(kw))
    monkeypatch.setattr(login_code_service.email_delivery, "is_configured", lambda: True, raising=False)
    monkeypatch.setattr(login_code_service.email_delivery, "send", lambda **kw: sent.append(kw), raising=False)
    admin, org = register_org(), register_org()
    _grant(db_session, admin)
    m = _member(client, org["headers"], "viewer", "Vera")
    client.delete(f"{A}/users/{m['id']}", headers=admin["headers"])
    r = client.post("/api/v1/auth/login-code/request", json={"email": m["email"]})
    assert r.status_code in (200, 202)                                                     # the same answer as for anyone
    assert all(m["email"] not in str(x.get("to")) for x in sent)


def test_self_delete_and_the_last_owner_are_refused(client, db_session, register_org):
    admin, org = register_org(), register_org()
    _grant(db_session, admin)
    r = client.delete(f"{A}/users/{admin['user']['id']}", headers=admin["headers"])
    assert r.status_code == 409 and "your own account" in r.text
    r = client.delete(f"{A}/users/{org['user']['id']}", headers=admin["headers"])        # the org's only owner
    assert r.status_code == 409 and "last owner" in r.text
    second = _member(client, org["headers"], "owner", "Otto")
    assert client.delete(f"{A}/users/{org['user']['id']}", headers=admin["headers"]).status_code == 204
    assert client.delete(f"{A}/users/{second['id']}", headers=admin["headers"]).status_code == 409


def test_purge_only_from_the_trash(client, db_session, register_org):
    admin, org = register_org(), register_org()
    _grant(db_session, admin)
    m = _member(client, org["headers"], "editor", "Pat")
    r = client.delete(f"{A}/users/{m['id']}/purge", headers=admin["headers"])
    assert r.status_code == 409 and "trash first" in r.text
    client.delete(f"{A}/users/{m['id']}", headers=admin["headers"])
    assert client.delete(f"{A}/users/{m['id']}/purge", headers=admin["headers"]).status_code == 204
    assert db_session.execute(text("SELECT count(*) FROM users WHERE id = :u"), {"u": m["id"]}).scalar_one() == 0
    assert client.get(f"{A}/users/{m['id']}", headers=admin["headers"]).status_code == 404


def test_trash_routes_are_for_platform_admins_only(client, register_org):
    org = register_org()
    m = _member(client, org["headers"], "editor", "Ned")
    for method, path in (("delete", f"/users/{m['id']}"), ("post", f"/users/{m['id']}/restore"), ("delete", f"/users/{m['id']}/purge")):
        assert getattr(client, method)(A + path, headers=org["headers"]).status_code == 403
    viewer = _member(client, org["headers"], "viewer", "Vic")
    vh = {"Authorization": f"Bearer {_login(client, viewer['email']).json()['access_token']}"}
    assert client.get("/api/v1/users?include_deleted=true", headers=vh).status_code == 403
