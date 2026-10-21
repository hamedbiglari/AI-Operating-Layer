"""Regression tests for the security audit of 2026-10-14 (docs/project-closure/FINAL_SECURITY_AUDIT.md).

Each test names the finding it pins. They run against the real app and the real database, like the rest of the
suite; nothing here is a fixture standing in for behaviour.
"""
from __future__ import annotations

import datetime as dt
import http.server
import ssl
import threading
import uuid

import pytest
from starlette.requests import Request  # module level: FastAPI resolves string annotations here


# ---------------------------------------------------------------- SEC-01: HTTPS through the SSRF guard
def _make_tls_material(tmp_path):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

    now = dt.datetime.now(dt.timezone.utc)
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "AIOL test CA")])
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name).public_key(ca_key.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now - dt.timedelta(minutes=5))
          .not_valid_after(now + dt.timedelta(hours=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
          .add_extension(x509.KeyUsage(digital_signature=False, content_commitment=False, key_encipherment=False,
                                       data_encipherment=False, key_agreement=False, key_cert_sign=True, crl_sign=True,
                                       encipher_only=False, decipher_only=False), critical=True)
          .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
          .sign(ca_key, hashes.SHA256()))
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf = (x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "docs.example")]))
            .issuer_name(ca_name).public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(now + dt.timedelta(hours=1))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("docs.example")]), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    pem = serialization.Encoding.PEM
    (tmp_path / "ca.pem").write_bytes(ca.public_bytes(pem))
    (tmp_path / "leaf.pem").write_bytes(leaf.public_bytes(pem))
    (tmp_path / "leaf.key").write_bytes(key.private_bytes(pem, serialization.PrivateFormat.TraditionalOpenSSL,
                                                          serialization.NoEncryption()))
    return tmp_path / "ca.pem", tmp_path / "leaf.pem", tmp_path / "leaf.key"


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        body = f"<html><body><p>served for {self.headers.get('Host')}</p></body></html>".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # silence
        pass


def test_sec01_https_fetch_verifies_the_certificate_against_the_hostname_not_the_pinned_ip(tmp_path, monkeypatch):
    from app.ingestion import url_source

    ca, leaf, key = _make_tls_material(tmp_path)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(str(leaf), str(key))
    srv = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    srv.socket = ctx.wrap_socket(srv.socket, server_side=True)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        monkeypatch.setattr(url_source, "ALLOWED_PORTS", {port})
        # DNS answer for the test name: the loopback server. Every other guard still runs.
        monkeypatch.setattr(url_source, "resolve_and_validate", lambda host, p: "127.0.0.1")
        monkeypatch.setenv("SSL_CERT_FILE", str(ca))
        res = url_source.fetch_url(f"https://docs.example:{port}/paper")
        assert b"served for docs.example" in res.content
        # And a certificate that does NOT match the requested name is still refused.
        with pytest.raises(url_source.UrlRejected):
            url_source.fetch_url(f"https://other.example:{port}/paper")
    finally:
        srv.shutdown()


# ---------------------------------------------------------------- SEC-05: HTML rendering of document content
def test_sec05_html_rendering_escapes_provider_supplied_attributes():
    from app.ingestion import render as renderer
    from app.ingestion.cdr import CanonicalDocument, Element

    evil = '"><script>alert(1)</script>'
    el = Element(element_type="paragraph", page=1, reading_order=0, text="hello <b>x</b>",
                 block_id='p1-b1" onmouseover="x', language=evil, direction=evil, bbox=[1.0, 2.0, 3.0, 4.0])
    out = renderer.render(CanonicalDocument(provider="t", provider_version="1", elements=[el]), "html")
    assert "<script>" not in out and 'onmouseover="x' not in out
    assert "&lt;b&gt;x&lt;/b&gt;" in out


# ---------------------------------------------------------------- SEC-02: password brute force
def _redis_or_skip():
    from app.security.rate_limit import redis_available

    if not redis_available():
        pytest.skip("Redis not reachable: the limiter fails open by design (see test_redis_down_failopen)")


