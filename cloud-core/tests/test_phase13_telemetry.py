"""
Phase 13 — telemetry ingestion, rollup, retention, reporting.

WHAT THESE TESTS ARE FOR

Not "the endpoint returns 202". The properties that, if broken, would make
the merchant's dashboard quietly wrong:

1. A retried batch does not inflate counts.
2. `dwell_ms = NULL` survives the whole pipeline as "not reported" and is
   never rendered, summed or averaged as 0.
3. A full IP address stops existing at its retention horizon, and the
   truncated form does not.
4. Geolocation is never invented — no adapter country in, no country out.
5. The rollup's `total_views` cannot disagree with its components.
6. Sorting works in both directions, because "least seen" is half the
   requirement and is the half a descending-only implementation silently
   drops.

Every one of these has a corresponding mutation in
`docs/phase13/MUTATION_PLAN.md`.

STATUS OF THIS FILE: written against the Phase 13 implementation, NOT YET
EXECUTED. See PHASE13_REPORT.md §Verification — the container in which
Phase 13 was authored has no FastAPI, no SQLAlchemy, no pytest and no
Postgres, so no result in this project may cite this file as passing until
it has actually been run.
"""

import uuid as uuid_module
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

UTC = timezone.utc

GPTBOT_UA = "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko); compatible; GPTBot/1.2; +https://openai.com/gptbot"
CHATGPT_USER_UA = "Mozilla/5.0 (compatible; ChatGPT-User/1.0; +https://openai.com/bot)"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"
NOVEL_UA = "TotallyNewResearchCrawler/0.1 (+https://example.invalid/bot)"


def _event(**kw) -> dict:
    body = {
        "event_key": uuid_module.uuid4().hex,
        "occurred_at": datetime.now(UTC).isoformat(),
        "path": "/product/taranjabin",
        "user_agent": BROWSER_UA,
    }
    body.update(kw)
    return body


def _ingest(client: TestClient, adapter_headers: dict, events: list[dict]):
    return client.post(
        "/api/v1/telemetry/ingest/page-views",
        json={"events": events},
        headers=adapter_headers,
    )


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_redelivered_batch_does_not_double_count(client: TestClient, adapter_credential) -> None:
    """The adapter retries. If a retry inflated the counts there would be
    no way to detect it afterwards — the numbers would simply be wrong and
    plausible."""
    headers = adapter_credential["headers"]
    events = [_event(), _event()]

    first = _ingest(client, headers, events).json()
    assert first["accepted"] == 2
    assert first["duplicates"] == 0

    second = _ingest(client, headers, events).json()
    assert second["accepted"] == 0, "a redelivered batch must write nothing"
    assert second["duplicates"] == 2, "and must report the duplicates, not hide them"


def test_partially_new_batch_accepts_only_the_new_events(
    client: TestClient, adapter_credential
) -> None:
    headers = adapter_credential["headers"]
    old = _event()
    _ingest(client, headers, [old])
    result = _ingest(client, headers, [old, _event()]).json()
    assert result == {
        "accepted": 1,
        "duplicates": 1,
        "rejected": 0,
        "agents_discovered": result["agents_discovered"],
        "errors": [],
    }


# ---------------------------------------------------------------------------
# NULL is not zero
# ---------------------------------------------------------------------------


def test_unreported_dwell_stays_null_end_to_end(
    client: TestClient, adapter_credential, register_org
) -> None:
    """A crawler that fetches once and leaves reports no dwell. Writing 0
    would claim we measured an instantaneous visit, which is a different
    and false statement."""
    org = adapter_credential["org"]
    _ingest(client, adapter_credential["headers"], [_event(user_agent=GPTBOT_UA)])

    page = client.get("/api/v1/telemetry/page-views", headers=org["headers"]).json()
    assert page["items"][0]["dwell_ms"] is None


def test_mean_dwell_is_null_not_zero_when_no_samples(
    client: TestClient, adapter_credential
) -> None:
    org = adapter_credential["org"]
    today = date.today()
    _ingest(client, adapter_credential["headers"], [_event(user_agent=GPTBOT_UA)])
    client.post(
        f"/api/v1/telemetry/content-stats/recompute?view_date={today}",
        headers=org["headers"],
    )
    stats = client.get("/api/v1/telemetry/content-stats", headers=org["headers"]).json()
    row = stats["items"][0]
    assert row["dwell_samples"] == 0
    assert row["mean_dwell_ms"] is None, "no samples means unknown, not zero"


