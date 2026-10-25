"""
Sorting regression tests (§51, ADR-056).

The properties under test are the ones that make sorting trustworthy
rather than merely present:

  - it actually reorders results (ascending AND descending)
  - an invalid field is REFUSED, never silently ignored
  - the permitted set is explicit and discoverable from the error
  - pagination stays deterministic under a non-unique sort column
  - tenant isolation is unaffected
  - every collection route accepts it, or is explicitly excluded
"""

import inspect

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.schemas.common import SORTABLE_FIELDS, SortDirection, apply_sort


def _products(client: TestClient, headers: dict, names: list[str]) -> None:
    for i, n in enumerate(names):
        client.post("/api/v1/products", json={"name": n, "slug": f"s{i}"}, headers=headers)


# --- it actually sorts, both directions -------------------------------------


def test_ascending_sort_reorders_results(client: TestClient, register_org) -> None:
    org = register_org()
    _products(client, org["headers"], ["Cherry", "Apple", "Banana"])

    body = client.get("/api/v1/products?sort_by=name&sort_dir=asc", headers=org["headers"]).json()
    assert [p["name"] for p in body["items"]] == ["Apple", "Banana", "Cherry"]


def test_descending_sort_reorders_results(client: TestClient, register_org) -> None:
    org = register_org()
    _products(client, org["headers"], ["Cherry", "Apple", "Banana"])

    body = client.get("/api/v1/products?sort_by=name&sort_dir=desc", headers=org["headers"]).json()
    assert [p["name"] for p in body["items"]] == ["Cherry", "Banana", "Apple"]


def test_asc_and_desc_are_genuinely_opposite(client: TestClient, register_org) -> None:
    """Guards against a direction parameter that is accepted and ignored."""
    org = register_org()
    _products(client, org["headers"], ["Delta", "Alpha", "Charlie", "Bravo"])

    asc = [p["name"] for p in client.get(
        "/api/v1/products?sort_by=name&sort_dir=asc", headers=org["headers"]).json()["items"]]
    desc = [p["name"] for p in client.get(
        "/api/v1/products?sort_by=name&sort_dir=desc", headers=org["headers"]).json()["items"]]
    assert asc == list(reversed(desc))
    assert asc != desc


def test_default_ordering_is_unchanged_when_no_sort_is_requested(
    client: TestClient, register_org
) -> None:
    """Adding sorting must not have altered existing behaviour."""
    org = register_org()
    _products(client, org["headers"], ["First", "Second", "Third"])

    body = client.get("/api/v1/products", headers=org["headers"]).json()
    assert [p["name"] for p in body["items"]] == ["Third", "Second", "First"]  # created_at DESC


# --- invalid input is refused, never silently ignored ---------------------------


def test_unknown_sort_field_returns_422(client: TestClient, register_org) -> None:
    org = register_org()
    _products(client, org["headers"], ["A"])

    response = client.get("/api/v1/products?sort_by=nonexistent", headers=org["headers"])
    assert response.status_code == 422


def test_422_names_the_permitted_fields(client: TestClient, register_org) -> None:
    """A refusal a consumer cannot act on is barely better than silence.

    Note the response shape: this project returns §51's consistent error
    envelope (`{"error": {...}, "request_id": ...}`), not FastAPI's raw
    `detail`. The first draft of this test asserted on `detail` and failed —
    the envelope was right and the test was wrong, which is worth recording
    because it confirms the §51 envelope is genuinely applied to sorting
    errors and not bypassed."""
    org = register_org()
    _products(client, org["headers"], ["A"])

    body = client.get("/api/v1/products?sort_by=bogus", headers=org["headers"]).json()
    assert "error" in body and "request_id" in body, "sorting errors must use the §51 envelope"
    message = body["error"]["message"]
    assert "bogus" in message
    for expected in ("name", "created_at", "status"):
        assert expected in message


