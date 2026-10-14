"""
AI agent registry service (Phase 13, ADR-076).

Owns exactly one responsibility: turning a User-Agent string into an
`AiAgent` row for this tenant, creating the row if this is the first time
anyone has seen it.

The owner's requirement — "there must be no restriction on which AIs are
listed; every AI that comes in must appear" — is implemented by
`resolve_or_discover` having no rejection path. A client that matches
nothing still gets a row, fingerprinted and marked `DISCOVERED`. The only
thing an unrecognised agent does not get is a confident classification,
and that is reported as `PROBABLE`/`UNKNOWN` rather than hidden.
"""

import hashlib
import re
import unicodedata
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.ai_agent import AiAgent
from app.models.enums import (
    AccessPurpose,
    ActorConfidence,
    ActorType,
    AgentRegistrationOrigin,
)
from app.schemas.common import SortParams, apply_sort
from app.services import actor_signatures

# Version-ish and build-ish runs are stripped before fingerprinting so
# that Mozilla/5.0 ... Chrome/121.0.0.0 and Chrome/122.0.0.0 collapse to
# one agent rather than producing a new "discovered AI" every six weeks.
_VERSIONISH = re.compile(r"[0-9]+(?:[._][0-9]+)*")
_WHITESPACE = re.compile(r"\s+")

_BROWSERISH = re.compile(r"\b(Mozilla|Safari|Chrome|Firefox|Edg|OPR|SamsungBrowser)\b")
# Asymmetric on purpose, inherited verbatim from AIOL_Actors: crawler names
# are usually one concatenated token, but a bare "bot" substring would
# misclassify "robot", "abbot" and several real browser strings, so "bot"
# requires a word boundary and the others do not.
_AUTOMATON = re.compile(r"(crawler|spider|scraper)", re.IGNORECASE)
_BOT_TOKEN = re.compile(r"\bbot\b|bot/", re.IGNORECASE)


def fingerprint(user_agent: str) -> str:
    """Stable grouping key for an unrecognised client.

    Keeps the readable head of the string so a human can tell what it is,
    and appends a short hash so two different clients that share a head do
    not merge. Deliberately deterministic and reversible-by-eye rather
    than an opaque digest: the merchant has to be able to look at this row
    and decide something about it.
    """
    normalised = unicodedata.normalize("NFKC", user_agent).strip()
    stripped = _VERSIONISH.sub("#", normalised)
    stripped = _WHITESPACE.sub(" ", stripped).strip()
    digest = hashlib.sha256(stripped.encode("utf-8")).hexdigest()[:10]
    head = stripped[:100] if stripped else "empty-user-agent"
    return f"{head}#{digest}"


def classify(user_agent: str) -> tuple[ActorType, ActorConfidence, AccessPurpose, str]:
    """Pure classification. No database, no request context, unit-testable.

    Returns (actor_type, confidence, purpose, verification_note).

    A signature hit is `DETECTED`, never `VERIFIED`: matching a header is
    matching a claim. Reverse-DNS and published-IP-range confirmation are
    what would earn `VERIFIED`, and neither is implemented — so nothing in
    Phase 13 can write that value, and the note says why in words the
    merchant will read on the dashboard.
    """
    ua = (user_agent or "").strip()
    if not ua:
        return (
            ActorType.UNKNOWN,
            ActorConfidence.UNKNOWN,
            AccessPurpose.UNKNOWN,
            "No User-Agent header was sent. Nothing about this client is known.",
        )

    sig = actor_signatures.match(ua)
    if sig is not None:
        return (
            sig.actor_type,
            ActorConfidence.DETECTED,
            sig.purpose,
            (
                "Self-reported: the User-Agent header matched a published "
                f"signature for {sig.display_name}. The header was NOT verified "
                "by reverse DNS or against a published IP range, so this is a "
                "claim by the client, not a confirmed identity."
            ),
        )

    if _AUTOMATON.search(ua) or _BOT_TOKEN.search(ua):
        return (
            ActorType.UNKNOWN,
            ActorConfidence.PROBABLE,
            AccessPurpose.UNKNOWN,
            (
                "Unrecognised automated client: the User-Agent contains a "
                "crawler-like token but matches no known signature. Its "
                "operator and purpose are unknown."
            ),
        )

    if _BROWSERISH.search(ua):
        return (
            ActorType.HUMAN,
            ActorConfidence.PROBABLE,
            AccessPurpose.UNKNOWN,
            (
                "Probable browser: the User-Agent looks like a consumer "
                "browser. Automated clients routinely send browser strings, "
                "so this is a probability, not a fact."
            ),
        )

    return (
        ActorType.UNKNOWN,
        ActorConfidence.UNKNOWN,
        AccessPurpose.UNKNOWN,
        "Unrecognised client. No signature matched and no heuristic applied.",
    )


