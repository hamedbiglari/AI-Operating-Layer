"""
Machine-readable representations of a Knowledge Object (§11, §12, §25).

THE RULE THIS FIXES (G8)

Before this, the only Markdown in the system was the WordPress plugin
rendering `post_content` — WordPress's copy of the text, not the canonical
Knowledge Object. That is exactly the drift §12 forbids: two
representations of "the same" knowledge that can disagree, with no way to
tell which is right.

Every representation here is generated from the SAME canonical Knowledge
Object:

    Knowledge Object  (source of truth)
      ├── Markdown    (this module)
      ├── JSON        (this module)
      └── JSON-LD     (this module)

Markdown is a DERIVED artifact (§13). It is never the source of knowledge.

CLAIM STATUS IS ALWAYS VISIBLE

Every claim carries its status and evidence strength in every format. A
draft claim and an approved one must never render identically — a consumer
that cannot tell them apart will quote both with equal confidence.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.claim import Claim
from app.models.entity import Entity
from app.models.enums import ClaimEvidenceStrength, ClaimStatus
from app.models.knowledge_object import KnowledgeObject


def _load(db: Session, *, knowledge_object_id: UUID, organization_id: UUID):
    ko = db.execute(
        select(KnowledgeObject).where(
            KnowledgeObject.id == knowledge_object_id,
            KnowledgeObject.organization_id == organization_id,
        )
    ).scalar_one_or_none()
    if ko is None:
        return None, [], []
    claims = db.execute(
        select(Claim).where(
            Claim.organization_id == organization_id,
            Claim.knowledge_object_id == knowledge_object_id,
        ).order_by(Claim.created_at.asc())
    ).scalars().all()
    entities = db.execute(
        select(Entity).where(
            Entity.organization_id == organization_id,
            Entity.knowledge_object_id == knowledge_object_id,
        ).order_by(Entity.created_at.asc())
    ).scalars().all()
    return ko, list(claims), list(entities)


def _verified_evidence_count(claim: Claim) -> int:
    return sum(
        1 for link in claim.evidence_links
        if link.evidence is not None and link.evidence.status.value == "verified"
    )


def to_markdown(db: Session, *, knowledge_object_id: UUID, organization_id: UUID) -> str | None:
    """Canonical Markdown for a Knowledge Object.

    Claim status is rendered inline rather than footnoted, because a reader
    scanning the list must not have to look elsewhere to learn that a claim
    is unverified."""
    ko, claims, entities = _load(
        db, knowledge_object_id=knowledge_object_id, organization_id=organization_id
    )
    if ko is None:
        return None

    lines: list[str] = [
        f"# {ko.canonical_name}",
        "",
        "<!-- Machine-readable representation generated from the canonical",
        "     Knowledge Object. Markdown is a derived artifact; the Knowledge",
        "     Object is the source of truth. Claim status and evidence",
        "     strength are stated for every claim - do not treat an",
        "     unverified claim as established. -->",
        "",
        f"- **Type:** {ko.object_type}",
        f"- **Status:** {ko.status.value}",
        f"- **Knowledge version:** {ko.version}",
        f"- **Updated:** {ko.updated_at.isoformat() if ko.updated_at else 'unknown'}",
        f"- **Canonical ID:** `{ko.id}`",
        "",
    ]

    if ko.description:
        lines += ["## Description", "", ko.description, ""]

    if entities:
        lines += ["## Entities", ""]
        for entity in entities:
            lines.append(f"- **{entity.canonical_name}** ({entity.entity_type})")
        lines.append("")

    lines += ["## Claims", ""]
    if not claims:
        lines += [
            "_No claims have been recorded for this object yet. "
            "This is an absence of data, not a negative finding._",
            "",
        ]
    else:
        lines += ["| Claim | Status | Evidence strength | Verified sources |",
                  "| --- | --- | --- | --- |"]
        for claim in claims:
            value = claim.object_value or (
                f"entity:{claim.object_entity_id}" if claim.object_entity_id else ""
            )
            text = f"{claim.predicate} {value}".strip().replace("|", "\\|")
            lines.append(
                f"| {text} | {claim.status.value} | "
                f"{claim.evidence_strength.value} | {_verified_evidence_count(claim)} |"
            )
        lines.append("")
        unverified = [c for c in claims if c.evidence_strength == ClaimEvidenceStrength.UNVERIFIED]
        if unverified:
            lines += [
                f"> **{len(unverified)} of {len(claims)} claims have no verified evidence.** "
                "They are listed for completeness and must not be cited as established.",
                "",
            ]

    lines += [
        "---",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()} from Knowledge Object "
        f"`{ko.id}` version {ko.version}._",
        "",
    ]
    return "\n".join(lines)


def to_json(db: Session, *, knowledge_object_id: UUID, organization_id: UUID) -> dict | None:
    """Structured representation. Same source, same claim statuses."""
    ko, claims, entities = _load(
        db, knowledge_object_id=knowledge_object_id, organization_id=organization_id
    )
    if ko is None:
        return None

    return {
        "id": str(ko.id),
        "canonical_name": ko.canonical_name,
        "object_type": ko.object_type,
        "status": ko.status.value,
        "description": ko.description,
        "knowledge_version": ko.version,
        "updated_at": ko.updated_at.isoformat() if ko.updated_at else None,
        "language": "und",  # the canonical object is language-neutral (§56)
        "entities": [
            {"id": str(e.id), "canonical_name": e.canonical_name, "entity_type": e.entity_type}
            for e in entities
        ],
        "claims": [
            {
                "id": str(c.id),
                "predicate": c.predicate,
                "object_value": c.object_value,
                "object_entity_id": str(c.object_entity_id) if c.object_entity_id else None,
                "status": c.status.value,
                "evidence_strength": c.evidence_strength.value,
                "verified_evidence_count": _verified_evidence_count(c),
                # Explicit rather than derivable: a consumer should not have
                # to reimplement the rule to know whether a claim is usable.
                "is_established": (
                    c.status == ClaimStatus.APPROVED
                    and c.evidence_strength != ClaimEvidenceStrength.UNVERIFIED
                ),
            }
            for c in claims
        ],
        "coverage": {
            "claim_count": len(claims),
            "approved_claim_count": sum(1 for c in claims if c.status == ClaimStatus.APPROVED),
            "unverified_claim_count": sum(
                1 for c in claims if c.evidence_strength == ClaimEvidenceStrength.UNVERIFIED
            ),
            "note": (
                "Absence of a claim is not a negative finding. Unverified claims "
                "are included for completeness and must not be cited as established."
            ),
        },
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def to_json_ld(db: Session, *, knowledge_object_id: UUID, organization_id: UUID) -> dict | None:
    """schema.org representation.

    ONLY claims that are approved AND evidence-backed become schema.org
    assertions. A draft claim published as structured data is a public
    claim the merchant cannot support - the same rule Phase 9 applied to
    product markup (ADR-042), applied to knowledge."""
    data = to_json(db, knowledge_object_id=knowledge_object_id, organization_id=organization_id)
    if data is None:
        return None

    established = [c for c in data["claims"] if c["is_established"]]
    document = {
        "@context": "https://schema.org",
        "@type": "DefinedTerm",
        "@id": f"urn:aiol:knowledge:{data['id']}",
        "name": data["canonical_name"],
        "termCode": data["object_type"],
        "version": data["knowledge_version"],
    }
    if data["description"]:
        document["description"] = data["description"]
    if data["updated_at"]:
        document["dateModified"] = data["updated_at"]
    if established:
        document["additionalProperty"] = [
            {
                "@type": "PropertyValue",
                "name": c["predicate"],
                "value": c["object_value"] or "",
            }
            for c in established
        ]
    return document