def test_sec02_password_login_is_throttled_per_account(client, register_org, monkeypatch):
    _redis_or_skip()
    from app.core.config import settings

    org = register_org()
    email = org["user"]["email"]
    monkeypatch.setattr(settings, "LOGIN_PASSWORD_ACCOUNT_LIMIT_PER_15_MIN", 3)
    codes = [client.post("/api/v1/auth/login", data={"username": email, "password": f"wrong-{i}"}).status_code
             for i in range(4)]
    assert codes == [401, 401, 401, 429]
    # The right password is also refused while the account is throttled: the limiter is not an oracle.
    r = client.post("/api/v1/auth/login", data={"username": email, "password": org["password"]})
    assert r.status_code == 429 and "Retry-After" in r.headers


def test_sec02_password_login_is_throttled_per_address(client, register_org, monkeypatch):
    _redis_or_skip()
    from app.core.config import settings

    monkeypatch.setattr(settings, "LOGIN_PASSWORD_IP_LIMIT_PER_MINUTE", 2)
    codes = [client.post("/api/v1/auth/login", data={"username": f"nobody{i}@example.dev", "password": "x"}).status_code
             for i in range(3)]
    assert codes == [401, 401, 429]


def test_sec02_unknown_account_costs_a_password_check(monkeypatch, db_session):
    from app.services import auth_service

    calls = []
    real = auth_service.verify_password
    monkeypatch.setattr(auth_service, "verify_password", lambda p, h: calls.append(h) or real(p, h))
    assert auth_service.authenticate(db_session, email=f"ghost-{uuid.uuid4().hex}@example.dev", password="x") is None
    assert len(calls) == 1, "an unknown address must spend the same bcrypt work as a known one"


# ---------------------------------------------------------------- SEC-03: unverified registration
def test_sec03_password_registration_is_off_in_production_unless_enabled(client, monkeypatch):
    from app.core.config import settings

    body = {"organization_name": "Prod Org", "owner_email": f"p-{uuid.uuid4().hex[:8]}@example.dev",
            "owner_name": "O", "owner_password": "supersecret123"}
    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "PASSWORD_REGISTRATION_ENABLED", None)
    assert client.post("/api/v1/auth/register-organization", json=body).status_code == 404
    monkeypatch.setattr(settings, "PASSWORD_REGISTRATION_ENABLED", True)
    assert client.post("/api/v1/auth/register-organization", json=body).status_code == 201


def test_sec03_registration_is_throttled_per_address(client, monkeypatch):
    _redis_or_skip()
    from app.core.config import settings

    monkeypatch.setattr(settings, "REGISTRATION_IP_LIMIT_PER_HOUR", 1)
    mk = lambda: {"organization_name": "Org", "owner_email": f"r-{uuid.uuid4().hex[:8]}@example.dev",  # noqa: E731
                  "owner_name": "O", "owner_password": "supersecret123"}
    assert client.post("/api/v1/auth/register-organization", json=mk()).status_code == 201
    assert client.post("/api/v1/auth/register-organization", json=mk()).status_code == 429


# ---------------------------------------------------------------- SEC-04: client address behind our proxy
class _Req:
    def __init__(self, peer, xff=None):
        self.client = type("C", (), {"host": peer})()
        self.headers = {"x-forwarded-for": xff} if xff is not None else {}


def test_sec04_client_ip_honours_only_our_own_proxy_hops(monkeypatch):
    from app.core.config import settings
    from app.security.client_ip import client_ip

    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 0)
    assert client_ip(_Req("10.0.0.5", "1.2.3.4")) == "10.0.0.5"            # header ignored without trusted hops
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 1)
    assert client_ip(_Req("10.0.0.5", "6.6.6.6, 1.2.3.4")) == "1.2.3.4"    # spoofed left entry not trusted
    assert client_ip(_Req("10.0.0.5", "garbage")) == "10.0.0.5"            # unparseable -> the peer
    monkeypatch.setattr(settings, "TRUSTED_PROXY_HOPS", 2)
    assert client_ip(_Req("10.0.0.5", "1.2.3.4")) == "10.0.0.5"            # shorter than our chain -> the peer
    assert client_ip(_Req("10.0.0.5", "6.6.6.6, 1.2.3.4, 10.0.0.9")) == "1.2.3.4"