def test_no_silent_fallback_on_invalid_field(client: TestClient, register_org) -> None:
    """THE anti-silent-fallback test: an invalid sort must NOT return a
    successful, differently-ordered page. A consumer paginating with a
    typo'd field would otherwise get inconsistent ordering and never learn
    why."""
    org = register_org()
    _products(client, org["headers"], ["Cherry", "Apple", "Banana"])

    response = client.get("/api/v1/products?sort_by=naem", headers=org["headers"])  # typo
    assert response.status_code == 422
    body = response.json()
    assert "items" not in body, "an invalid sort must not return a successful page"
    assert body["error"]["code"]


def test_sql_injection_in_sort_by_is_refused(client: TestClient, register_org) -> None:
    org = register_org()
    _products(client, org["headers"], ["A"])

    for payload in ("name; DROP TABLE products", "name)--", "1=1", "created_at,name"):
        response = client.get(f"/api/v1/products?sort_by={payload}", headers=org["headers"])
        assert response.status_code == 422, f"{payload!r} must be refused"


def test_non_public_columns_are_not_sortable(client: TestClient, register_org) -> None:
    """The allow-list maps PUBLIC names to attributes; internal columns are
    absent from the contract even though the column exists."""
    org = register_org()
    _products(client, org["headers"], ["A"])

    for internal in ("organization_id", "id", "knowledge_object_id"):
        assert client.get(
            f"/api/v1/products?sort_by={internal}", headers=org["headers"]
        ).status_code == 422


def test_credential_secret_hash_is_not_sortable(client: TestClient, register_org) -> None:
    """Sorting by a secret hash would leak ordering information about
    secrets. It is absent from the allow-list."""
    assert "secret_hash" not in SORTABLE_FIELDS["InstallationCredential"]


# --- deterministic pagination ------------------------------------------------------


def test_pagination_is_deterministic_under_a_non_unique_sort_column(
    client: TestClient, register_org
) -> None:
    """All these products share a status, so sorting by it leaves ties.
    Without a stable tiebreak, Postgres may order ties differently per
    query and page 2 could repeat or skip rows from page 1."""
    org = register_org()
    _products(client, org["headers"], [f"P{i:02d}" for i in range(12)])

    page1 = client.get(
        "/api/v1/products?sort_by=status&limit=5&offset=0", headers=org["headers"]
    ).json()["items"]
    page2 = client.get(
        "/api/v1/products?sort_by=status&limit=5&offset=5", headers=org["headers"]
    ).json()["items"]
    page3 = client.get(
        "/api/v1/products?sort_by=status&limit=5&offset=10", headers=org["headers"]
    ).json()["items"]

    ids = [p["id"] for p in page1 + page2 + page3]
    assert len(ids) == len(set(ids)), "paging over a tied sort column repeated a row"
    assert len(ids) == 12, "paging over a tied sort column skipped a row"


def test_repeated_identical_requests_return_identical_order(
    client: TestClient, register_org
) -> None:
    org = register_org()
    _products(client, org["headers"], [f"P{i:02d}" for i in range(8)])

    runs = [
        [p["id"] for p in client.get(
            "/api/v1/products?sort_by=status", headers=org["headers"]).json()["items"]]
        for _ in range(3)
    ]
    assert runs[0] == runs[1] == runs[2]


# --- tenant isolation survives sorting ----------------------------------------------