def test_reported_dwell_is_preserved_and_averaged_over_real_samples(
    client: TestClient, adapter_credential
) -> None:
    org = adapter_credential["org"]
    today = date.today()
    _ingest(
        client,
        adapter_credential["headers"],
        [
            _event(dwell_ms=4000, dwell_is_complete=True),
            _event(dwell_ms=6000, dwell_is_complete=True),
            _event(),  # no dwell reported — must not drag the mean toward 0
        ],
    )
    client.post(
        f"/api/v1/telemetry/content-stats/recompute?view_date={today}",
        headers=org["headers"],
    )
    row = client.get("/api/v1/telemetry/content-stats", headers=org["headers"]).json()["items"][0]
    assert row["dwell_samples"] == 2
    assert row["dwell_ms_total"] == 10_000
    assert row["mean_dwell_ms"] == 5000.0, "the unreported view must not be counted as a 0ms sample"


# ---------------------------------------------------------------------------
# Geolocation is never invented
# ---------------------------------------------------------------------------


def test_no_country_in_means_no_country_out(client: TestClient, adapter_credential) -> None:
    """There is no IP-geolocation database and no lookup call. If the
    adapter did not supply a location, every geo field is NULL and the
    method says so."""
    org = adapter_credential["org"]
    _ingest(client, adapter_credential["headers"], [_event(ip_address="203.0.113.44")])
    row = client.get("/api/v1/telemetry/page-views", headers=org["headers"]).json()["items"][0]
    assert row["geo_country"] is None
    assert row["geo_city"] is None
    assert row["geo_method"] == "none"


def test_supplied_geo_is_stored_with_its_method_and_coarse_coordinates(
    client: TestClient, adapter_credential
) -> None:
    org = adapter_credential["org"]
    _ingest(
        client,
        adapter_credential["headers"],
        [
            _event(
                geo_method="edge_header",
                geo_country="ir",
                geo_city="Tehran",
                geo_latitude=35.689198,
                geo_longitude=51.388973,
            )
        ],
    )
    row = client.get("/api/v1/telemetry/page-views", headers=org["headers"]).json()["items"][0]
    assert row["geo_country"] == "IR"
    assert row["geo_method"] == "edge_header"
    # ~1km. Full precision would be a street address.
    assert row["geo_latitude"] == 35.69
    assert row["geo_longitude"] == 51.39


# ---------------------------------------------------------------------------
# IP truncation and retention
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("203.0.113.44", "203.0.113.0/24"),
        ("2001:db8:abcd:1234::1", "2001:db8:abcd::/48"),
        ("not-an-ip", None),
        ("", None),
        (None, None),
    ],
)
def test_truncate_ip(raw, expected) -> None:
    """A malformed address must truncate to None, never fall back to the
    raw string — a fallback that returns the input turns a parse failure
    into an untruncated address, which is the exact failure this function
    exists to prevent."""
    from app.services.telemetry_service import truncate_ip

    assert truncate_ip(raw) == expected


def test_retention_nulls_the_address_and_keeps_the_prefix(
    client: TestClient, adapter_credential, db_session
) -> None:
    from app.models.page_view import PageView
    from app.services import telemetry_service

    org = adapter_credential["org"]
    _ingest(client, adapter_credential["headers"], [_event(ip_address="203.0.113.44")])

    view = db_session.query(PageView).first()
    assert view.ip_address is not None
    assert view.ip_truncated == "203.0.113.0/24"

    # One second BEFORE the horizon: nothing happens.
    just_before = view.ip_retained_until - timedelta(seconds=1)
    assert telemetry_service.enforce_retention(db_session, now=just_before) == 0
    db_session.refresh(view)
    assert view.ip_address is not None, "retention must not fire early"

    # At the horizon: the address goes, the prefix stays.
    assert telemetry_service.enforce_retention(db_session, now=view.ip_retained_until) == 1
    db_session.refresh(view)
    assert view.ip_address is None
    assert view.ip_truncated == "203.0.113.0/24", "analytics must survive the deletion"


def test_full_ip_is_not_in_the_default_report(client: TestClient, adapter_credential) -> None:
    org = adapter_credential["org"]
    _ingest(client, adapter_credential["headers"], [_event(ip_address="203.0.113.44")])
    row = client.get("/api/v1/telemetry/page-views", headers=org["headers"]).json()["items"][0]
    assert "ip_address" not in row, "the default report exposes the /24 only"
    assert row["ip_truncated"] == "203.0.113.0/24"


def test_full_ip_route_requires_owner_or_admin(
    client: TestClient, adapter_credential, viewer_headers
) -> None:
    response = client.get("/api/v1/telemetry/page-views/with-ip", headers=viewer_headers)
    assert response.status_code == 403


