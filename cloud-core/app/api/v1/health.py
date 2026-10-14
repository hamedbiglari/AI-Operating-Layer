"""
Health check endpoints.

Phase 0 review finding: liveness and readiness are different questions
and were conflated into a single /health endpoint. Phase 1 splits them:

- GET /health/live  — is the process itself alive? No dependencies checked.
                       Used by an orchestrator to decide whether to restart
                       the container.
- GET /health/ready — is the app ready to serve traffic? Checks the
                       database (and, as they're introduced, other hard
                       dependencies like Redis). Used by an orchestrator/
                       load balancer to decide whether to route traffic.

GET /health is kept as a backward-compatible alias for /health/ready,
since docker-compose healthchecks and existing tooling from Phase 0
already reference it.
"""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import get_db

router = APIRouter(prefix="/health", tags=["health"])


@router.get("/live")
def liveness() -> dict:
    """Process liveness only — never touches the database."""
    return {"status": "ok", "app": settings.APP_NAME, "env": settings.APP_ENV}


def _redis_status() -> str:
    """Phase 9 made Redis relevant to readiness: it backs adapter rate
    limiting. It is reported as DEGRADED rather than NOT READY, because
    the limiter fails open by design (ADR-039) - the app can still
    serve traffic correctly without it, just unmetered. Reporting it
    is what lets an operator notice; failing readiness would turn a
    cache outage into a total outage."""
    try:
        import redis  # noqa: PLC0415

        client = redis.Redis.from_url(
            settings.REDIS_URL, socket_connect_timeout=0.25, socket_timeout=0.25
        )
        client.ping()
        return "ok"
    except Exception as exc:  # noqa: BLE001 - broad by design for a probe
        return f"degraded: {exc.__class__.__name__}"


def _readiness_payload(db: Session) -> tuple[dict, bool]:
    db_status = "ok"
    is_ready = True
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001 - deliberately broad for a health probe
        db_status = f"error: {exc.__class__.__name__}"
        is_ready = False

    redis_status = _redis_status()

    payload = {
        # Only the database is a HARD dependency: without it nothing
        # works. Redis degradation is surfaced but does not fail
        # readiness - see _redis_status.
        "status": "ok" if is_ready else "degraded",
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "database": db_status,
        "redis": redis_status,
    }
    return payload, is_ready


@router.get("/ready")
def readiness(response: Response, db: Session = Depends(get_db)) -> dict:
    """Readiness: checks hard dependencies (currently: database)."""
    payload, is_ready = _readiness_payload(db)
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload


@router.get("")
def health_alias(response: Response, db: Session = Depends(get_db)) -> dict:
    """Backward-compatible alias for /health/ready (Phase 0 contract)."""
    payload, is_ready = _readiness_payload(db)
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload
