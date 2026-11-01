"""Platform admin (Step 14B): /api/v1/admin reads across organizations for platform admins only; a grant is a
platform_admins row read on every request; tenant routes keep their isolation even for a platform admin."""
from __future__ import annotations

import uuid

from sqlalchemy import delete

from app.models.platform_admin import PlatformAdmin

A = "/api/v1/admin"


def _grant(db, org):
    db.add(PlatformAdmin(user_id=uuid.UUID(org["user"]["id"]), organization_id=uuid.UUID(org["organization"]["id"])))
    db.flush()


def _member(client, h, role, name):
    r = client.post("/api/v1/users", headers=h, json={"email": f"{name.lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}@example.com", "name": name,
                    "password": "member-pass-12345", "role": role})
    assert r.status_code in (200, 201), r.text
    return r.json()


def _login(client, email):
    tok = client.post("/api/v1/auth/login", data={"username": email, "password": "member-pass-12345"}).json()["access_token"]
    return {"Authorization": f"Bearer {tok}"}


def test_admin_routes_are_for_platform_admins_only(client, register_org):
    org = register_org()
    viewer = _member(client, org["headers"], "viewer", "Viewer")
    paths = ("/overview", "/organizations", "/users", f"/users/{org['user']['id']}")
    for path in paths:
        assert client.get(A + path).status_code == 401
        assert client.get(A + path, headers=org["headers"]).status_code == 403          # an organization owner
        assert client.get(A + path, headers=_login(client, viewer["email"])).status_code == 403
    assert client.get("/api/v1/auth/me", headers=org["headers"]).json()["is_platform_admin"] is False


def test_platform_admin_reads_every_organization(client, db_session, register_org):
    a, b = register_org(name="Alpha Org"), register_org(name="Beta Org")
    member = _member(client, b["headers"], "editor", "Bea Editor")
    _grant(db_session, a)
    h = a["headers"]
    orgs = client.get(f"{A}/organizations?limit=200&q=Org", headers=h).json()
    counts = {o["name"]: o["user_count"] for o in orgs["items"]}
    assert counts["Alpha Org"] == 1 and counts["Beta Org"] == 2
    beta = client.get(f"{A}/organizations?q=Beta Org", headers=h).json()
    assert beta["total"] == 1 and beta["items"][0]["slug"] == b["organization"]["slug"]
    found = client.get(f"{A}/users", headers=h, params={"q": member["email"]}).json()
    assert found["total"] == 1 and found["items"][0]["organization_name"] == "Beta Org" and found["items"][0]["role"] == "editor"
    by_org = client.get(f"{A}/users", headers=h, params={"q": "Beta Org", "status": "active"}).json()
    assert by_org["total"] == 2
    page = client.get(f"{A}/users", headers=h, params={"q": "Org", "limit": 1}).json()
    assert len(page["items"]) == 1 and page["total"] >= 3
    one = client.get(f"{A}/users/{member['id']}", headers=h)
    assert one.status_code == 200 and one.json()["organization_name"] == "Beta Org"
    assert client.get(f"{A}/users/{uuid.uuid4()}", headers=h).status_code == 404
    by_email = client.get(f"{A}/users", headers=h, params={"q": "Org", "sort_by": "email", "sort_dir": "asc"}).json()["items"]
    assert [u["email"] for u in by_email] == sorted(u["email"] for u in by_email)
    assert client.get(f"{A}/users", headers=h, params={"sort_by": "password_hash"}).status_code == 422


def test_overview_counts_organizations_and_users(client, db_session, register_org):
    a = register_org()
    _grant(db_session, a)
    before = client.get(f"{A}/overview", headers=a["headers"]).json()
    b = register_org()
    _member(client, b["headers"], "viewer", "Vic")
    after = client.get(f"{A}/overview", headers=a["headers"]).json()
    assert after["organizations"]["total"] - before["organizations"]["total"] == 1
    assert after["users"]["total"] - before["users"]["total"] == 2
    assert after["organizations"]["active"] >= after["organizations"]["total"] - before["organizations"]["total"]
    assert after["users"]["active"] >= 0 and after["failed_sync_jobs_24h"] >= 0 and after["failed_ai_jobs_24h"] >= 0
    assert after["as_of"]


def test_a_grant_is_read_on_every_request(client, db_session, register_org):
    a = register_org()
    h = a["headers"]
    _grant(db_session, a)
    assert client.get("/api/v1/auth/me", headers=h).json()["is_platform_admin"] is True
    assert client.get(f"{A}/overview", headers=h).status_code == 200
    db_session.execute(delete(PlatformAdmin).where(PlatformAdmin.user_id == uuid.UUID(a["user"]["id"])))
    db_session.flush()
    assert client.get("/api/v1/auth/me", headers=h).json()["is_platform_admin"] is False
    assert client.get(f"{A}/overview", headers=h).status_code == 403   # the same token, revoked in the database


def test_tenant_routes_stay_isolated_for_a_platform_admin(client, db_session, register_org):
    a, b = register_org(), register_org()
    other = _member(client, b["headers"], "viewer", "Other")
    _grant(db_session, a)
    h = a["headers"]
    mine = client.get("/api/v1/users", headers=h).json()
    assert [u["id"] for u in mine["items"]] == [a["user"]["id"]]
    assert client.get(f"/api/v1/users/{other['id']}", headers=h).status_code == 404
    assert client.get("/api/v1/organizations/me", headers=h).json()["id"] == a["organization"]["id"]


def test_grant_and_revoke_platform_admin(client, db_session, register_org):
    a, b = register_org(), register_org()
    member = _member(client, b["headers"], "editor", "Grant Me")
    _grant(db_session, a)
    h = a["headers"]
    assert client.post(f"{A}/grant", headers=b["headers"], json={"email": member["email"]}).status_code == 403
    r = client.post(f"{A}/grant", headers=h, json={"email": member["email"].upper()})
    assert r.status_code == 200 and r.json()["is_platform_admin"] is True and r.json()["organization_name"]
    assert client.post(f"{A}/grant", headers=h, json={"user_id": member["id"]}).status_code == 200   # idempotent
    mh = _login(client, member["email"])
    assert client.get(f"{A}/overview", headers=mh).status_code == 200
    listed = client.get(f"{A}/users", headers=h, params={"q": member["email"]}).json()["items"][0]
    assert listed["is_platform_admin"] is True
    assert client.post(f"{A}/grant", headers=h, json={"email": "nobody@example.com"}).status_code == 404
    assert client.post(f"{A}/grant", headers=h, json={}).status_code == 422
    assert client.post(f"{A}/grant", headers=h, json={"email": member["email"], "user_id": member["id"]}).status_code == 422
    assert client.delete(f"{A}/grant/{a['user']['id']}", headers=h).status_code == 409          # not your own
    assert client.delete(f"{A}/grant/{member['id']}", headers=h).status_code == 204
    assert client.get(f"{A}/overview", headers=mh).status_code == 403
    assert client.delete(f"{A}/grant/{member['id']}", headers=h).status_code == 404
