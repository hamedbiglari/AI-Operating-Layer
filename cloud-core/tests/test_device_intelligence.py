"""Device Intelligence (ADR-138): protocol, red-team cases, privacy, tenant isolation, assessment.

Every key here is generated in the test, exactly as a client would: ES256, private key never sent.
Results are SYNTHETIC: they prove the protocol and the evidence rules, not real-world detection accuracy.
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from sqlalchemy import select

from app.core.config import settings
from app.models.audit_log import AuditLog
from app.models.device_intelligence import DeviceChallenge, DeviceCredential, DeviceObservation
from app.services import device_intelligence_service as svc

D = "/api/v1/devices"


class Installation:
    """What a client does: generate a key, sign challenges. `raw=True` signs in P1363 like WebCrypto."""

    def __init__(self, raw: bool = False):
        self.key = ec.generate_private_key(ec.SECP256R1())
        self.raw = raw
        self.credential_id: str | None = None

    @property
    def public_b64(self) -> str:
        der = self.key.public_key().public_bytes(serialization.Encoding.DER,
                                                 serialization.PublicFormat.SubjectPublicKeyInfo)
        return base64.b64encode(der).decode()

    def sign(self, text: str) -> str:
        der = self.key.sign(text.encode("ascii"), ec.ECDSA(hashes.SHA256()))
        if self.raw:
            r, s = decode_dss_signature(der)
            der = r.to_bytes(32, "big") + s.to_bytes(32, "big")
        return base64.b64encode(der).decode()

    def register(self, client, h, platform="windows", expect=(200, 201), **extra):
        ch = client.post(f"{D}/challenges", headers=h, json={"purpose": "register"})
        assert ch.status_code == 201, ch.text
        c = ch.json()
        r = client.post(f"{D}/credentials", headers=h, json={
            "challenge_id": c["challenge_id"], "nonce": c["nonce"], "public_key": self.public_b64,
            "signature": self.sign(c["signing_input"]), "platform": platform, "key_storage": "os_keystore",
            "app_version": "0.1.0", "os_family": platform, **extra})
        assert r.status_code in expect, r.text
        if r.status_code in (200, 201):
            self.credential_id = r.json()["id"]
        return r

    def verify(self, client, h, credential_id=None):
        cid = credential_id or self.credential_id
        ch = client.post(f"{D}/challenges", headers=h, json={"purpose": "verify", "credential_id": cid})
        if ch.status_code != 201:
            return ch
        c = ch.json()
        return client.post(f"{D}/credentials/{cid}/verify", headers=h, json={
            "challenge_id": c["challenge_id"], "nonce": c["nonce"], "signature": self.sign(c["signing_input"])})


def _second_user(client, org, role="viewer"):
    email = f"member-{uuid.uuid4().hex[:8]}@example.dev"
    r = client.post("/api/v1/users", headers=org["headers"],
                    json={"email": email, "name": "Member", "password": "supersecret123", "role": role})
    assert r.status_code == 201, r.text
    tok = client.post("/api/v1/auth/login", data={"username": email, "password": "supersecret123"}).json()
    return {"Authorization": f"Bearer {tok['access_token']}"}, r.json()["id"]


# ------------------------------------------------------------------ protocol
def test_every_device_route_requires_a_session(client):
    cid = uuid.uuid4()
    for method, path in [("post", "/challenges"), ("post", "/credentials"), ("get", "/credentials"),
                         ("post", f"/credentials/{cid}/verify"), ("delete", f"/credentials/{cid}"),
                         ("get", "/admin/credentials"), ("get", f"/admin/credentials/{cid}"),
                         ("post", f"/admin/credentials/{cid}/revoke")]:
        assert getattr(client, method)(f"{D}{path}").status_code == 401, path


def test_register_then_verify_continuity(client, register_org):
    org = register_org()
    inst = Installation()
    r = inst.register(client, org["headers"])
    assert r.status_code == 201 and r.json()["created"] is True
    body = r.json()
    assert body["provenance"] == "WINDOWS_CLIENT" and body["status"] == "active"
    assert "public_key" not in body and len(body["reference"]) == 12
    v = inst.verify(client, org["headers"])
    assert v.status_code == 200, v.text
    mine = client.get(f"{D}/credentials", headers=org["headers"]).json()["items"]
    assert [m["id"] for m in mine] == [inst.credential_id]


def test_webcrypto_style_p1363_signatures_are_accepted(client, register_org):
    org = register_org()
    inst = Installation(raw=True)
    assert inst.register(client, org["headers"], platform="web").status_code == 201
    assert inst.verify(client, org["headers"]).status_code == 200


def test_registering_the_same_key_twice_is_idempotent(client, register_org, db_session):
    org = register_org()
    inst = Installation()
    first = inst.register(client, org["headers"])
    again = inst.register(client, org["headers"])
    assert again.status_code == 200 and again.json()["created"] is False
    assert again.json()["id"] == first.json()["id"]
    assert len(db_session.execute(select(DeviceCredential)).scalars().all()) >= 1


# ------------------------------------------------------------------ red team: spoofing and replay
def test_a_public_key_without_the_private_key_cannot_register(client, register_org):
    """Spoofed payload: the attacker knows a victim's public key but signs with their own key."""
    org = register_org()
    victim, attacker = Installation(), Installation()
    ch = client.post(f"{D}/challenges", headers=org["headers"], json={"purpose": "register"}).json()
    r = client.post(f"{D}/credentials", headers=org["headers"], json={
        "challenge_id": ch["challenge_id"], "nonce": ch["nonce"], "public_key": victim.public_b64,
        "signature": attacker.sign(ch["signing_input"]), "platform": "windows"})
    assert r.status_code == 401 and r.json()["error"]["reason"] == "bad_signature"