# ---------------------------------------------------------------------------
# Rollup integrity
# ---------------------------------------------------------------------------


def test_total_views_equals_the_sum_of_its_parts(client: TestClient, adapter_credential) -> None:
    """`total_views` is denormalised so the sort is cheap. That is only
    safe if it cannot become a seventh independent number."""
    org = adapter_credential["org"]
    today = date.today()
    _ingest(
        client,
        adapter_credential["headers"],
        [
            _event(user_agent=BROWSER_UA),
            _event(user_agent=GPTBOT_UA),
            _event(user_agent=CHATGPT_USER_UA),
            _event(user_agent="Googlebot/2.1"),
            _event(user_agent=NOVEL_UA),
        ],
    )
    client.post(
        f"/api/v1/telemetry/content-stats/recompute?view_date={today}",
        headers=org["headers"],
    )
    row = client.get("/api/v1/telemetry/content-stats", headers=org["headers"]).json()["items"][0]
    parts = (
        row["human_views"] + row["ai_crawler_views"] + row["ai_answer_views"]
        + row["agent_views"] + row["search_views"] + row["unknown_views"]
    )
    assert row["total_views"] == parts == 5


def test_ai_answer_views_are_not_merged_into_crawler_views(
    client: TestClient, adapter_credential
) -> None:
    """The whole product point: "a training crawler took a copy" and "an AI
    quoted this page to a customer" are different facts. A bot/human split
    would collapse them."""
    org = adapter_credential["org"]
    today = date.today()
    _ingest(
        client,
        adapter_credential["headers"],
        [_event(user_agent=GPTBOT_UA), _event(user_agent=CHATGPT_USER_UA)],
    )
    client.post(
        f"/api/v1/telemetry/content-stats/recompute?view_date={today}",
        headers=org["headers"],
    )
    row = client.get("/api/v1/telemetry/content-stats", headers=org["headers"]).json()["items"][0]
    assert row["ai_crawler_views"] == 1
    assert row["ai_answer_views"] == 1


def test_rollup_is_a_full_recompute_not_an_increment(
    client: TestClient, adapter_credential
) -> None:
    """Running it twice must produce the same numbers. An incremental
    counter that drifts is undetectable."""
    org = adapter_credential["org"]
    today = date.today()
    _ingest(client, adapter_credential["headers"], [_event(), _event()])
    url = f"/api/v1/telemetry/content-stats/recompute?view_date={today}"
    client.post(url, headers=org["headers"])
    first = client.get("/api/v1/telemetry/content-stats", headers=org["headers"]).json()["items"][0]
    client.post(url, headers=org["headers"])
    second = client.get("/api/v1/telemetry/content-stats", headers=org["headers"]).json()["items"][0]
    assert first["total_views"] == second["total_views"] == 2


# ---------------------------------------------------------------------------
# Sorting — both directions
# ---------------------------------------------------------------------------


def test_content_stats_sort_ascending_surfaces_least_seen_first(
    client: TestClient, adapter_credential
) -> None:
    """"Least seen" is half the owner's requirement and is the half a
    descending-only implementation silently drops."""
    org = adapter_credential["org"]
    today = date.today()
    events = [_event(path="/popular") for _ in range(3)] + [_event(path="/ignored")]
    _ingest(client, adapter_credential["headers"], events)
    client.post(
        f"/api/v1/telemetry/content-stats/recompute?view_date={today}",
        headers=org["headers"],
    )

    asc = client.get(
        "/api/v1/telemetry/content-stats?sort_by=total_views&sort_dir=asc",
        headers=org["headers"],
    ).json()["items"]
    assert [r["path"] for r in asc] == ["/ignored", "/popular"]

    desc = client.get(
        "/api/v1/telemetry/content-stats?sort_by=total_views&sort_dir=desc",
        headers=org["headers"],
    ).json()["items"]
    assert [r["path"] for r in desc] == ["/popular", "/ignored"]


def test_unknown_sort_field_is_422_naming_the_allowed_values(
    client: TestClient, adapter_credential
) -> None:
    """Silent fallback is worse than an error: a consumer paginating a
    list would get a different order on every page and never learn why
    (ADR-056)."""
    org = adapter_credential["org"]
    response = client.get(
        "/api/v1/telemetry/content-stats?sort_by=ip_address", headers=org["headers"]
    )
    assert response.status_code == 422
    # Error envelope standardised project-wide ({"error": {"code", "message"}});
    # the test predated it (updated in the final existing-owner closure pass).
    assert "total_views" in response.json()["error"]["message"]