def test_sorting_does_not_leak_another_orgs_rows(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    _products(client, org_a["headers"], ["AAA"])
    _products(client, org_b["headers"], ["ZZZ"])

    for direction in ("asc", "desc"):
        body = client.get(
            f"/api/v1/products?sort_by=name&sort_dir={direction}", headers=org_a["headers"]
        ).json()
        assert [p["name"] for p in body["items"]] == ["AAA"]


def test_sorting_respects_filters(client: TestClient, register_org) -> None:
    org = register_org()
    client.post("/api/v1/products", json={"name": "Sweet", "slug": "s1", "category": "sweeteners"},
                headers=org["headers"])
    client.post("/api/v1/products", json={"name": "Herb", "slug": "s2", "category": "herbs"},
                headers=org["headers"])

    body = client.get(
        "/api/v1/products?category=sweeteners&sort_by=name&sort_dir=asc", headers=org["headers"]
    ).json()
    assert [p["name"] for p in body["items"]] == ["Sweet"]


# --- sorting works across multiple domains, not just products -------------------------


def test_sorting_works_on_queries(client: TestClient, register_org) -> None:
    import json as _json

    org = register_org()
    client.post("/api/v1/queries/import",
                data={"source": "manual",
                      "rows_json": _json.dumps([{"query": "zebra"}, {"query": "apple"}])},
                headers=org["headers"])

    body = client.get("/api/v1/queries?sort_by=query&sort_dir=asc", headers=org["headers"]).json()
    assert [q["query"] for q in body["items"]] == ["apple", "zebra"]


def test_sorting_works_on_sites(client: TestClient, register_org) -> None:
    org = register_org()
    for d in ("zulu.example", "alpha.example"):
        client.post("/api/v1/sites", json={"name": d, "domain": d}, headers=org["headers"])

    body = client.get("/api/v1/sites?sort_by=domain&sort_dir=asc", headers=org["headers"]).json()
    domains = [s["domain"] for s in body["items"]]
    assert domains == sorted(domains)


def test_invalid_sort_is_refused_on_a_second_domain_too(client: TestClient, register_org) -> None:
    """Confirms the canonical implementation is genuinely shared, not
    re-implemented per endpoint."""
    org = register_org()
    assert client.get("/api/v1/sites?sort_by=bogus", headers=org["headers"]).status_code == 422
    assert client.get("/api/v1/knowledge?sort_by=bogus", headers=org["headers"]).status_code == 422
    assert client.get("/api/v1/sources?sort_by=bogus", headers=org["headers"]).status_code == 422


# --- coverage: every collection route is sorted or explicitly excluded ------------------

_EXCLUDED = {
    # Relevance-ranked: an arbitrary sort would discard the ranking that is
    # the entire point of a search endpoint.
    "/api/v1/knowledge/search",
    # Similarity-ranked: members are ordered by score against the cluster
    # representative. The order IS the information.
    "/api/v1/query-clusters/{cluster_id}/members",
    # Aggregate ranking (GROUP BY canonical query, ordered by demand count):
    # the rows are not a model apply_sort can order, and demand volume IS the
    # information; `ascending` flips it (the owner asked for both
    # directions). Documented in the final existing-owner closure pass,
    # after the other six telemetry routes were moved onto SortParams.
    "/api/v1/telemetry/search-demand/terms",
    # Reading order of one document (ADR-122): elements are returned in the order they are read on the page.
    # Any other order would scramble the text the list exists to show.
    "/api/v1/documents/{document_id}/elements",
    # Units of one synthesis run in plan order (ADR-124): the coverage ledger is read top to bottom against the
    # plan, so the order IS the information.
    "/api/v1/synthesis/runs/{run_id}/units",
}


def test_every_collection_route_supports_sorting_or_is_explicitly_excluded() -> None:
    paged = [
        r for r in app.routes
        if hasattr(r, "response_model") and r.response_model and "Page[" in str(r.response_model)
    ]
    assert len(paged) >= 40, "route inventory shrank unexpectedly"

    missing = [
        r.path for r in paged
        if "sort" not in inspect.signature(r.endpoint).parameters and r.path not in _EXCLUDED
    ]
    assert missing == [], f"collection routes without sorting and without justification: {missing}"


def test_the_exclusions_are_exactly_the_documented_ones() -> None:
    paged = [
        r for r in app.routes
        if hasattr(r, "response_model") and r.response_model and "Page[" in str(r.response_model)
    ]
    actual_excluded = {
        r.path for r in paged if "sort" not in inspect.signature(r.endpoint).parameters
    }
    assert actual_excluded == _EXCLUDED, (
        "the set of unsorted routes drifted from the documented exclusions"
    )


def test_excluded_routes_are_actually_callable(client: TestClient, register_org) -> None:
    """REGRESSION (P11-sort-rollout).

    The mechanical rollout excluded two routes from RECEIVING a `sort`
    parameter, but a second pass added `sort=sort` to their service call
    anyway — so both raised `NameError: name 'sort' is not defined` on
    every request.

    `test_the_exclusions_are_exactly_the_documented_ones` did not catch it,
    because it inspects the SIGNATURE and the signature was correct. The
    body was not. That is the R1 class again: structure verified, behaviour
    not. This test calls the routes."""
    org = register_org()
    client.post("/api/v1/knowledge", json={"canonical_name": "Taranjabin", "object_type": "plant"},
                headers=org["headers"])

    search = client.get("/api/v1/knowledge/search?q=Taran", headers=org["headers"])
    assert search.status_code == 200, search.text
    assert search.json()["total"] >= 1

    clusters = client.get("/api/v1/query-clusters", headers=org["headers"]).json()
    assert clusters["total"] == 0  # none created, but the route must work

    # A concrete cluster id exercises the members route itself.
    import uuid as _uuid
    members = client.get(
        f"/api/v1/query-clusters/{_uuid.uuid4()}/members", headers=org["headers"]
    )
    assert members.status_code == 404, "must be a clean 404, not a NameError 500"


def test_every_collection_route_actually_responds(client: TestClient, register_org) -> None:
    """Broader guard of the same class: every collection route must return
    a real HTTP status, not a 500 from a wiring mistake. Path params are
    filled with a random UUID, so 404 is an expected and acceptable
    outcome — a 500 is not."""
    import inspect as _inspect
    import uuid as _uuid

    org = register_org()
    failures = []
    for route in app.routes:
        if not (hasattr(route, "response_model") and route.response_model
                and "Page[" in str(route.response_model)):
            continue
        if "GET" not in getattr(route, "methods", set()):
            continue
        path = route.path
        for name in _inspect.signature(route.endpoint).parameters:
            if "{" + name + "}" in path:
                path = path.replace("{" + name + "}", str(_uuid.uuid4()))
        if "{" in path:
            continue  # unresolvable param; skipped rather than guessed
        # `q` is required on the search route.
        url = path + ("?q=x" if path.endswith("/search") else "")
        response = client.get(url, headers=org["headers"])
        if response.status_code >= 500:
            failures.append(f"{path} -> {response.status_code}")
    assert failures == [], f"collection routes returning 5xx: {failures}"


def test_sort_wiring_is_complete_in_both_directions() -> None:
    """REGRESSION (P11-sort-rollout), generalised.

    The rollout produced TWO distinct wiring bugs that behaviour tests only
    caught by accident:

      1. routes that PASS `sort=sort` without accepting a `sort` parameter
         -> NameError 500 on every request
      2. routes that ACCEPT `sort` and never pass it on
         -> the parameter is silently ignored, which is exactly the
            silent-fallback failure this whole feature forbids. A client
            sends ?sort_by=name, gets 200, and gets default ordering.

    The second is worse than the first: a 500 is loud, a silently ignored
    sort is not. Neither was caught by the signature-level coverage test.
    This asserts both directions statically, so a future mechanical edit
    cannot reintroduce either."""
    import ast
    import pathlib

    accept_but_drop, pass_but_no_param = [], []
    for path in sorted(pathlib.Path("app/api/v1").glob("*.py")):
        tree = ast.parse(path.read_text())
        for fn in [n for n in ast.walk(tree)
                   if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
            params = {a.arg for a in fn.args.args} | {a.arg for a in fn.args.kwonlyargs}
            # `sort` counts as used whether it is forwarded as a keyword
            # (sort=sort) or passed positionally to apply_sort(...). The
            # first version of this check only looked for keywords and
            # flagged every route that called apply_sort directly - a false
            # positive that appeared the moment P12-18 routes were added.
            passes = any(
                (isinstance(n, ast.keyword) and n.arg == "sort")
                or (isinstance(n, ast.Name) and n.id == "sort"
                    and not isinstance(getattr(n, "ctx", None), ast.Store))
                for n in ast.walk(fn)
                if not (isinstance(n, ast.arg))
            )
            if "sort" in params and not passes:
                accept_but_drop.append(f"{path.name}::{fn.name}")
            if passes and "sort" not in params:
                pass_but_no_param.append(f"{path.name}::{fn.name}")

    assert accept_but_drop == [], (
        f"routes accept `sort` but silently ignore it: {accept_but_drop}"
    )
    assert pass_but_no_param == [], (
        f"routes pass `sort` without accepting it (NameError at runtime): {pass_but_no_param}"
    )


def test_sortable_registry_has_no_empty_allow_lists() -> None:
    for model, fields in SORTABLE_FIELDS.items():
        assert fields, f"{model} has an empty sort allow-list, which would refuse every request"
        assert "created_at" in fields or "chunk_index" in fields, (
            f"{model} has no stable default sort field"
        )


def test_apply_sort_rejects_unknown_field_at_the_function_level() -> None:
    """Unit-level: the canonical function refuses, independent of routing."""
    from fastapi import HTTPException
    from sqlalchemy import select

    from app.models.product import Product
    from app.schemas.common import SortParams

    with pytest.raises(HTTPException) as exc:
        apply_sort(select(Product), Product, SortParams(sort_by="nope"), "created_at")
    assert exc.value.status_code == 422


def test_apply_sort_appends_a_stable_tiebreak() -> None:
    """The determinism guarantee, asserted on the generated SQL."""
    from sqlalchemy import select

    from app.models.product import Product
    from app.schemas.common import SortParams

    stmt = apply_sort(select(Product), Product, SortParams(sort_by="status"), "created_at")
    sql = str(stmt).lower()
    assert "order by" in sql
    assert "products.id" in sql.split("order by")[1], "no stable tiebreak on id"


def test_new_lists_sort_and_refuse_unknown_fields(client: TestClient, register_org) -> None:
    """Synthesis runs and workspace commands joined the sortable lists in the 2026-10-14 audit."""
    org = register_org()
    for path in ("/api/v1/synthesis/runs", "/api/v1/workspace/commands"):
        assert client.get(f"{path}?sort_by=created_at&sort_dir=asc", headers=org["headers"]).status_code == 200
        bad = client.get(f"{path}?sort_by=password_hash", headers=org["headers"])
        assert bad.status_code == 422 and "Allowed values" in bad.text


@pytest.mark.parametrize("model", sorted(SORTABLE_FIELDS))
def test_every_allow_listed_sort_column_exists_on_its_model(model: str) -> None:
    """A SORTABLE_FIELDS name that is not a mapped column passes validation and then crashes
    apply_sort (500, not 422). Source once listed `published_at`; its column is `publication_date`.
    Checked against the mapper's column attributes, the names apply_sort's getattr resolves:
    relationships, properties and hybrids are rejected, and an attribute like Source.metadata_
    (DB column "metadata") is matched by its attribute name, as getattr needs."""
    from sqlalchemy import inspect

    from app.db.base import Base

    models = {m.class_.__name__: m.class_ for m in Base.registry.mappers}
    assert model in models, f"SORTABLE_FIELDS key {model!r} (common.py) does not match any imported model class"
    columns = {attr.key for attr in inspect(models[model]).column_attrs}
    bad = [f"{model}.{column!r} (sort_by={key!r}, allow-list SORTABLE_FIELDS[{model!r}] in common.py) "
           f"— not a mapped column attribute" for key, column in SORTABLE_FIELDS[model].items() if column not in columns]
    assert len(bad) == 0, "; ".join(bad)


def test_source_sort_fields_work_and_published_at_is_refused(client: TestClient, register_org) -> None:
    org = register_org()
    for title, published in (("B", "2026-02-01"), ("A", "2026-01-01")):
        client.post("/api/v1/sources", json={"source_type": "website", "title": title, "publication_date": published},
                    headers=org["headers"])
    for field in ("publication_date", "created_at", "updated_at", "title"):
        assert client.get(f"/api/v1/sources?sort_by={field}", headers=org["headers"]).status_code == 200, field
    body = client.get("/api/v1/sources?sort_by=publication_date&sort_dir=asc", headers=org["headers"]).json()
    assert [s["title"] for s in body["items"]] == ["A", "B"]
    bad = client.get("/api/v1/sources?sort_by=published_at", headers=org["headers"])
    assert bad.status_code == 422 and "publication_date" in bad.text