# ---------------------------------------------------------------- SEC-06: sandbox payments
def test_sec06_production_refuses_to_start_with_the_sandbox_payment_provider():
    from app.core.config import InsecureProductionConfigError, Settings

    with pytest.raises(InsecureProductionConfigError, match="sandbox"):
        Settings(APP_ENV="production", APP_DEBUG=False, SECRET_KEY="x" * 64,
                 DATABASE_URL="postgresql+psycopg://u:strong@db:5432/aiol", PAYMENT_PROVIDER="sandbox")


def test_sec06_sandbox_completion_is_unavailable_in_production(monkeypatch, db_session):
    from fastapi import HTTPException

    from app.core.config import settings
    from app.services import billing_service

    monkeypatch.setattr(settings, "APP_ENV", "production")
    monkeypatch.setattr(settings, "PAYMENT_PROVIDER", "sandbox")
    from pydantic import SecretStr

    monkeypatch.setattr(settings, "PAYMENT_WEBHOOK_SECRET", SecretStr("whsec-test"))
    with pytest.raises(HTTPException) as e:
        billing_service.sandbox_complete(db_session, organization_id=uuid.uuid4(), payment_id=uuid.uuid4())
    # Refused before any payment lookup: the feature itself is unavailable in production.
    assert e.value.status_code == 404 and e.value.detail == "Not available."


# ---------------------------------------------------------------- SEC-07: response hardening
def test_sec07_api_responses_carry_hardening_headers(client):
    r = client.get("/api/v1/health/live")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "no-referrer"
    r = client.post("/api/v1/auth/login", data={"username": "nobody@example.dev", "password": "x"})
    assert r.headers["Cache-Control"] == "no-store"


def test_sec07_interactive_docs_are_not_published_in_production():
    import os
    import subprocess
    import sys

    env = dict(os.environ, APP_ENV="production", APP_DEBUG="false", SECRET_KEY="y" * 64,
               DATABASE_URL="postgresql+psycopg://u:strong@db:5432/aiol")
    code = ("from fastapi.testclient import TestClient; from app.main import app; c = TestClient(app); "
            "print('RESULT', c.get('/docs').status_code, c.get('/openapi.json').status_code)")
    out = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=120,
                         cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    result = [ln for ln in out.stdout.splitlines() if ln.startswith("RESULT ")]
    assert result == ["RESULT 404 404"], out.stderr[-2000:]


# ---------------------------------------------------------------- SEC-09: the published signing key
@pytest.mark.parametrize("env", ["staging", "production", "prod", "qa"])
def test_sec09_the_published_default_signing_key_is_refused_outside_development(env):
    from app.core.config import InsecureProductionConfigError, Settings

    with pytest.raises(InsecureProductionConfigError, match="SECRET_KEY"):
        Settings(APP_ENV=env, APP_DEBUG=False, DATABASE_URL="postgresql+psycopg://u:strong@db:5432/aiol")


def test_sec09_production_requires_a_long_signing_key():
    from app.core.config import InsecureProductionConfigError, Settings

    with pytest.raises(InsecureProductionConfigError, match="32"):
        Settings(APP_ENV="production", APP_DEBUG=False, SECRET_KEY="short",
                 DATABASE_URL="postgresql+psycopg://u:strong@db:5432/aiol")


# ---------------------------------------------------------------- SEC-13: parser CPU cost
@pytest.mark.parametrize("word", ["claim ", "section ", "continue ", "ادعا "])
def test_sec13_command_parser_is_linear_on_crafted_input(word):
    import time

    from app.services import workspace_service

    text = (word * 5000)[:20000]
    start = time.perf_counter()
    workspace_service.parse(text)
    assert time.perf_counter() - start < 0.5


