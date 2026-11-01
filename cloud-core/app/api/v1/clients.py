"""
GET /clients/config — what the official clients may link to and what has actually been published (ADR-137).
GET /clients/updates/{target}/{arch}/{current_version} — the signed desktop update, if any (ADR-140).

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

from fastapi import APIRouter, Path, Query, Response

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
        # ADR-139: the version the sign-in checkbox accepts, and what that one tick covers.
        "terms": {"version": settings.CLIENT_TERMS_VERSION, "consents": ["terms", "privacy", "device_intelligence"]},
        "device_intelligence": {"enabled": settings.DEVICE_INTELLIGENCE_ENABLED,
                                "observation_retention_days": settings.DEVICE_OBSERVATION_RETENTION_DAYS},
        "session": {"access_token_minutes": settings.NATIVE_ACCESS_TOKEN_EXPIRE_MINUTES,
                    "refresh_days": settings.REFRESH_TOKEN_EXPIRE_DAYS},
    }


# --------------------------------------------------------------------------- signed desktop updates (ADR-140)
_UPDATE_TARGETS = {"windows", "darwin"}
_ARCHES = {"x86_64", "aarch64", "i686"}


def _version_tuple(v: str) -> tuple[int, ...] | None:
    core = (v or "").strip().lstrip("v").split("-", 1)[0].split("+", 1)[0]
    parts = core.split(".")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        return None
    return tuple(int(p) for p in parts)


def _updates() -> dict:
    raw = settings.CLIENT_UPDATES_JSON.strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("CLIENT_UPDATES_JSON is not valid JSON; no update is offered")
        return {}
    return data if isinstance(data, dict) else {}


@router.get("/updates/{target}/{arch}/{current_version}")
def update_check(target: str = Path(max_length=20), arch: str = Path(max_length=20),
                 current_version: str = Path(max_length=40)):
    """The Tauri updater's endpoint. 204 = no update. 200 = {version, url, signature, notes, pub_date} for a
    strictly newer, operator-published, signed release. Anything malformed or unsigned is never offered: the
    app would refuse it anyway (it verifies the signature with its built-in public key), and offering it would
    only make every launch fail an update."""
    if target not in _UPDATE_TARGETS or arch not in _ARCHES:
        return Response(status_code=204)
    entry = _updates().get(f"{target}-{arch}")
    current = _version_tuple(current_version)
    if not isinstance(entry, dict) or current is None:
        return Response(status_code=204)
    offered = _version_tuple(str(entry.get("version", "")))
    url = _link(entry.get("url"))
    signature = entry.get("signature")
    if offered is None or offered <= current or not url or not url.startswith("https://") \
            or not isinstance(signature, str) or len(signature) < 40:
        return Response(status_code=204)
    return {"version": str(entry["version"]).lstrip("v"), "url": url, "signature": signature,
            "notes": entry.get("notes") or "", "pub_date": entry.get("pub_date")}