def test_a_challenge_cannot_be_replayed(client, register_org):
    org = register_org()
    inst = Installation()
    ch = client.post(f"{D}/challenges", headers=org["headers"], json={"purpose": "register"}).json()
    payload = {"challenge_id": ch["challenge_id"], "nonce": ch["nonce"], "public_key": inst.public_b64,
               "signature": inst.sign(ch["signing_input"]), "platform": "windows"}
    assert client.post(f"{D}/credentials", headers=org["headers"], json=payload).status_code == 201
    replay = client.post(f"{D}/credentials", headers=org["headers"], json=payload)
    assert replay.status_code == 409 and replay.json()["error"]["reason"] == "challenge_replayed"


def test_a_failed_signature_burns_the_challenge(client, register_org):
    org = register_org()
    inst, other = Installation(), Installation()
    ch = client.post(f"{D}/challenges", headers=org["headers"], json={"purpose": "register"}).json()
    base = {"challenge_id": ch["challenge_id"], "nonce": ch["nonce"], "public_key": inst.public_b64,
            "platform": "windows"}
    assert client.post(f"{D}/credentials", headers=org["headers"],
                       json={**base, "signature": other.sign(ch["signing_input"])}).status_code == 401
    retry = client.post(f"{D}/credentials", headers=org["headers"],
                        json={**base, "signature": inst.sign(ch["signing_input"])})
    assert retry.status_code == 409, "a wrong signature must not be a free retry on the same nonce"


def test_an_expired_challenge_is_refused(client, register_org, db_session):
    org = register_org()
    inst = Installation()
    ch = client.post(f"{D}/challenges", headers=org["headers"], json={"purpose": "register"}).json()
    row = db_session.get(DeviceChallenge, uuid.UUID(ch["challenge_id"]))
    row.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.flush()
    r = client.post(f"{D}/credentials", headers=org["headers"], json={
        "challenge_id": ch["challenge_id"], "nonce": ch["nonce"], "public_key": inst.public_b64,
        "signature": inst.sign(ch["signing_input"]), "platform": "windows"})
    assert r.status_code == 409 and r.json()["error"]["reason"] == "challenge_expired"


def test_a_wrong_nonce_is_refused(client, register_org):
    org = register_org()
    inst = Installation()
    ch = client.post(f"{D}/challenges", headers=org["headers"], json={"purpose": "register"}).json()
    forged_nonce = base64.urlsafe_b64encode(b"x" * 32).decode().rstrip("=")
    text = ch["signing_input"].replace(ch["nonce"], forged_nonce)
    r = client.post(f"{D}/credentials", headers=org["headers"], json={
        "challenge_id": ch["challenge_id"], "nonce": forged_nonce, "public_key": inst.public_b64,
        "signature": inst.sign(text), "platform": "windows"})
    assert r.status_code == 409 and r.json()["error"]["reason"] == "challenge_invalid"


