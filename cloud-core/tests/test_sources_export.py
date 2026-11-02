"""GET /sources/export.csv (V5-source-export): the Sources list as CSV, same filters, every row, formula-safe."""
import csv
import io

from fastapi.testclient import TestClient


def _source(client: TestClient, headers: dict, title: str, source_type: str = "website") -> dict:
    r = client.post("/api/v1/sources", json={"source_type": source_type, "title": title}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()


def _rows(response) -> list[list[str]]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert response.text.startswith("\ufeff")            # BOM: spreadsheets read UTF-8 (Persian titles)
    return list(csv.reader(io.StringIO(response.text.lstrip("\ufeff"))))


def test_every_source_with_its_counts_and_status(client: TestClient, register_org) -> None:
    org = register_org()
    for i in range(3):
        _source(client, org["headers"], f"Paper {i}", "scientific_paper")
    _source(client, org["headers"], "ترنجبین — مرور")
    r = client.get("/api/v1/sources/export.csv", headers=org["headers"])
    rows = _rows(r)
    assert rows[0] == ["id", "title", "source_type", "status", "documents", "knowledge_objects", "claims", "evidence",
                       "author", "publisher", "publication_date", "url", "doi", "last_activity_at"]
    assert len(rows) == 5 and r.headers["x-total-count"] == "4"
    assert "ترنجبین — مرور" in [row[1] for row in rows[1:]]
    assert all(row[4:8] == ["0", "0", "0", "0"] for row in rows[1:])
    assert 'filename="sources.csv"' in r.headers["content-disposition"]


def test_the_list_filters_apply(client: TestClient, register_org) -> None:
    org = register_org()
    _source(client, org["headers"], "Saffron study", "scientific_paper")
    _source(client, org["headers"], "Garlic page", "website")
    rows = _rows(client.get("/api/v1/sources/export.csv?source_type=website", headers=org["headers"]))
    assert [row[1] for row in rows[1:]] == ["Garlic page"]
    rows = _rows(client.get("/api/v1/sources/export.csv?search=saffron", headers=org["headers"]))
    assert [row[1] for row in rows[1:]] == ["Saffron study"]


def test_a_title_cannot_run_as_a_spreadsheet_formula(client: TestClient, register_org) -> None:
    org = register_org()
    _source(client, org["headers"], '=HYPERLINK("http://evil.test","x")')
    _source(client, org["headers"], "-2+3")
    titles = [row[1] for row in _rows(client.get("/api/v1/sources/export.csv", headers=org["headers"]))[1:]]
    assert sorted(titles) == sorted(["'=HYPERLINK(\"http://evil.test\",\"x\")", "'-2+3"])


def test_only_this_organizations_sources(client: TestClient, register_org) -> None:
    a, b = register_org(), register_org()
    _source(client, a["headers"], "Private")
    assert len(_rows(client.get("/api/v1/sources/export.csv", headers=b["headers"]))) == 1
