"""Seed one fresh organization for live end-to-end checks of the harness.

Everything goes through the real Cloud Core API except document conversions,
which have no create endpoint and are written through the ORM (as
tests/test_dashboard_summary.py does). Prints JSON with the organization
name, its access token and the /dashboard/summary it produced.

Needs a running Cloud Core and the same DATABASE_URL it uses:
  cd cloud-core
  DATABASE_URL=postgresql+psycopg://aiol:aiol_dev_password@localhost:5432/aiol \
    .venv/Scripts/python.exe ../visual-harness/e2e/seed.py [http://127.0.0.1:8000] > seed.json

Seeded counts (the Dashboard expects exactly these):
  sources 4 (all added today); conversions: 3 in progress (oldest queued 25 min
  ago), 4 succeeded, 1 failed, 2 to review; evidence pending review 2;
  conflicting claims 3; open gaps 2.
"""

import json
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "cloud-core"))

import httpx  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.models.document_artifact import DocumentConversion  # noqa: E402

API = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/") + "/api/v1"
client = httpx.Client(base_url=API, timeout=30)


def ok(response: httpx.Response) -> dict:
    assert response.status_code in (200, 201), (str(response.request.url), response.status_code, response.text[:300])
    return response.json()


stamp = int(time.time())
org = ok(client.post("/auth/register-organization", json={
    "organization_name": f"E2E Dashboard {stamp}", "owner_email": f"e2e-{stamp}@example.dev",
    "owner_name": "E2E Owner", "owner_password": "supersecret123"}))
token = org["token"]["access_token"]
client.headers["Authorization"] = "Bearer " + token

# Sources: 3 plain + 1 that holds the documents.
sources = [ok(client.post("/sources", json={"source_type": "website", "title": f"Source {i}"})) for i in range(3)]
doc_source = ok(client.post("/sources", json={"source_type": "website", "title": "Document source"}))

# Evidence: 2 pending review (counted), 1 verified and 1 draft (not counted).
for status in ("pending_review", "pending_review", "verified"):
    evidence = ok(client.post("/evidence", json={"source_id": sources[0]["id"], "summary": "E " + status}))
    ok(client.post(f"/evidence/{evidence['id']}/review", json={"status": status}))
ok(client.post("/evidence", json={"source_id": sources[0]["id"], "summary": "draft"}))

# Claims: 3 conflicting (counted), 1 strong (not counted).
ko = ok(client.post("/knowledge", json={"canonical_name": "Taranjabin", "object_type": "plant"}))
entity = ok(client.post("/entities", json={"knowledge_object_id": ko["id"], "entity_type": "plant", "canonical_name": "Taranjabin"}))
for predicate, strength in (("contains", "conflicting"), ("relates_to", "conflicting"), ("treats", "conflicting"),
                            ("is_source_of", "strong")):
    claim = ok(client.post("/claims", json={"knowledge_object_id": ko["id"], "subject_entity_id": entity["id"],
                                            "predicate": predicate, "object_value": "x"}))
    ok(client.post(f"/claims/{claim['id']}/review", json={
        "status": "disputed" if strength == "conflicting" else "approved", "evidence_strength": strength}))

# Gaps: 2 open + 1 resolved.
gaps = [ok(client.post("/knowledge-gaps", json={"knowledge_object_id": ko["id"], "gap_type": "evidence_gap",
                                                "description": f"G{i}"})) for i in range(3)]
ok(client.patch(f"/knowledge-gaps/{gaps[2]['id']}", json={"status": "resolved"}))

# Conversions, one document each.
now = datetime.now(timezone.utc)
plan = [("queued", 25), ("queued", 5), ("processing", None), ("processed", None), ("processed", None),
        ("processed", None), ("completed", None), ("failed", None), ("partially_processed", None), ("needs_review", None)]
db = SessionLocal()
for i, (state, minutes_ago) in enumerate(plan):
    doc = ok(client.post(f"/documents?source_id={doc_source['id']}", json={"title": f"Doc {i}", "content": "text"}))
    flagged = state in ("failed", "needs_review")
    db.add(DocumentConversion(
        organization_id=uuid.UUID(doc["organization_id"]), document_id=uuid.UUID(doc["id"]),
        original_filename=f"doc{i}.pdf", source_hash=f"{i:064x}", source_size_bytes=1, converter_name="e2e-seed",
        converter_version="1", processing_state=state, is_current=True, superseded_at=None,
        needs_review=flagged, review_reasons=["e2e_seed"] if flagged else [],
        **({"created_at": now - timedelta(minutes=minutes_ago)} if minutes_ago else {})))
db.commit()
db.close()

print(json.dumps({"organization": f"E2E Dashboard {stamp}", "token": token,
                  "summary": ok(client.get("/dashboard/summary"))}, indent=1))