def test_sec13_bounded_gaps_still_recognise_ordinary_commands():
    from app.services import workspace_service

    assert workspace_service.parse("Find the claims from page 12 of this paper")["intent"] == "claims_from_page"
    assert workspace_service.parse("continue the previous research")["intent"] == "continue_previous"


# ---------------------------------------------------------------- SEC-14: admin -> owner escalation
def _member(client, owner, role):
    email = f"{role}-{uuid.uuid4().hex[:8]}@example.dev"
    r = client.post("/api/v1/users", headers=owner["headers"],
                    json={"email": email, "name": role.title(), "password": "supersecret123", "role": role})
    assert r.status_code == 201, r.text
    tok = client.post("/api/v1/auth/login", data={"username": email, "password": "supersecret123"}).json()
    return r.json(), {"Authorization": f"Bearer {tok['access_token']}"}


def test_sec14_admin_cannot_promote_anyone_to_owner(client, register_org):
    owner = register_org()
    admin, admin_h = _member(client, owner, "admin")
    viewer, _ = _member(client, owner, "viewer")
    assert client.patch(f"/api/v1/users/{admin['id']}", headers=admin_h, json={"role": "owner"}).status_code == 403
    assert client.patch(f"/api/v1/users/{viewer['id']}", headers=admin_h, json={"role": "owner"}).status_code == 403
    r = client.post("/api/v1/users", headers=admin_h, json={"email": f"x-{uuid.uuid4().hex[:6]}@example.dev",
                                                            "name": "X", "password": "supersecret123", "role": "owner"})
    assert r.status_code == 403
    # Ordinary admin work still works.
    assert client.patch(f"/api/v1/users/{viewer['id']}", headers=admin_h, json={"role": "editor"}).status_code == 200


def test_sec14_admin_cannot_demote_or_block_the_owner(client, register_org):
    owner = register_org()
    _, admin_h = _member(client, owner, "admin")
    oid = owner["user"]["id"]
    assert client.patch(f"/api/v1/users/{oid}", headers=admin_h, json={"role": "viewer"}).status_code == 403
    assert client.patch(f"/api/v1/users/{oid}", headers=admin_h, json={"status": "suspended"}).status_code == 403
    assert client.get("/api/v1/auth/me", headers=owner["headers"]).status_code == 200


def test_sec14_the_last_active_owner_cannot_be_removed(client, register_org):
    owner = register_org()
    oid = owner["user"]["id"]
    r = client.patch(f"/api/v1/users/{oid}", headers=owner["headers"], json={"role": "admin"})
    assert r.status_code == 409
    second, _ = _member(client, owner, "owner")
    assert client.patch(f"/api/v1/users/{oid}", headers=owner["headers"], json={"role": "admin"}).status_code == 200


# ---------------------------------------------------------------- SEC-15: OCR language argument
@pytest.mark.parametrize("bad", ["../../tmp/x", "eng --psm 0", "/etc/passwd", "eng+../x"])
def test_sec15_ocr_languages_must_be_tesseract_codes(bad):
    from app.ingestion.providers.ocr import safe_languages

    with pytest.raises(ValueError):
        safe_languages(bad)
    assert safe_languages("eng+fas") == "eng+fas" and safe_languages("chi_sim") == "chi_sim"


def test_sec15_upload_refuses_a_path_as_ocr_language(client, register_org):
    org = register_org()
    src = client.post("/api/v1/sources", headers=org["headers"],
                      json={"title": "S", "source_type": "document"})
    assert src.status_code == 201, src.text
    r = client.post("/api/v1/documents/upload", headers=org["headers"],
                    files={"file": ("a.txt", b"hello world", "text/plain")},
                    data={"source_id": src.json()["id"], "ocr_languages": "../../tmp/x"})
    assert r.status_code == 422, r.text


