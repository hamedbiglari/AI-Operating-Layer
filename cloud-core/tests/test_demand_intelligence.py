"""Demand Intelligence (REQ-DI-001..003, ADR-099): real sources only, distinct, normalised,
feeding research. No connector is ever simulated."""
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.core.config import settings
from app.models.enums import SearchDemandSource
from app.services import search_demand_service

D = "/api/v1/demand"
GSC_CSV = ("Top queries,Clicks,Impressions,CTR,Position\n"
           "toranjebin benefits,12,340,3.53%,7.2\n"
           "buy toranjebin online,4,120,3.33%,11.5\n"
           ",1,1,1%,1\n").encode()


def _org_id(org):
    return uuid.UUID(str(org["organization"]["id"]))


def _searches(db, org, text, n, zero=False):
    for i in range(n):
        search_demand_service.record_search(
            db, organization_id=_org_id(org), site_id=None, event_key=f"{text}-{i}-{uuid.uuid4().hex[:6]}",
            search_text=text, demand_source=SearchDemandSource.ONSITE_SEARCH, occurred_at=datetime.now(timezone.utc),
            result_count=0 if zero else 3)
    db.commit()


def test_internal_search_becomes_real_signals(client: TestClient, db_session, register_org) -> None:
    org = register_org()
    _searches(db_session, org, "toranjebin price", 3, zero=True)
    _searches(db_session, org, "mannitol", 2)
    r = client.post(f"{D}/sync/internal-search", headers=org["headers"]).json()
    assert r["created"] == 2
    sig = {s["query_text"]: s for s in client.get(f"{D}/signals?source_type=internal_search", headers=org["headers"]).json()["items"]}
    assert sig["toranjebin price"]["searches"] == 3 and sig["toranjebin price"]["zero_result_searches"] == 3
    assert sig["mannitol"]["zero_result_searches"] == 0
    # search-engine metrics are not invented for first-party searches
    assert sig["mannitol"]["impressions"] is None and sig["mannitol"]["clicks"] is None
    # re-sync is idempotent (updates, never duplicates)
    again = client.post(f"{D}/sync/internal-search", headers=org["headers"]).json()
    assert again["created"] == 0 and again["updated"] == 2


def test_gsc_export_import_normalises_and_keeps_the_raw_row(client: TestClient, register_org) -> None:
    org = register_org()
    r = client.post(f"{D}/import/gsc-export", headers=org["headers"], files={"file": ("q.csv", GSC_CSV, "text/csv")},
                    data={"period_label": "2026-08"})
    assert r.status_code == 201, r.text
    assert r.json() == {"source_type": "gsc_export", "created": 2, "updated": 0, "skipped_empty": 1}
    items = client.get(f"{D}/signals?source_type=gsc_export&sort_by=impressions&sort_dir=desc", headers=org["headers"]).json()["items"]
    top = items[0]
    assert top["query_text"] == "toranjebin benefits" and top["impressions"] == 340 and top["clicks"] == 12
    assert abs(float(top["ctr"]) - 0.0353) < 1e-6 and float(top["position"]) == 7.2
    # internal-search metrics are not invented for GSC rows
    assert top["searches"] is None
    again = client.post(f"{D}/import/gsc-export", headers=org["headers"], files={"file": ("q.csv", GSC_CSV, "text/csv")},
                        data={"period_label": "2026-08"}).json()
    assert again["created"] == 0 and again["updated"] == 2


def test_live_connectors_are_honestly_blocked_without_oauth(client: TestClient, register_org, monkeypatch) -> None:
    org = register_org()
    monkeypatch.setattr(settings, "GSC_OAUTH_CLIENT_ID", None)
    r = client.post(f"{D}/connections/gsc/connect", headers=org["headers"], json={"property_ref": "sc-domain:example.com"}).json()
    assert r["status"] == "BLOCKED_EXTERNAL_DEPENDENCY" and "OAuth" in r["last_error"]
    conns = {c["source_type"]: c for c in client.get(f"{D}/connections", headers=org["headers"]).json()}
    assert conns["gsc"]["status"] == "BLOCKED_EXTERNAL_DEPENDENCY" and conns["ga4"]["status"] == "NOT_CONNECTED"
    assert conns["gsc"]["imported_rows"] == 0 and conns["gsc"]["last_sync_at"] is None      # nothing faked
    assert client.post(f"{D}/connections/semrush/connect", headers=org["headers"], json={}).status_code == 404


def test_demand_feeds_research_with_traceability(client: TestClient, db_session, register_org) -> None:
    org = register_org()
    _searches(db_session, org, "is toranjebin safe for children", 2, zero=True)
    client.post(f"{D}/sync/internal-search", headers=org["headers"])
    sig = client.get(f"{D}/signals?source_type=internal_search", headers=org["headers"]).json()["items"][0]
    r = client.post(f"{D}/signals/promote", headers=org["headers"], json={"signal_ids": [sig["id"]]})
    assert r.status_code == 201, r.text
    task_id = r.json()["tasks"][0]["research_task_id"]
    task = client.get(f"/api/v1/research/tasks/{task_id}", headers=org["headers"]).json()
    assert task["query"] == "is toranjebin safe for children"
    after = client.get(f"{D}/signals?status=promoted", headers=org["headers"]).json()["items"][0]
    assert after["research_task_id"] == task_id and "found nothing" in after["information_need"]


def test_sources_stay_distinct(client: TestClient, db_session, register_org) -> None:
    org = register_org()
    _searches(db_session, org, "toranjebin benefits", 1)
    client.post(f"{D}/sync/internal-search", headers=org["headers"])
    client.post(f"{D}/import/gsc-export", headers=org["headers"], files={"file": ("q.csv", GSC_CSV, "text/csv")})
    rows = client.get(f"{D}/signals?q=toranjebin benefits&limit=50", headers=org["headers"]).json()["items"]
    assert sorted(r["source_type"] for r in rows) == ["gsc_export", "internal_search"]   # same query, two sources, not merged


def test_demand_is_tenant_isolated(client: TestClient, db_session, register_org) -> None:
    a, b = register_org(), register_org()
    client.post(f"{D}/import/gsc-export", headers=a["headers"], files={"file": ("q.csv", GSC_CSV, "text/csv")})
    assert client.get(f"{D}/signals", headers=b["headers"]).json()["total"] == 0
    sig = client.get(f"{D}/signals", headers=a["headers"]).json()["items"][0]
    r = client.post(f"{D}/signals/promote", headers=b["headers"], json={"signal_ids": [sig["id"]]})
    assert r.status_code == 404
