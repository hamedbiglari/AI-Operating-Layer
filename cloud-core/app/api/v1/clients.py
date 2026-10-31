"""
GET /clients/config — what the official clients may link to and what has actually been published (ADR-137).

Public (no session): a signed-out client needs Help, Privacy and Terms on its sign-in screen. It returns only
operator configuration — no tenant, user or usage data.

Every link is null unless an operator configured it; the clients hide a menu item whose link is null rather than
invent a destination. `releases` lists only what CLIENT_RELEASES_JSON declares; an empty list means nothing is
published, and the clients say exactly that.
"""
from __future__ import annotations

import json
import logging
from urllib.parse import urlparse

from fastapi import APIRouter, Query

from app.core.config import settings

router = APIRouter(prefix="/clients", tags=["clients"])
logger = logging.getLogger(__name__)

PLATFORMS = ("windows", "macos", "android", "ios", "web")
RELEASE_STATUSES = ("AVAILABLE", "PREVIEW", "COMING_SOON", "NOT_SUPPORTED")


def _link(value: str | None) -> str | None:
    value = (value or "").strip()
    if not value:
        return None
    parsed = urlparse(value)
    allowed = ("https",) if settings.is_production else ("https", "http")
    if parsed.scheme not in allowed or not parsed.netloc:
        return None
    return value


def releases() -> list[dict]:
    raw = settings.CLIENT_RELEASES_JSON.strip()
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("CLIENT_RELEASES_JSON is not valid JSON; no releases are reported")
        return []
    out = []
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        platform, state = item.get("platform"), item.get("status")
        if platform not in PLATFORMS or state not in RELEASE_STATUSES:
            continue
        url = _link(item.get("url"))
        if state == "AVAILABLE" and url is None:
            continue           # "available" with nowhere to get it from is not available
        out.append({"platform": platform, "status": state, "version": item.get("version"), "url": url})
    return out


@router.get("/config")
def client_config(platform: str | None = Query(default=None, max_length=20)) -> dict:
    upgrade_platforms = {p.strip() for p in settings.CLIENT_UPGRADE_PLATFORMS.split(",") if p.strip()}
    upgrade = _link(settings.CLIENT_UPGRADE_URL)
    upgrade_state = "available" if upgrade else "not_configured"
    if upgrade and platform and platform not in upgrade_platforms:
        upgrade, upgrade_state = None, "not_offered_on_platform"
    return {
        "links": {
            "help": _link(settings.CLIENT_HELP_URL),
            "learn_more": _link(settings.CLIENT_LEARN_MORE_URL),
            "privacy": _link(settings.CLIENT_PRIVACY_URL),
            "terms": _link(settings.CLIENT_TERMS_URL),
            "docs": _link(settings.CLIENT_DOCS_URL),
            "report_problem": _link(settings.CLIENT_REPORT_PROBLEM_URL),
        },
        "upgrade": {"url": upgrade, "state": upgrade_state},
        "releases": releases(),
        "languages": ["en", "fa"],
        "device_intelligence": {"enabled": settings.DEVICE_INTELLIGENCE_ENABLED,
                                "observation_retention_days": settings.DEVICE_OBSERVATION_RETENTION_DAYS},
        "session": {"access_token_minutes": settings.NATIVE_ACCESS_TOKEN_EXPIRE_MINUTES,
                    "refresh_days": settings.REFRESH_TOKEN_EXPIRE_DAYS},
    }