# ---------------------------------------------------------------- SEC-16: request body size
def _tiny_app(limit):
    from fastapi import FastAPI

    from app.core.middleware import BodySizeLimitMiddleware

    a = FastAPI()

    @a.post("/echo")
    async def echo(request: Request):
        return {"n": len(await request.body())}

    a.add_middleware(BodySizeLimitMiddleware, max_bytes=limit)
    return a


def test_sec16_declared_oversized_body_is_refused_before_reading():
    from fastapi.testclient import TestClient

    c = TestClient(_tiny_app(1024))
    assert c.post("/echo", content=b"x" * 1000).json() == {"n": 1000}
    assert c.post("/echo", content=b"x" * 2000).status_code == 413


def test_sec16_chunked_oversized_body_is_cut_off():
    from fastapi.testclient import TestClient

    def chunks():
        for _ in range(10):
            yield b"x" * 512

    r = TestClient(_tiny_app(1024)).post("/echo", content=chunks())
    assert r.status_code == 413


def test_sec16_the_real_app_carries_the_limit():
    from app.core.middleware import BodySizeLimitMiddleware
    from app.main import app

    assert any(m.cls is BodySizeLimitMiddleware for m in app.user_middleware)


# ---------------------------------------------------------------- SEC-17: new modules keep tenants apart
def test_sec17_workspace_commands_are_private_to_their_author(client, register_org):
    a, b = register_org(), register_org()
    teammate, teammate_h = _member(client, a, "editor")
    cmd = client.post("/api/v1/workspace/commands", headers=a["headers"], json={"text": "summarise the evidence"})
    assert cmd.status_code == 201, cmd.text
    cid = cmd.json()["id"]
    for h in (b["headers"], teammate_h):        # another tenant, and another person in the same tenant
        assert client.get(f"/api/v1/workspace/commands/{cid}", headers=h).status_code == 404
        assert client.get(f"/api/v1/workspace/commands/{cid}/versions", headers=h).status_code == 404
        assert client.put(f"/api/v1/workspace/commands/{cid}/draft", headers=h, json={"text": "x"}).status_code in (404, 422)
        assert client.post(f"/api/v1/workspace/commands/{cid}/archive", headers=h).status_code == 404
        assert client.delete(f"/api/v1/workspace/commands/{cid}", headers=h).status_code == 404
        assert cid not in [c["id"] for c in client.get("/api/v1/workspace/commands", headers=h).json()["items"]]
    assert client.get(f"/api/v1/workspace/commands/{cid}", headers=a["headers"]).status_code == 200


def test_sec17_document_intelligence_routes_hide_other_tenants_documents(client, register_org):
    a, b = register_org(), register_org()
    src = client.post("/api/v1/sources", headers=a["headers"], json={"title": "S", "source_type": "document"})
    assert src.status_code == 201, src.text
    doc = client.post(f"/api/v1/documents?source_id={src.json()['id']}", headers=a["headers"],
                      json={"title": "Private", "content": "secret text"})
    assert doc.status_code == 201, doc.text
    did = doc.json()["id"]
    for path in (f"/api/v1/documents/{did}/elements", f"/api/v1/documents/{did}/conversions",
                 f"/api/v1/documents/{did}/render/html", f"/api/v1/documents/{did}/render/markdown"):
        r = client.get(path, headers=b["headers"])
        assert r.status_code == 404, (path, r.status_code)
        assert "secret text" not in r.text
    assert client.post(f"/api/v1/documents/{did}/reprocess", headers=b["headers"], json={}).status_code == 404


def test_sec17_synthesis_runs_hide_other_tenants_runs(client, register_org):
    a, b = register_org(), register_org()
    foreign = uuid.uuid4()
    for path in (f"/api/v1/synthesis/runs/{foreign}", f"/api/v1/synthesis/runs/{foreign}/units"):
        assert client.get(path, headers=b["headers"]).status_code == 404
    assert client.get("/api/v1/synthesis/runs", headers=b["headers"]).json()["total"] == 0