def resolve_or_discover(
    db: Session,
    *,
    organization_id: UUID,
    user_agent: str,
    observed_at=None,
) -> AiAgent:
    """Find the `AiAgent` for this User-Agent, creating it if new.

    THERE IS NO REJECTION PATH. Every distinct client gets a row. This is
    the difference between a registry and an allow-list, and it is the
    requirement.

    Not flushed here: the caller owns the transaction, because a telemetry
    batch resolves many agents and must commit once.
    """
    actor_type, confidence, purpose, note = classify(user_agent)
    sig = actor_signatures.match(user_agent or "")

    if sig is not None:
        signature = sig.needle
        display_name = sig.display_name
        vendor = sig.vendor
        origin = AgentRegistrationOrigin.SEEDED
    else:
        signature = fingerprint(user_agent or "")
        display_name = signature.split("#")[0][:160] or "Unidentified client"
        vendor = None
        origin = AgentRegistrationOrigin.DISCOVERED

    agent = db.execute(
        select(AiAgent).where(
            AiAgent.organization_id == organization_id,
            AiAgent.signature == signature,
        )
    ).scalar_one_or_none()

    now = observed_at or utcnow()

    if agent is None:
        agent = AiAgent(
            organization_id=organization_id,
            signature=signature,
            display_name=display_name,
            vendor=vendor,
            actor_type=actor_type,
            declared_purpose=purpose,
            confidence=confidence,
            origin=origin,
            verification_note=note,
            sample_user_agent=(user_agent or "")[:400] or None,
            first_seen_at=now,
            last_seen_at=now,
            observation_count=1,
        )
        db.add(agent)
        return agent

    # Existing agent: only the observation facts move. A merchant may have
    # renamed the agent or corrected its purpose, and re-seeing it must not
    # overwrite that judgment with the shipped default.
    agent.observation_count = (agent.observation_count or 0) + 1
    if agent.first_seen_at is None or now < agent.first_seen_at:
        agent.first_seen_at = now
    if agent.last_seen_at is None or now > agent.last_seen_at:
        agent.last_seen_at = now
    if agent.sample_user_agent is None and user_agent:
        agent.sample_user_agent = user_agent[:400]
    return agent


def list_agents(
    db: Session,
    *,
    organization_id: UUID,
    actor_type: ActorType | None = None,
    origin: AgentRegistrationOrigin | None = None,
    seen_only: bool = False,
    limit: int = 50,
    offset: int = 0,
    sort: SortParams | None = None,
) -> tuple[list[AiAgent], int]:
    from sqlalchemy import func

    stmt = select(AiAgent).where(AiAgent.organization_id == organization_id)
    if actor_type is not None:
        stmt = stmt.where(AiAgent.actor_type == actor_type)
    if origin is not None:
        stmt = stmt.where(AiAgent.origin == origin)
    if seen_only:
        stmt = stmt.where(AiAgent.observation_count > 0)

    total = db.execute(
        select(func.count()).select_from(stmt.subquery())
    ).scalar_one()

    stmt = apply_sort(stmt, AiAgent, sort, default_field="last_seen_at")
    rows = list(db.execute(stmt.limit(limit).offset(offset)).scalars().all())
    return rows, total


def rename(db: Session, *, agent: AiAgent, display_name: str) -> AiAgent:
    """A merchant may rename a discovered agent. The signature is never
    editable: it is the join key between traffic and policy, and letting it
    be edited would silently re-point every policy that referenced it."""
    agent.display_name = display_name.strip()[:160]
    return agent
