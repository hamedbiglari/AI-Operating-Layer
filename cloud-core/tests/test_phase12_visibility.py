"""
Phase 12 — AI Visibility.

The adversarial question throughout: **can this system be made to state
something it does not know?** Three ways it could, each tested:

1. a not-checked signal counted as a negative finding
2. an observation presented as a measure of overall visibility
3. a paid probe running with no budget left
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.models.enums import SignalPresence
from app.services import visibility_service


def _obs(client: TestClient, headers: dict, **kw) -> dict:
    payload = {
        "platform": "chatgpt", "test_type": "brand_query",
        "prompt": "What is taranjabin?",
        "tested_at": datetime.now(timezone.utc).isoformat(),
    }
    payload.update(kw)
    return client.post("/api/v1/visibility/observations", json=payload, headers=headers)


def _budget(client: TestClient, headers: dict, limit: float) -> dict:
    return client.put("/api/v1/visibility/budget",
                      json={"period_limit": limit, "currency": "USD"}, headers=headers).json()


# --- tri-state: NOT_CHECKED is not ABSENT --------------------------------------


def test_signals_default_to_not_checked(client: TestClient, register_org) -> None:
    """A caller that did not examine a signal says NOTHING about it. The
    default must not be 'absent', which would be a fabricated finding."""
    org = register_org()
    body = _obs(client, org["headers"]).json()
    for field in ("mentioned", "cited", "recommended", "product_present", "url_present"):
        assert body[field] == "not_checked", f"{field} must default to not_checked"


def test_absent_and_not_checked_are_distinct_values(client: TestClient, register_org) -> None:
    org = register_org()
    checked = _obs(client, org["headers"], mentioned="absent").json()
    unchecked = _obs(client, org["headers"], prompt="other").json()
    assert checked["mentioned"] == "absent"
    assert unchecked["mentioned"] == "not_checked"
    assert checked["mentioned"] != unchecked["mentioned"]


def test_summary_never_folds_not_checked_into_a_denominator(
    client: TestClient, register_org
) -> None:
    """THE central honesty test.

    3 observations: one PRESENT, one ABSENT, one NOT_CHECKED. The honest
    denominator for `mentioned` is 2, not 3 — the third observation never
    looked. A naive implementation reporting 1/3 = 33% would be inventing
    a number."""
    org = register_org()
    _obs(client, org["headers"], prompt="a", mentioned="present")
    _obs(client, org["headers"], prompt="b", mentioned="absent")
    _obs(client, org["headers"], prompt="c")  # not_checked

    summary = client.get("/api/v1/visibility/summary", headers=org["headers"]).json()
    m = summary["signals"]["mentioned"]
    assert m["present"] == 1
    assert m["absent"] == 1
    assert m["not_checked"] == 1
    assert m["checked"] == 2, "checked must exclude not_checked observations"
    assert summary["observation_count"] == 3
    assert m["checked"] != summary["observation_count"]


def test_summary_returns_no_score_percentage_or_ranking(
    client: TestClient, register_org
) -> None:
    """§31 distinguishes seven signals precisely so they are not collapsed.
    A composite score would undo that."""
    org = register_org()
    _obs(client, org["headers"], mentioned="present")

    text = client.get("/api/v1/visibility/summary", headers=org["headers"]).text
    for forbidden in ("visibility_score", "score", "percentage", "percent", "rating", "rank"):
        assert forbidden not in text.lower(), f"'{forbidden}' must not appear in a visibility summary"


def test_summary_states_what_it_does_not_cover(client: TestClient, register_org) -> None:
    org = register_org()
    _obs(client, org["headers"], mentioned="present")

    caveats = " ".join(
        client.get("/api/v1/visibility/summary", headers=org["headers"]).json()["caveats"]
    ).lower()
    assert "not a measure of overall visibility" in caveats


def test_empty_summary_says_absence_is_not_evidence(client: TestClient, register_org) -> None:
    org = register_org()
    summary = client.get("/api/v1/visibility/summary", headers=org["headers"]).json()
    assert summary["observation_count"] == 0
    assert "not evidence of absence" in " ".join(summary["caveats"]).lower()


def test_summary_flags_when_a_signal_was_never_examined(client: TestClient, register_org) -> None:
    org = register_org()
    _obs(client, org["headers"], mentioned="present")  # cited never checked

    caveats = " ".join(
        client.get("/api/v1/visibility/summary", headers=org["headers"]).json()["caveats"]
    )
    assert "cited" in caveats
    assert "either way" in caveats.lower()


def test_summary_flags_manual_only_coverage(client: TestClient, register_org) -> None:
    """All-manual data reflects what a human happened to check, not a
    systematic sample. A reader must be told."""
    org = register_org()
    _obs(client, org["headers"], mentioned="present", collection_method="manual_paste")

    caveats = " ".join(
        client.get("/api/v1/visibility/summary", headers=org["headers"]).json()["caveats"]
    ).lower()
    assert "entered manually" in caveats


# --- click and purchase are not representable -----------------------------------


def test_click_and_purchase_cannot_be_recorded(client: TestClient, register_org) -> None:
    """§31 names seven signals; this system can observe five. Click happens
    in the user's browser and purchase on the merchant's site — neither is
    visible from a platform response, so there is no column to write a
    guess into (ADR-062)."""
    org = register_org()
    response = _obs(client, org["headers"], clicked="present", purchased="present")
    assert response.status_code == 201
    body = response.json()
    assert "clicked" not in body
    assert "purchased" not in body
    assert "click" not in body
    assert "purchase" not in body


def test_visibility_model_has_no_click_or_purchase_column() -> None:
    from app.models.visibility import VisibilityTest

    columns = {c.name for c in VisibilityTest.__table__.columns}
    for forbidden in ("clicked", "click_count", "purchased", "purchase_count", "conversions"):
        assert forbidden not in columns


# --- budget is checked BEFORE the probe -------------------------------------------


def test_missing_budget_defaults_to_zero_not_unlimited(client: TestClient, register_org) -> None:
    """'Not configured' and 'unlimited' must never be the same state."""
    org = register_org()
    budget = client.get("/api/v1/visibility/budget", headers=org["headers"]).json()
    assert budget["period_limit"] == 0
    assert budget["period_spent"] == 0


def test_paid_observation_is_refused_with_no_budget(client: TestClient, register_org) -> None:
    org = register_org()
    response = _obs(client, org["headers"], estimated_cost=0.05)
    assert response.status_code == 402, "a paid probe with no budget must be refused"


def test_refused_probe_records_nothing(client: TestClient, register_org) -> None:
    """A budget refusal must not leave a half-written row behind."""
    org = register_org()
    _obs(client, org["headers"], estimated_cost=0.05)

    listing = client.get("/api/v1/visibility/observations", headers=org["headers"]).json()
    assert listing["total"] == 0


def test_free_observation_is_allowed_with_no_budget(client: TestClient, register_org) -> None:
    """A manually pasted observation costs nothing and must not be blocked
    by a budget intended for paid API probes."""
    org = register_org()
    assert _obs(client, org["headers"]).status_code == 201


def test_spend_accumulates_and_then_blocks(client: TestClient, register_org) -> None:
    org = register_org()
    _budget(client, org["headers"], 0.10)

    assert _obs(client, org["headers"], prompt="a", estimated_cost=0.04).status_code == 201
    assert _obs(client, org["headers"], prompt="b", estimated_cost=0.04).status_code == 201
    # 0.08 spent; a third 0.04 would reach 0.12 > 0.10
    assert _obs(client, org["headers"], prompt="c", estimated_cost=0.04).status_code == 402

    budget = client.get("/api/v1/visibility/budget", headers=org["headers"]).json()
    assert abs(budget["period_spent"] - 0.08) < 0.0001


def test_budget_refusal_is_402_not_403(client: TestClient, register_org) -> None:
    """The caller is authorised; there is simply no budget. A client must be
    able to tell those apart."""
    org = register_org()
    response = _obs(client, org["headers"], estimated_cost=1.0)
    assert response.status_code == 402
    assert response.status_code != 403


# --- provenance and time integrity ---------------------------------------------------


def test_tested_at_is_preserved_not_overwritten(client: TestClient, register_org) -> None:
    """An observation pasted from yesterday happened yesterday. Stamping it
    with import time would corrupt every time series silently."""
    org = register_org()
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).replace(microsecond=0)

    body = _obs(client, org["headers"], tested_at=yesterday.isoformat()).json()
    assert body["tested_at"].startswith(yesterday.strftime("%Y-%m-%dT%H:%M"))


def test_collection_method_is_recorded(client: TestClient, register_org) -> None:
    org = register_org()
    body = _obs(client, org["headers"], collection_method="platform_api").json()
    assert body["collection_method"] == "platform_api"


def test_platform_model_is_null_when_unknown_not_guessed(client: TestClient, register_org) -> None:
    org = register_org()
    assert _obs(client, org["headers"]).json()["platform_model"] is None


# --- reuse, not duplication ------------------------------------------------------------


def test_observation_references_phase6_query_without_duplicating_it(
    client: TestClient, register_org
) -> None:
    import json as _json

    org = register_org()
    imported = client.post(
        "/api/v1/queries/import",
        data={"source": "manual", "rows_json": _json.dumps([{"query": "قیمت ترنجبین"}])},
        headers=org["headers"],
    ).json()
    query_id = imported["items"][0]["query_id"]

    body = _obs(client, org["headers"], query_id=query_id).json()
    assert body["query_id"] == query_id
    # The observation stores a reference, not a copy of the query text.
    assert "query" not in body or body.get("query") is None


# --- tenant isolation --------------------------------------------------------------------


def test_cannot_read_another_orgs_observation(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    obs_b = _obs(client, org_b["headers"]).json()
    assert client.get(
        f"/api/v1/visibility/observations/{obs_b['id']}", headers=org_a["headers"]
    ).status_code == 404


def test_observation_list_is_tenant_scoped(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    _obs(client, org_a["headers"], prompt="A only")
    _obs(client, org_b["headers"], prompt="B only")

    listing = client.get("/api/v1/visibility/observations", headers=org_a["headers"]).json()
    assert listing["total"] == 1
    assert listing["items"][0]["prompt"] == "A only"


def test_summary_is_tenant_scoped(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    for _ in range(3):
        _obs(client, org_b["headers"], mentioned="present")

    assert client.get("/api/v1/visibility/summary", headers=org_a["headers"]).json()["observation_count"] == 0


def test_budget_is_tenant_scoped(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    _budget(client, org_b["headers"], 5.0)

    assert client.get("/api/v1/visibility/budget", headers=org_a["headers"]).json()["period_limit"] == 0


def test_cannot_attach_another_orgs_query(client: TestClient, register_org) -> None:
    """Composite tenant FK at the database level (ADR-037)."""
    import json as _json

    org_a, org_b = register_org(), register_org()
    imported = client.post(
        "/api/v1/queries/import",
        data={"source": "manual", "rows_json": _json.dumps([{"query": "b query"}])},
        headers=org_b["headers"],
    ).json()
    query_id_b = imported["items"][0]["query_id"]

    response = _obs(client, org_a["headers"], query_id=query_id_b)
    assert response.status_code >= 400, "cross-tenant query reference must be refused"


def test_viewer_cannot_record_observations(client: TestClient, register_org) -> None:
    org = register_org()
    client.post("/api/v1/users",
                json={"email": "vis-viewer@example.dev", "name": "V",
                      "password": "supersecret123", "role": "viewer"},
                headers=org["headers"])
    login = client.post("/api/v1/auth/login",
                        data={"username": "vis-viewer@example.dev", "password": "supersecret123"})
    viewer = {"Authorization": f"Bearer {login.json()['access_token']}"}

    assert _obs(client, viewer).status_code == 403


# --- unit-level ---------------------------------------------------------------------------


def test_model_and_server_defaults_are_not_checked(client: TestClient, register_org, db_session) -> None:
    """Exercises the ORM/server default directly, bypassing the API schema.

    Found by mutation testing: flipping the model default from NOT_CHECKED
    to ABSENT passed all 28 tests, because `VisibilityObservationCreate`
    always supplies an explicit value and the column default was never
    reached. That left the real database default unguarded — a direct
    service call or a raw INSERT would have silently produced fabricated
    'absent' findings.

    This inserts without specifying any signal, so the column default is
    what is actually under test."""
    import uuid as _uuid
    from datetime import datetime as _dt, timezone as _tz

    from app.models.visibility import VisibilityTest
    from app.models.enums import VisibilityPlatform, VisibilityTestType

    org = register_org()
    row = VisibilityTest(
        organization_id=_uuid.UUID(org["organization"]["id"]),
        platform=VisibilityPlatform.CHATGPT,
        test_type=VisibilityTestType.BRAND_QUERY,
        prompt="default probe",
        tested_at=_dt.now(_tz.utc),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    for field in visibility_service.SIGNAL_FIELDS:
        assert getattr(row, field) == SignalPresence.NOT_CHECKED, (
            f"{field} column default must be NOT_CHECKED; ABSENT would fabricate a finding"
        )


def test_server_default_in_the_database_is_not_checked(db_session) -> None:
    """Belt and braces: asserts the DDL default itself, so a migration that
    changed it would fail here even if the ORM default were correct."""
    from sqlalchemy import text

    rows = db_session.execute(text(
        "SELECT column_name, column_default FROM information_schema.columns "
        "WHERE table_name = 'visibility_tests' AND column_name IN "
        "('mentioned','cited','recommended','product_present','url_present')"
    )).all()
    assert len(rows) == 5
    for name, default in rows:
        assert default is not None and "not_checked" in default, (
            f"{name} server default is {default!r}, expected not_checked"
        )


def test_period_key_is_calendar_month() -> None:
    at = datetime(2026, 9, 15, tzinfo=timezone.utc)
    assert visibility_service.current_period_key(at) == "2026-09"


def test_signal_fields_are_exactly_the_five_spec_columns() -> None:
    assert visibility_service.SIGNAL_FIELDS == (
        "mentioned", "cited", "recommended", "product_present", "url_present"
    )
    assert "clicked" not in visibility_service.SIGNAL_FIELDS
    assert "purchased" not in visibility_service.SIGNAL_FIELDS