def test_ip_address_is_not_sortable(client: TestClient, adapter_credential) -> None:
    """Sorting a report by a visitor's IP is a lookup dressed as an
    ordering. It is deliberately absent from the allow-list."""
    from app.models.page_view import PageView
    from app.schemas.common import sortable_fields

    assert "ip_address" not in sortable_fields(PageView)
    assert "user_agent" not in sortable_fields(PageView)


# ---------------------------------------------------------------------------
# Query-string stripping
# ---------------------------------------------------------------------------


def test_query_string_is_stripped_from_the_stored_path(
    client: TestClient, adapter_credential
) -> None:
    """Defence in depth: the adapter already strips it, but a query string
    routinely carries personal data and one careless caller must not be
    able to put it in the analytics store."""
    org = adapter_credential["org"]
    _ingest(
        client,
        adapter_credential["headers"],
        [_event(path="/search?q=my+medical+condition&token=abc")],
    )
    row = client.get("/api/v1/telemetry/page-views", headers=org["headers"]).json()["items"][0]
    assert row["path"] == "/search"


# ---------------------------------------------------------------------------
# Authentication boundaries
# ---------------------------------------------------------------------------


def test_ingest_rejects_a_user_token(client: TestClient, register_org) -> None:
    """A dashboard session must never be able to write telemetry. The two
    audiences do not share a dependency on purpose."""
    org = register_org()
    response = _ingest(client, org["headers"], [_event()])
    assert response.status_code == 401


def test_ingest_rejects_a_credential_without_the_scope(
    client: TestClient, adapter_credential_no_telemetry
) -> None:
    response = _ingest(client, adapter_credential_no_telemetry["headers"], [_event()])
    assert response.status_code == 403


def test_reports_reject_an_adapter_credential(client: TestClient, adapter_credential) -> None:
    response = client.get(
        "/api/v1/telemetry/page-views", headers=adapter_credential["headers"]
    )
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Agent signature denormalisation on page-view reads
#
# Added during a forensic pass (2026-09-18) that found PageViewRead
# exposed only ai_agent_id (a UUID). A merchant-facing "recent requests"
# table with a raw UUID instead of "GPTBot" is useless, and the fix
# (telemetry_service.signatures_for, called once per response with an
# IN-clause) is exactly the kind of thing an N+1 query regression can
# silently reappear as later, hence the explicit query-count assertion.
# ---------------------------------------------------------------------------


def test_page_view_reads_include_the_agent_signature_not_just_its_id(
    client: TestClient, adapter_credential
) -> None:
    org = adapter_credential["org"]
    _ingest(client, adapter_credential["headers"], [_event(user_agent=GPTBOT_UA)])
    row = client.get("/api/v1/telemetry/page-views", headers=org["headers"]).json()["items"][0]
    assert row["agent_signature"] == "GPTBot"


def test_a_human_view_has_no_agent_signature_not_a_placeholder(
    client: TestClient, adapter_credential
) -> None:
    org = adapter_credential["org"]
    _ingest(client, adapter_credential["headers"], [_event(user_agent=BROWSER_UA)])
    row = client.get("/api/v1/telemetry/page-views", headers=org["headers"]).json()["items"][0]
    assert row["agent_signature"] is None


def test_signatures_for_is_one_query_not_one_per_row(
    client: TestClient, adapter_credential, db_session
) -> None:
    """The N+1 this function exists to prevent. A page of 50 rows sharing
    3 distinct agents must resolve in one batched query, not up to 50."""
    from sqlalchemy import event

    org = adapter_credential["org"]
    _ingest(
        client,
        adapter_credential["headers"],
        [_event(user_agent=GPTBOT_UA) for _ in range(5)]
        + [_event(user_agent=CHATGPT_USER_UA) for _ in range(5)],
    )

    queries = []
    listener = lambda conn, cursor, stmt, *a: queries.append(stmt)
    event.listen(db_session.get_bind(), "before_cursor_execute", listener)
    try:
        from app.services import telemetry_service

        rows, _ = telemetry_service.list_page_views(db_session, organization_id=org["organization"]["id"])
        before = len(queries)
        telemetry_service.signatures_for(
            db_session,
            organization_id=org["organization"]["id"],
            agent_ids=[r.ai_agent_id for r in rows],
        )
        after = len(queries)
    finally:
        event.remove(db_session.get_bind(), "before_cursor_execute", listener)

    assert after - before == 1, "signature lookup must be exactly one batched query"
