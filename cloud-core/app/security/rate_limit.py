"""
Tenant-aware rate limiting for adapter endpoints (ADR-039).

**Ordering is the whole design.** The limiter runs AFTER machine
identity resolution and BEFORE any Core work:

    authenticate (cheap, one indexed lookup + one hash)
        -> rate limit (one Redis INCR)
            -> expensive Core operation

Limiting before authentication would mean limiting by IP, which for a
WordPress plugin behind a shared host is both ineffective and unfair.
Limiting after Core work would defeat the purpose entirely. This
ordering is what makes the "cheap -> deterministic -> filtered ->
expensive only when necessary" resource principle actually enforceable
rather than aspirational.

Keyed by `installation_id`, so one misbehaving plugin cannot exhaust
another tenant's budget.

**Fail-open, deliberately, and documented as a trade-off.** If Redis is
unreachable the request proceeds rather than 503-ing. Reason: Redis is
not currently a hard dependency of the request path anywhere else in
this codebase, and a cache outage turning into a total integration
outage is a worse failure than a temporarily unenforced limit. The
readiness probe reports Redis degradation so operators see it
(`/health/ready`). If the cost model later makes unmetered traffic the
bigger risk, this becomes a settings flag - the decision point is
isolated here, not scattered.

Fixed-window counter rather than a token bucket: for burst protection
against retry storms and webhook floods, a window is sufficient,
obviously correct, and costs one round trip. A sliding window or
bucket would be more precise about burst shape and is not worth the
complexity until there is evidence it matters.
"""

import logging
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Response, status

from app.core.config import settings
from app.security.machine_identity import MachineIdentity, get_machine_identity

logger = logging.getLogger(__name__)

_WINDOW_SECONDS = 60


@dataclass(frozen=True)
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    retry_after: int


def _redis_client():
    """Imported lazily so that neither the import graph nor the test
    suite requires a live Redis."""
    try:
        import redis  # noqa: PLC0415

        return redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=0.25, socket_timeout=0.25)
    except Exception:  # noqa: BLE001 - any failure means "no limiter available"
        return None


def redis_available() -> bool:
    """Phase 13: the dashboard's status strip needs to distinguish three
    states, not two. A client object that constructs fine but cannot PING
    is NOT available - the limiter fails open in that case, which is
    exactly the `degraded` the merchant must be told about rather than a
    green light (ADR-039 / AIOL_Status)."""
    client = _redis_client()
    if client is None:
        return False
    try:
        return bool(client.ping())
    except Exception:  # noqa: BLE001
        return False


def check_rate_limit(*, installation_id: str, limit: int, window_seconds: int = _WINDOW_SECONDS) -> RateLimitResult:
    client = _redis_client()
    if client is None:
        return RateLimitResult(allowed=True, limit=limit, remaining=limit, retry_after=0)

    key = f"ratelimit:installation:{installation_id}"
    try:
        current = client.incr(key)
        if current == 1:
            client.expire(key, window_seconds)
        ttl = client.ttl(key)
    except Exception:  # noqa: BLE001 - see module docstring: fail open
        logger.warning("Rate limiter unavailable; allowing request", extra={"installation_id": installation_id})
        return RateLimitResult(allowed=True, limit=limit, remaining=limit, retry_after=0)

    remaining = max(limit - int(current), 0)
    return RateLimitResult(
        allowed=int(current) <= limit,
        limit=limit,
        remaining=remaining,
        retry_after=int(ttl) if ttl and ttl > 0 else window_seconds,
    )


def rate_limited(limit: int = 120):
    """Dependency factory. Note it depends on `get_machine_identity`,
    which is what guarantees the ordering described in the module
    docstring - the limiter cannot run before the identity exists."""

    def _dependency(
        response: Response,
        identity: MachineIdentity = Depends(get_machine_identity),
    ) -> MachineIdentity:
        result = check_rate_limit(installation_id=str(identity.installation_id), limit=limit)
        response.headers["X-RateLimit-Limit"] = str(result.limit)
        response.headers["X-RateLimit-Remaining"] = str(result.remaining)
        if not result.allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded for this installation.",
                headers={"Retry-After": str(result.retry_after)},
            )
        return identity

    return _dependency