def test_another_users_challenge_cannot_be_used(client, register_org):
    org = register_org()
    h2, _ = _second_user(client, org)
    inst = Installation()
    ch = client.post(f"{D}/challenges", headers=org["headers"], json={"purpose": "register"}).json()
    r = client.post(f"{D}/credentials", headers=h2, json={
        "challenge_id": ch["challenge_id"], "nonce": ch["nonce"], "public_key": inst.public_b64,
        "signature": inst.sign(ch["signing_input"]), "platform": "windows"})
    assert r.status_code == 409 and r.json()["error"]["reason"] == "challenge_invalid"


def test_a_signature_is_bound_to_its_user_and_cannot_be_moved(client, register_org):
    """A signature over user A's challenge is useless to user B even with B's own challenge id."""
    org = register_org()
    h2, _ = _second_user(client, org)
    inst = Installation()
    a = client.post(f"{D}/challenges", headers=org["headers"], json={"purpose": "register"}).json()
    b = client.post(f"{D}/challenges", headers=h2, json={"purpose": "register"}).json()
    r = client.post(f"{D}/credentials", headers=h2, json={
        "challenge_id": b["challenge_id"], "nonce": b["nonce"], "public_key": inst.public_b64,
        "signature": inst.sign(a["signing_input"]), "platform": "windows"})
    assert r.status_code == 401


def test_a_verify_challenge_is_bound_to_one_credential(client, register_org):
    org = register_org()
    one, two = Installation(), Installation()
    one.register(client, org["headers"])
    two.register(client, org["headers"])
    ch = client.post(f"{D}/challenges", headers=org["headers"],
                     json={"purpose": "verify", "credential_id": one.credential_id}).json()
    r = client.post(f"{D}/credentials/{two.credential_id}/verify", headers=org["headers"], json={
        "challenge_id": ch["challenge_id"], "nonce": ch["nonce"], "signature": two.sign(ch["signing_input"])})
    assert r.status_code == 409


def test_non_p256_and_garbage_keys_are_refused(client, register_org):
    org = register_org()
    ch = client.post(f"{D}/challenges", headers=org["headers"], json={"purpose": "register"}).json()
    p384 = ec.generate_private_key(ec.SECP384R1()).public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    for key in (base64.b64encode(p384).decode(), base64.b64encode(b"\x00" * 91).decode(), "!!!" * 20):
        r = client.post(f"{D}/credentials", headers=org["headers"], json={
            "challenge_id": ch["challenge_id"], "nonce": ch["nonce"], "public_key": key,
            "signature": "A" * 88, "platform": "windows"})
        assert r.status_code == 422, r.text


def test_a_key_cannot_switch_platform(client, register_org):
    org = register_org()
    inst = Installation()
    inst.register(client, org["headers"], platform="windows")
    r = inst.register(client, org["headers"], platform="ios", expect=(409,))
    assert r.json()["error"]["reason"] == "provenance_mismatch"


# ------------------------------------------------------------------ tenant isolation
def test_another_tenant_cannot_see_verify_or_revoke_a_credential(client, register_org):
    a, b = register_org(), register_org()
    inst = Installation()
    inst.register(client, a["headers"])
    assert client.get(f"{D}/admin/credentials/{inst.credential_id}", headers=b["headers"]).status_code == 404
    assert client.post(f"{D}/admin/credentials/{inst.credential_id}/revoke", headers=b["headers"]).status_code == 404
    assert client.post(f"{D}/challenges", headers=b["headers"],
                       json={"purpose": "verify", "credential_id": inst.credential_id}).status_code == 404
    assert client.delete(f"{D}/credentials/{inst.credential_id}", headers=b["headers"]).status_code == 404
    assert client.get(f"{D}/admin/credentials", headers=b["headers"]).json()["total"] == 0


def test_the_same_key_in_two_tenants_is_two_unconnected_rows(client, register_org):
    a, b = register_org(), register_org()
    inst = Installation()
    ra = inst.register(client, a["headers"]).json()
    rb = inst.register(client, b["headers"]).json()
    assert ra["id"] != rb["id"] and ra["created"] and rb["created"]
    detail = client.get(f"{D}/admin/credentials/{rb['id']}", headers=b["headers"]).json()
    assert [x["email"] for x in detail["linked_accounts"]] == [b["user"]["email"]]


