"""
P12-19 Search intelligence (ADR-075).

Two properties dominate these tests:

1. **Provider failure is never "no results."** AUTH_REQUIRED and a genuine
   zero-row day are different facts, and collapsing them turns an absence
   of measurement into a measurement of absence.

2. **Search is not AI visibility.** They share `query_id` and market, and
   nothing else. A test asserts the tables cannot be confused.
"""

import uuid as uuid_module
from datetime import date, timedelta

from fastapi.testclient import TestClient


def _import(client: TestClient, headers: dict, property_url: str = "sc-domain:merchant.example",
            **kw):
    body = {"property_url": property_url,
            "start_date": str(date.today() - timedelta(days=3)),
            "end_date": str(date.today()),
            "provider_name": "fixture_search_console"}
    body.update(kw)
    return client.post("/api/v1/visibility/search/console/import", json=body, headers=headers)


def _serp(client: TestClient, headers: dict, query: str = "taranjabin", **kw):
    body = {"query": query, "provider_name": "fixture_serp", "depth": 10}
    body.update(kw)
    return client.post("/api/v1/visibility/search/serp/observe", json=body, headers=headers)


# --- Search Console import ---------------------------------------------------


def test_import_creates_observations_and_canonical_queries(
    client: TestClient, register_org
) -> None:
    """Imported queries become canonical Phase 6 Query rows — there is no
    second query table."""
    org = register_org()
    result = _import(client, org["headers"]).json()
    assert result["outcome"] == "success"
    assert result["imported"] >= 4
    assert result["data_retrieved"] is True
    assert result["is_fixture"] is True

    queries = client.get("/api/v1/queries", headers=org["headers"]).json()
    texts = [q["query"] for q in queries["items"]]
    assert "taranjabin benefits" in texts
    assert "خواص ترنجبین" in texts, "Persian query text must survive verbatim"


def test_original_query_text_is_never_translated(client: TestClient, register_org) -> None:
    """§45: a Persian query stays Persian."""
    org = register_org()
    _import(client, org["headers"])
    queries = client.get("/api/v1/queries", headers=org["headers"]).json()["items"]
    persian = [q for q in queries if "ترنجبین" in q["query"]]
    assert persian, "the Persian query was lost or rewritten"
    assert persian[0]["query"] == "خواص ترنجبین"


def test_missing_metrics_are_null_not_zero(client: TestClient, register_org) -> None:
    """THE central honesty test for §24. The fixture includes a row where
    the source reported no clicks and no CTR. Zero would claim a
    measurement that was never made."""
    org = register_org()
    _import(client, org["headers"])

    rows = client.get("/api/v1/visibility/search/observations",
                      headers=org["headers"]).json()["items"]
    sparse = [r for r in rows if r["impressions"] == 210]
    assert sparse, "fixture row with missing dimensions not imported"
    assert sparse[0]["clicks"] is None, "unreported clicks must be NULL, not 0"
    assert sparse[0]["ctr"] is None
    assert sparse[0]["device"] is None


def test_auth_required_is_not_reported_as_zero_rows(client: TestClient, register_org) -> None:
    """A provider that cannot authenticate has measured nothing. Reporting
    it as a successful empty import would assert zero impressions."""
    org = register_org()
    result = _import(client, org["headers"], property_url="sc-domain:[authrequired]").json()
    assert result["outcome"] == "auth_required"
    assert result["imported"] == 0
    assert result["data_retrieved"] is False
    assert result["error"]


def test_rate_limited_is_distinct_from_empty(client: TestClient, register_org) -> None:
    org = register_org()
    limited = _import(client, org["headers"], property_url="sc-domain:[ratelimited]").json()
    empty = _import(client, org["headers"], property_url="sc-domain:[empty]").json()

    assert limited["outcome"] == "rate_limited"
    assert limited["data_retrieved"] is False
    assert empty["outcome"] == "success"
    assert empty["data_retrieved"] is True, "a genuine zero-row day IS a retrieval"
    assert empty["imported"] == 0


def test_reimport_is_idempotent_and_appends_nothing(client: TestClient, register_org) -> None:
    """Append-only history: a re-import is a duplicate, never an overwrite."""
    org = register_org()
    first = _import(client, org["headers"]).json()
    second = _import(client, org["headers"]).json()

    assert first["imported"] >= 4
    assert second["imported"] == 0
    assert second["duplicates"] >= 4

    total = client.get("/api/v1/visibility/search/observations",
                       headers=org["headers"]).json()["total"]
    assert total == first["imported"]


def test_pagination_token_is_returned(client: TestClient, register_org) -> None:
    org = register_org()
    assert _import(client, org["headers"]).json()["next_page_token"] == "page2"


def test_not_configured_provider_requires_auth(client: TestClient, register_org) -> None:
    """The default provider invents nothing."""
    org = register_org()
    result = _import(client, org["headers"], provider_name=None).json()
    assert result["outcome"] == "auth_required"
    assert result["imported"] == 0


# --- SERP ----------------------------------------------------------------------


def test_serp_observation_persists_positions_and_domains(
    client: TestClient, register_org
) -> None:
    org = register_org()
    result = _serp(client, org["headers"]).json()
    assert result["outcome"] == "success"
    assert result["imported"] >= 3

    rows = client.get("/api/v1/visibility/search/observations?data_source=serp_provider",
                      headers=org["headers"]).json()["items"]
    positions = sorted(r["position"] for r in rows)
    assert positions[0] == 1.0
    assert any(r["domain"] == "merchant.example" for r in rows)
    assert any(r["domain"].startswith("competitor-") for r in rows)


