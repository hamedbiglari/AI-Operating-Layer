"""
Integration tests for GET /dashboard/summary. Every count is checked against
the `total` of the list endpoint the Dashboard card links to, so the two
cannot drift. Conversions have no org-wide list endpoint, so their counts are
checked against rows seeded directly.
"""

import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from sqlalchemy import select, update

from app.models.document_artifact import DocumentConversion
from app.models.source import Source
from app.services.dashboard_service import (
    FAILED_STATES,
    IN_PROGRESS_STATES,
    REVIEW_STATES,
    SUCCEEDED_STATES,
)

SUMMARY = "/api/v1/dashboard/summary"


def _total(client: TestClient, headers: dict, path: str) -> int:
    response = client.get(path, headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["total"]


def _seed_knowledge(client: TestClient, headers: dict) -> None:
    """3 sources, 2 evidence pending review, 2 conflicting claims, 2 open gaps,
    each next to rows in another state that must not be counted."""
    sources = [
        client.post("/api/v1/sources", json={"source_type": "website", "title": f"S{i}"}, headers=headers).json()
        for i in range(3)
    ]
    for i, status in enumerate(["pending_review", "pending_review", "verified"]):
        evidence = client.post(
            "/api/v1/evidence", json={"source_id": sources[0]["id"], "summary": f"E{i}"}, headers=headers
        ).json()
        reviewed = client.post(f"/api/v1/evidence/{evidence['id']}/review", json={"status": status}, headers=headers)
        assert reviewed.status_code == 200, reviewed.text
    response = client.post("/api/v1/evidence", json={"source_id": sources[0]["id"], "summary": "left as draft"},
                           headers=headers)
    assert response.status_code == 201, response.text

    ko = client.post("/api/v1/knowledge", json={"canonical_name": "Taranjabin", "object_type": "plant"},
                     headers=headers).json()
    subject = client.post("/api/v1/entities", json={"knowledge_object_id": ko["id"], "entity_type": "plant",
                                                    "canonical_name": "Taranjabin"}, headers=headers).json()
    for predicate, review in [("contains", {"status": "disputed", "evidence_strength": "conflicting"}),
                              ("relates_to", {"status": "disputed", "evidence_strength": "conflicting"}),
                              ("is_source_of", {"status": "approved", "evidence_strength": "strong"})]:
        claim = client.post("/api/v1/claims", json={"knowledge_object_id": ko["id"], "subject_entity_id": subject["id"],
                                                     "predicate": predicate, "object_value": "x"},
                            headers=headers).json()
        reviewed = client.post(f"/api/v1/claims/{claim['id']}/review", json=review, headers=headers)
        assert reviewed.status_code == 200, reviewed.text

    gaps = [
        client.post("/api/v1/knowledge-gaps", json={"knowledge_object_id": ko["id"], "gap_type": "evidence_gap",
                                                    "description": f"G{i}"}, headers=headers).json()
        for i in range(3)
    ]
    response = client.patch(f"/api/v1/knowledge-gaps/{gaps[2]['id']}", json={"status": "resolved"}, headers=headers)
    assert response.status_code == 200, response.text


def _document(client: TestClient, headers: dict) -> tuple[str, str]:
    source = client.post("/api/v1/sources", json={"source_type": "website", "title": "Doc source"},
                         headers=headers).json()
    doc = client.post(f"/api/v1/documents?source_id={source['id']}", json={"title": "D", "content": "text"},
                      headers=headers).json()
    return doc["id"], doc["organization_id"]


def _conversion(db, *, document_id: str, organization_id: str, state: str, current: bool = True,
                created_at: datetime | None = None) -> None:
    flagged = state in ("failed", "needs_review")
    db.add(DocumentConversion(
        organization_id=uuid.UUID(organization_id), document_id=uuid.UUID(document_id),
        original_filename="f.pdf", source_hash="0" * 64, source_size_bytes=1,
        converter_name="test", converter_version="1", processing_state=state, is_current=current,
        superseded_at=None if current else datetime.now(timezone.utc),
        needs_review=flagged, review_reasons=["test_reason"] if flagged else [],
        **({"created_at": created_at} if created_at else {}),
    ))
    db.flush()


def test_summary_requires_authentication(client: TestClient) -> None:
    assert client.get(SUMMARY).status_code == 401


def test_empty_organization_has_zero_counts_and_null_duplicates(client: TestClient, register_org) -> None:
    body = client.get(SUMMARY, headers=register_org()["headers"]).json()
    assert body["sources"] == {"total": 0, "added_last_30d": 0}
    assert body["conversions"] == {"in_progress": 0, "oldest_queued_at": None, "succeeded": 0, "failed": 0}
    assert body["review"] == {"conversions": 0, "evidence_pending": 0, "claims_conflicting": 0, "gaps_open": 0}
    # Not tracked yet: null, never 0.
    assert body["duplicate_decisions"] is None


def test_counts_match_list_endpoint_totals(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    headers = org["headers"]
    _seed_knowledge(client, headers)
    # One source older than the 30-day window.
    oldest = db_session.execute(
        select(Source.id).where(Source.organization_id == uuid.UUID(org["organization"]["id"])).limit(1)
    ).scalar_one()
    db_session.execute(update(Source).where(Source.id == oldest)
                       .values(created_at=datetime.now(timezone.utc) - timedelta(days=40)))
    db_session.flush()

    body = client.get(SUMMARY, headers=headers).json()

    assert body["sources"]["total"] == _total(client, headers, "/api/v1/sources?limit=1") == 3
    assert body["sources"]["added_last_30d"] == 2
    assert body["review"]["evidence_pending"] == _total(
        client, headers, "/api/v1/evidence?status=pending_review&limit=1") == 2
    assert body["review"]["claims_conflicting"] == _total(
        client, headers, "/api/v1/claims?evidence_strength=conflicting&limit=1") == 2
    assert body["review"]["gaps_open"] == _total(client, headers, "/api/v1/knowledge-gaps?status=open&limit=1") == 2


def test_conversion_counts_from_seeded_rows(client: TestClient, register_org, db_session) -> None:
    headers = register_org()["headers"]
    docs = [_document(client, headers) for _ in range(6)]
    org_id = docs[0][1]
    assert db_session.execute(select(DocumentConversion).where(
        DocumentConversion.organization_id == uuid.UUID(org_id))).first() is None, "documents API made conversions"

    long_ago = datetime(2026, 1, 1, tzinfo=timezone.utc)
    seed = [
        # (document, state, current, created_at)
        (0, "processed", True, None),            # succeeded
        (0, "queued", False, None),              # reprocess in flight: in progress, not current
        (1, "failed", True, None),               # failed (also flagged; must not be counted under review)
        (1, "processing", False, None),          # reprocess in flight
        (2, "partially_processed", True, None),  # review, never succeeded
        (3, "needs_review", True, None),         # review
        (4, "queued", True, long_ago),           # first upload in flight; oldest queued
        (5, "processed", True, None),            # succeeded
        (5, "failed", False, None),              # failed reprocess: old version still current, not counted
    ]
    for doc, state, current, created_at in seed:
        _conversion(db_session, document_id=docs[doc][0], organization_id=org_id, state=state, current=current,
                    created_at=created_at)

    body = client.get(SUMMARY, headers=headers).json()

    assert body["conversions"]["in_progress"] == 3
    assert body["conversions"]["succeeded"] == 2
    assert body["conversions"]["failed"] == 1
    assert body["review"]["conversions"] == 2
    assert datetime.fromisoformat(body["conversions"]["oldest_queued_at"]) == long_ago

    # Every current, finished conversion is in exactly one outcome group.
    groups = [SUCCEEDED_STATES, FAILED_STATES, REVIEW_STATES, IN_PROGRESS_STATES]
    assert all(len(set(a) & set(b)) == 0 for i, a in enumerate(groups) for b in groups[i + 1:])
    current_finished = [state for _, state, current, _ in seed if current and state not in IN_PROGRESS_STATES]
    assert len(current_finished) == (body["conversions"]["succeeded"] + body["conversions"]["failed"]
                                     + body["review"]["conversions"])


def test_other_organization_is_never_counted(client: TestClient, register_org, db_session) -> None:
    mine = register_org()
    other = register_org()
    _seed_knowledge(client, other["headers"])
    # One conversion in each group: in progress, succeeded, failed, review.
    for state in ("queued", "processed", "failed", "needs_review"):
        doc_id, other_org_id = _document(client, other["headers"])
        _conversion(db_session, document_id=doc_id, organization_id=other_org_id, state=state)

    body = client.get(SUMMARY, headers=mine["headers"]).json()
    assert body["sources"]["total"] == 0
    assert body["conversions"] == {"in_progress": 0, "oldest_queued_at": None, "succeeded": 0, "failed": 0}
    assert body["review"] == {"conversions": 0, "evidence_pending": 0, "claims_conflicting": 0, "gaps_open": 0}

    # And the other organization sees its own rows.
    theirs = client.get(SUMMARY, headers=other["headers"]).json()
    assert theirs["sources"]["total"] == 7
    assert theirs["conversions"]["in_progress"] == 1
    assert theirs["conversions"]["succeeded"] == 1
    assert theirs["conversions"]["failed"] == 1
    assert theirs["review"]["conversions"] == 1