def test_a_non_admin_cannot_read_device_evidence(client, register_org):
    org = register_org()
    viewer, _ = _second_user(client, org, role="viewer")
    assert client.get(f"{D}/admin/credentials", headers=viewer).status_code == 403


def test_a_user_who_never_proved_possession_cannot_verify_or_unlink(client, register_org):
    org = register_org()
    h2, _ = _second_user(client, org)
    inst = Installation()
    inst.register(client, org["headers"])
    assert inst.verify(client, h2).status_code == 404
    assert client.delete(f"{D}/credentials/{inst.credential_id}", headers=h2).status_code == 404


# ------------------------------------------------------------------ shared devices and lifecycle
def test_account_switching_on_one_installation_links_both_accounts(client, register_org):
    org = register_org()
    h2, _ = _second_user(client, org)
    inst = Installation()
    first = inst.register(client, org["headers"]).json()
    second = inst.register(client, h2).json()
    assert second["id"] == first["id"] and second["created"] is False
    a = client.get(f"{D}/admin/credentials/{first['id']}", headers=org["headers"]).json()
    assert "SAME_REGISTERED_INSTALLATION" in a["assessment"]["categories"]
    assert len(a["linked_accounts"]) == 2
    # Never a person-level conclusion.
    assert "person" not in str(a["assessment"]["categories"]).lower()


def test_unlinking_the_last_account_revokes_and_a_revoked_key_cannot_return(client, register_org):
    org = register_org()
    inst = Installation()
    inst.register(client, org["headers"])
    assert client.delete(f"{D}/credentials/{inst.credential_id}", headers=org["headers"]).status_code == 204
    assert client.get(f"{D}/credentials", headers=org["headers"]).json()["items"] == []
    r = inst.register(client, org["headers"], expect=(409,))
    assert r.json()["error"]["reason"] == "credential_revoked"
    # Reinstall: a new key is a new installation, and registers normally.
    assert Installation().register(client, org["headers"]).status_code == 201


def test_unlinking_one_of_two_accounts_keeps_the_credential_for_the_other(client, register_org):
    org = register_org()
    h2, _ = _second_user(client, org)
    inst = Installation()
    inst.register(client, org["headers"])
    inst.register(client, h2)
    assert client.delete(f"{D}/credentials/{inst.credential_id}", headers=h2).status_code == 204
    assert inst.verify(client, org["headers"]).status_code == 200
    assert inst.verify(client, h2).status_code == 404


def test_admin_revocation_is_audited_and_stops_verification(client, register_org, db_session):
    org = register_org()
    inst = Installation()
    inst.register(client, org["headers"])
    r = client.post(f"{D}/admin/credentials/{inst.credential_id}/revoke", headers=org["headers"])
    assert r.status_code == 200 and r.json()["revoked_reason"] == "admin_revoked"
    assert inst.verify(client, org["headers"]).json()["error"]["reason"] == "credential_revoked"
    actions = {a.action for a in db_session.execute(select(AuditLog)).scalars()}
    assert {"device.credential_registered", "device.credential_revoked"} <= actions
    again = client.post(f"{D}/admin/credentials/{inst.credential_id}/revoke", headers=org["headers"])
    assert again.status_code == 409


def test_reading_device_evidence_is_audited(client, register_org, db_session):
    org = register_org()
    inst = Installation()
    inst.register(client, org["headers"])
    client.get(f"{D}/admin/credentials/{inst.credential_id}", headers=org["headers"])
    assert db_session.execute(select(AuditLog).where(
        AuditLog.action == "device_intelligence.viewed")).scalars().first() is not None


# ------------------------------------------------------------------ assessment and false positives
def test_a_single_installation_is_insufficient_evidence_not_an_accusation(client, register_org):
    org = register_org()
    inst = Installation()
    inst.register(client, org["headers"])
    items = client.get(f"{D}/admin/credentials", headers=org["headers"]).json()["items"]
    assert items[0]["assessment"]["categories"] == ["INSUFFICIENT_EVIDENCE"]
    assert items[0]["assessment"]["algorithm_version"] == svc.ALGORITHM_VERSION


def test_failed_checks_against_a_verified_key_are_conflicting_evidence(client, register_org):
    org = register_org()
    inst, thief = Installation(), Installation()
    inst.register(client, org["headers"])
    assert thief.verify(client, org["headers"], credential_id=inst.credential_id).status_code == 401
    a = client.get(f"{D}/admin/credentials/{inst.credential_id}", headers=org["headers"]).json()["assessment"]
    assert "CONFLICTING_EVIDENCE" in a["categories"] and a["evidence"]["failed_checks"] == 1