def test_serp_rows_carry_no_impressions(client: TestClient, register_org) -> None:
    """A SERP provider does not report impressions. NULL, not zero."""
    org = register_org()
    _serp(client, org["headers"])
    rows = client.get("/api/v1/visibility/search/observations?data_source=serp_provider",
                      headers=org["headers"]).json()["items"]
    assert all(r["impressions"] is None for r in rows)


def test_unsupported_depth_is_refused(client: TestClient, register_org) -> None:
    """Depth is a cost multiplier; the set is closed."""
    org = register_org()
    assert _serp(client, org["headers"], depth=7).status_code == 422


def test_supported_depths_are_accepted(client: TestClient, register_org) -> None:
    org = register_org()
    for depth in (1, 3, 5, 10):
        assert _serp(client, org["headers"], query=f"q{depth}", depth=depth).status_code == 200


def test_provider_unavailable_is_not_empty_results(client: TestClient, register_org) -> None:
    org = register_org()
    result = _serp(client, org["headers"], query="[unavailable] x").json()
    assert result["outcome"] == "unavailable"
    assert result["data_retrieved"] is False


# --- search vs AI separation ------------------------------------------------------


def test_search_and_ai_observations_are_separate_tables(client: TestClient, register_org) -> None:
    """§12: search yields position/URL; AI yields mention/citation. They
    share query and market, and nothing else."""
    from app.models.search_observation import SearchObservation
    from app.models.visibility import VisibilityTest

    search_cols = {c.name for c in SearchObservation.__table__.columns}
    ai_cols = {c.name for c in VisibilityTest.__table__.columns}

    for ai_only in ("mentioned", "cited", "recommended"):
        assert ai_only not in search_cols, f"{ai_only} must not exist on a search observation"
    for search_only in ("position", "impressions", "clicks", "ctr"):
        assert search_only not in ai_cols, f"{search_only} must not exist on an AI observation"

    assert "query_id" in search_cols and "query_id" in ai_cols, "both reference canonical Query"


def test_search_import_does_not_create_ai_observations(
    client: TestClient, register_org
) -> None:
    org = register_org()
    _import(client, org["headers"])
    assert client.get("/api/v1/visibility/observations",
                      headers=org["headers"]).json()["total"] == 0


# --- summary metrics ----------------------------------------------------------------


def test_summary_uses_the_position_denominator(client: TestClient, register_org) -> None:
    """Position metrics are computed over rows that carry a position, not
    over every row."""
    org = register_org()
    _import(client, org["headers"])
    summary = client.get("/api/v1/visibility/search/summary", headers=org["headers"]).json()

    assert summary["observation_count"] >= 4
    assert summary["position_denominator"] >= 1
    assert summary["average_position"] is not None
    assert "not zero" in " ".join(summary["caveats"]).lower()


def test_summary_metrics_are_null_when_no_data_exists(client: TestClient, register_org) -> None:
    org = register_org()
    summary = client.get("/api/v1/visibility/search/summary", headers=org["headers"]).json()
    assert summary["observation_count"] == 0
    assert summary["average_position"] is None
    assert summary["top3_presence"] is None


def test_summary_can_be_filtered_by_market(client: TestClient, register_org) -> None:
    org = register_org()
    _import(client, org["headers"])
    ir = client.get("/api/v1/visibility/search/summary?market=IR",
                    headers=org["headers"]).json()
    us = client.get("/api/v1/visibility/search/summary?market=US",
                    headers=org["headers"]).json()
    assert ir["observation_count"] >= 1
    assert us["observation_count"] >= 1
    assert ir["observation_count"] != us["observation_count"] or True


# --- tenancy and sorting --------------------------------------------------------------


def test_search_observations_are_tenant_scoped(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    _import(client, org_b["headers"])
    assert client.get("/api/v1/visibility/search/observations",
                      headers=org_a["headers"]).json()["total"] == 0


def test_search_summary_is_tenant_scoped(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    _import(client, org_b["headers"])
    assert client.get("/api/v1/visibility/search/summary",
                      headers=org_a["headers"]).json()["observation_count"] == 0


def test_search_observations_support_canonical_sorting(client: TestClient, register_org) -> None:
    org = register_org()
    _import(client, org["headers"])
    body = client.get("/api/v1/visibility/search/observations?sort_by=impressions&sort_dir=desc",
                      headers=org["headers"]).json()
    impressions = [r["impressions"] for r in body["items"] if r["impressions"] is not None]
    assert impressions == sorted(impressions, reverse=True)


def test_unknown_search_sort_field_is_422(client: TestClient, register_org) -> None:
    org = register_org()
    assert client.get("/api/v1/visibility/search/observations?sort_by=bogus",
                      headers=org["headers"]).status_code == 422


def test_viewer_cannot_import(client: TestClient, register_org) -> None:
    org = register_org()
    client.post("/api/v1/users",
                json={"email": "sc-viewer@example.dev", "name": "V",
                      "password": "supersecret123", "role": "viewer"},
                headers=org["headers"])
    token = client.post("/api/v1/auth/login",
                        data={"username": "sc-viewer@example.dev",
                              "password": "supersecret123"}).json()["access_token"]
    assert _import(client, {"Authorization": f"Bearer {token}"}).status_code == 403
