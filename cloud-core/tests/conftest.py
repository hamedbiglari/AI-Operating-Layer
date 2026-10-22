"""
Shared pytest fixtures.

Two client fixtures exist, deliberately:

- `raw_client`: a plain TestClient with NO dependency overrides. Used for
  endpoints that don't require a live database (e.g. /health/live) so
  those tests run identically with or without Postgres available.

- `client`: a TestClient whose `get_db` dependency is overridden to use
  a per-test SQLAlchemy session that is wrapped in an outer transaction
  and rolled back after the test (the standard "join a transaction"
  pattern), so every DB-backed test is fully isolated and leaves no
  residue — even though the service layer under test calls
  `session.commit()` internally.

Per the Phase 0 review finding on testing: DB-backed tests here skip
gracefully when PostgreSQL is unreachable (for local iteration without
Docker), but CI (`.github/workflows/ci.yml`) always runs them against a
real Postgres service container, so a green CI run is never a false
positive.

Phase 5 adds `_celery_eager_mode`, session-scoped and autouse: Celery's
own documented `task_always_eager` setting makes `.delay()` execute the
real task function synchronously, in-process, with no broker or worker
process required. This is Celery's standard, first-party technique for
testing task code — not a mock or stub of
`app/workers/tasks.py::execute_research_task_job`'s body, which is the
same function a real worker process would run.
"""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

import app.models  # noqa: F401 - registers all models on Base.metadata
from app.core.config import settings
from app.db.base import Base
from app.db.session import CONNECT_ARGS, get_db
from app.main import app
from app.security.tokens import create_access_token


@pytest.fixture(scope="session", autouse=True)
def _celery_eager_mode():
    """Session-scoped, autouse: every `.delay()` call anywhere in the
    test suite runs the real task body synchronously and raises any
    exception it hits immediately (`task_eager_propagates`), instead of
    silently queuing a message no worker process in this environment
    would ever consume."""
    from app.workers.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield


@pytest.fixture(scope="session")
def raw_client() -> TestClient:
    """Plain client, no DB dependency override. Safe with or without Postgres."""
    return TestClient(app)


@pytest.fixture(scope="session")
def db_engine():
    engine = create_engine(settings.DATABASE_URL, future=True, connect_args=CONNECT_ARGS)
    try:
        with engine.connect():
            pass
    except OperationalError:
        pytest.skip(
            "PostgreSQL is not reachable at DATABASE_URL — skipping DB-backed tests. "
            "This is expected for local iteration without Docker; CI always runs "
            "these against a real Postgres service container."
        )

    # checkfirst=True (the default) makes this safe to run repeatedly
    # against a database that already has these tables (e.g. one
    # provisioned by `alembic upgrade head`) — it only creates what's
    # missing. We deliberately do NOT drop_all() at teardown: DATABASE_URL
    # may point at a database a developer's own `docker compose up`
    # server is actively using, and destructively dropping its schema
    # after a local `pytest` run would be a nasty surprise. Per-test
    # isolation already comes from the transaction rollback in
    # `db_session` below, so nothing here needs a "reset the world" step.
    Base.metadata.create_all(bind=engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine):
    """A session bound to a connection with an outer transaction that is
    always rolled back, even if the code under test calls `commit()`."""
    connection = db_engine.connect()
    outer_transaction = connection.begin()

    session_factory = sessionmaker(bind=connection, future=True, expire_on_commit=False)
    session = session_factory()

    nested = connection.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess, trans):  # noqa: ANN001
        nonlocal nested
        if not nested.is_active:
            nested = connection.begin_nested()

    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture()