def test_a_shared_network_alone_is_only_shared_network(db_session, register_org, client):
    """Office NAT / family Wi-Fi / VPN exit: two accounts, two installations, one network prefix."""
    from app.models.user import User

    org = register_org()
    h2, uid2 = _second_user(client, org)
    one, two = Installation(), Installation()
    one.register(client, org["headers"])
    two.register(client, h2)
    owner = db_session.get(User, uuid.UUID(org["user"]["id"]))
    for cred_id, uid in ((one.credential_id, owner.id), (two.credential_id, uuid.UUID(uid2))):
        db_session.add(DeviceObservation(organization_id=owner.organization_id, credential_id=uuid.UUID(cred_id),
                                         user_id=uid, provenance="WINDOWS_CLIENT", kind="verified",
                                         **svc.network_fields("203.0.113.7")))
    db_session.flush()
    a = client.get(f"{D}/admin/credentials/{one.credential_id}", headers=org["headers"]).json()["assessment"]
    assert a["categories"] == ["SHARED_NETWORK_ONLY"]
    assert "SAME_REGISTERED_INSTALLATION" not in a["categories"]


def test_vpn_exit_changes_do_not_break_continuity(client, register_org, db_session):
    """An IP change is not a new device: the key is what carries continuity."""
    org = register_org()
    inst = Installation()
    inst.register(client, org["headers"])
    for _ in range(3):
        assert inst.verify(client, org["headers"]).status_code == 200
    a = client.get(f"{D}/admin/credentials/{inst.credential_id}", headers=org["headers"]).json()["assessment"]
    assert a["categories"] == ["INSUFFICIENT_EVIDENCE"]


# ------------------------------------------------------------------ privacy
def test_network_observations_are_keyed_pseudonyms_never_addresses(db_session):
    fields = svc.network_fields("198.51.100.23")
    assert "198.51.100" not in str(fields) and len(fields["network_pseudonym"]) == 64
    assert fields["pseudonym_key_version"] == settings.DEVICE_PSEUDONYM_KEY_VERSION
    same_net = svc.network_fields("198.51.100.200")
    assert same_net["network_prefix_pseudonym"] == fields["network_prefix_pseudonym"]
    assert same_net["network_pseudonym"] != fields["network_pseudonym"]
    assert svc.network_fields("unknown")["network_pseudonym"] is None, "no address is NULL, not a value"
    assert svc.network_prefix("2001:db8:1:2::5") == "2001:db8:1::/48"


def test_admin_detail_exposes_no_key_material_or_raw_network(client, register_org):
    org = register_org()
    inst = Installation()
    inst.register(client, org["headers"])
    raw = client.get(f"{D}/admin/credentials/{inst.credential_id}", headers=org["headers"]).text
    assert inst.public_b64 not in raw and "testclient" not in raw
    assert "public_key_spki" not in raw and "nonce" not in raw


def test_retention_purges_old_observations_and_dead_challenges(db_session, client, register_org):
    org = register_org()
    inst = Installation()
    inst.register(client, org["headers"])
    old = datetime.now(timezone.utc) - timedelta(days=settings.DEVICE_OBSERVATION_RETENTION_DAYS + 1)
    for o in db_session.execute(select(DeviceObservation)).scalars():
        o.created_at = old
    db_session.flush()
    out = svc.purge_expired(db_session, now=datetime.now(timezone.utc) + timedelta(hours=2))
    assert out["observations_deleted"] >= 1 and out["challenges_deleted"] >= 1
    assert db_session.execute(select(DeviceObservation).where(
        DeviceObservation.created_at < datetime.now(timezone.utc) - timedelta(days=1))).first() is None


def test_turning_device_intelligence_off_disables_it_without_touching_sign_in(client, register_org, monkeypatch):
    monkeypatch.setattr(settings, "DEVICE_INTELLIGENCE_ENABLED", False)
    org = register_org()
    assert client.post(f"{D}/challenges", headers=org["headers"], json={"purpose": "register"}).status_code == 404
    assert client.get("/api/v1/auth/me", headers=org["headers"]).status_code == 200