def client(db_session) -> TestClient:
    def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def register_org(client: TestClient):
    """Factory fixture: registers a fresh organization + owner user and
    returns the API response body plus ready-to-use auth headers."""

    counter = {"n": 0}

    def _register(name: str | None = None, email: str | None = None, password: str = "supersecret123"):
        counter["n"] += 1
        name = name or f"Test Org {counter['n']}"
        email = email or f"owner{counter['n']}@example.dev"

        response = client.post(
            "/api/v1/auth/register-organization",
            json={
                "organization_name": name,
                "owner_email": email,
                "owner_name": "Owner",
                "owner_password": password,
            },
        )
        assert response.status_code == 201, response.text
        body = response.json()
        body["password"] = password
        body["headers"] = {"Authorization": f"Bearer {body['token']['access_token']}"}
        return body

    return _register


def bearer_header(*, user_id: str, organization_id: str, role: str) -> dict:
    """Build an Authorization header directly from a hand-crafted JWT,
    bypassing HTTP login — useful for constructing edge-case tokens."""
    token = create_access_token(user_id=user_id, organization_id=organization_id, role=role)
    return {"Authorization": f"Bearer {token}"}


# ===========================================================================
# Phase 13 fixtures
#
# Kept here rather than in the Phase 13 test files so that both of them
# use ONE definition of "an adapter credential". Two copies would drift,
# and a drifted fixture is how a test starts asserting something the
# product does not do.
# ===========================================================================


def _make_installation(client: TestClient, org: dict, scopes: list[str]) -> dict:
    installation = client.post(
        "/api/v1/installations",
        json={"name": "Phase 13 test site", "adapter_type": "wordpress"},
        headers=org["headers"],
    )
    assert installation.status_code == 201, installation.text
    installation = installation.json()

    issued = client.post(
        f"/api/v1/installations/{installation['id']}/credentials",
        json={"scopes": scopes},
        headers=org["headers"],
    )
    assert issued.status_code == 201, issued.text
    token = issued.json()["token"]
    return {
        "org": org,
        "installation": installation,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.fixture()
def adapter_credential(client: TestClient, register_org):
    """An adapter credential holding both Phase 13 telemetry scopes."""
    return _make_installation(
        client, register_org(), ["telemetry:write", "telemetry:read"]
    )


@pytest.fixture()
def adapter_credential_no_telemetry(client: TestClient, register_org):
    """Deliberately scoped WITHOUT telemetry, so the authorization test is
    testing the scope check rather than the absence of a credential."""
    return _make_installation(client, register_org(), ["mappings:read"])


@pytest.fixture()
def viewer_headers(client: TestClient, register_org):
    """A VIEWER-role user in a fresh organization. Used to prove that the
    full-IP route is not merely undocumented for low-privilege roles but
    actually refused."""
    org = register_org()
    created = client.post(
        "/api/v1/users",
        json={
            "email": f"viewer-{uuid.uuid4().hex[:8]}@example.dev",
            "name": "Viewer",
            "password": "supersecret123",
            "role": "viewer",
        },
        headers=org["headers"],
    )
    assert created.status_code == 201, created.text
    user = created.json()
    return bearer_header(
        user_id=user["id"],
        organization_id=user["organization_id"],
        role="viewer",
    )


_redis_unreachable = False


@pytest.fixture(autouse=True)
def _reset_signin_throttles():
    """Each test starts with empty password-login and registration counters (security audit SEC-02/SEC-03).
    Without this, the per-address limits — correct in production — would count every test in the run as one
    client. The limits themselves are asserted in test_security_audit_2026_10.py."""
    global _redis_unreachable
    from app.security.rate_limit import _redis_client
    from redis.exceptions import ConnectionError as RedisConnectionError

    client = None if _redis_unreachable else _redis_client()
    if client is not None:
        try:
            for pattern in ("ratelimit:installation:login-pw-*", "ratelimit:installation:register-ip:*"):
                for key in client.scan_iter(pattern):
                    client.delete(key)
        except RedisConnectionError:
            _redis_unreachable = True
        except Exception:  # noqa: BLE001 - no Redis: the limiter fails open and there is nothing to reset
            pass
    yield
