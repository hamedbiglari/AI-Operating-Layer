"""
Integration tests for /queries: import (CSV + JSON row batch), the
normalized_query dedup behavior, list/filter, update, and archive.
"""

import io
import json

import openpyxl
from fastapi.testclient import TestClient


def _import_json(client: TestClient, headers: dict, source: str, rows: list[dict]) -> dict:
    response = client.post(
        "/api/v1/queries/import",
        data={"source": source, "rows_json": json.dumps(rows)},
        headers=headers,
    )
    return response


def test_import_json_rows_creates_queries(client: TestClient, register_org) -> None:
    org = register_org()
    response = _import_json(
        client, org["headers"], "manual",
        [{"query": "قیمت ترنجبین"}, {"query": "taranjabin price"}],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created_count"] == 2
    assert body["matched_count"] == 0
    assert len(body["items"]) == 2


def test_reimporting_same_query_appends_provenance_not_duplicate(client: TestClient, register_org) -> None:
    org = register_org()
    first = _import_json(client, org["headers"], "manual", [{"query": "قیمت ترنجبین"}])
    first_id = first.json()["items"][0]["query_id"]

    second = _import_json(client, org["headers"], "csv", [{"query": "  قیمت   ترنجبین  "}])
    assert second.status_code == 201
    body = second.json()
    assert body["created_count"] == 0
    assert body["matched_count"] == 1
    assert body["items"][0]["query_id"] == first_id

    listing = client.get("/api/v1/queries", headers=org["headers"]).json()
    assert listing["total"] == 1


def test_import_csv_file(client: TestClient, register_org) -> None:
    org = register_org()
    csv_content = "query,search_volume,priority\nقیمت ترنجبین,1200,high\ntaranjabin benefits,300,medium\n"
    files = {"file": ("queries.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    response = client.post(
        "/api/v1/queries/import", data={"source": "csv"}, files=files, headers=org["headers"]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created_count"] == 2


def test_import_csv_without_query_column_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    csv_content = "keyword,volume\nقیمت ترنجبین,1200\n"
    files = {"file": ("bad.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    response = client.post(
        "/api/v1/queries/import", data={"source": "csv"}, files=files, headers=org["headers"]
    )
    assert response.status_code == 422


def test_import_excel_file(client: TestClient, register_org) -> None:
    org = register_org()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["query", "search_volume", "priority"])
    sheet.append(["قیمت ترنجبین", 1200, "high"])
    sheet.append(["taranjabin benefits", 300, "medium"])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    files = {
        "file": (
            "queries.xlsx",
            buffer,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    response = client.post(
        "/api/v1/queries/import", data={"source": "excel"}, files=files, headers=org["headers"]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created_count"] == 2

    listing = client.get("/api/v1/queries?source=excel", headers=org["headers"]).json()
    assert listing["total"] == 2
    volumes = {item["search_volume"] for item in listing["items"]}
    assert 1200 in volumes


def test_import_excel_without_query_column_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["keyword", "volume"])
    sheet.append(["قیمت ترنجبین", 1200])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)

    files = {"file": ("bad.xlsx", buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")}
    response = client.post(
        "/api/v1/queries/import", data={"source": "excel"}, files=files, headers=org["headers"]
    )
    assert response.status_code == 422


def test_import_corrupt_excel_file_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    files = {
        "file": (
            "corrupt.xlsx",
            io.BytesIO(b"this is not a real xlsx file"),
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }
    response = client.post(
        "/api/v1/queries/import", data={"source": "excel"}, files=files, headers=org["headers"]
    )
    assert response.status_code == 422


def test_import_excel_dedupes_against_existing_csv_import(client: TestClient, register_org) -> None:
    org = register_org()
    csv_content = "query\nقیمت ترنجبین\n"
    csv_files = {"file": ("q.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    client.post("/api/v1/queries/import", data={"source": "csv"}, files=csv_files, headers=org["headers"])

    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["query"])
    sheet.append(["  قیمت   ترنجبین  "])
    buffer = io.BytesIO()
    workbook.save(buffer)
    buffer.seek(0)
    xlsx_files = {
        "file": ("q.xlsx", buffer, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    }
    response = client.post(
        "/api/v1/queries/import", data={"source": "excel"}, files=xlsx_files, headers=org["headers"]
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["created_count"] == 0
    assert body["matched_count"] == 1

    listing = client.get("/api/v1/queries", headers=org["headers"]).json()
    assert listing["total"] == 1


def test_import_requires_file_or_rows(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post("/api/v1/queries/import", data={"source": "manual"}, headers=org["headers"])
    assert response.status_code == 422


def test_list_queries_filtered_by_status_and_source(client: TestClient, register_org) -> None:
    org = register_org()
    _import_json(client, org["headers"], "search_console", [{"query": "a"}])
    _import_json(client, org["headers"], "manual", [{"query": "b"}])

    by_source = client.get("/api/v1/queries?source=manual", headers=org["headers"]).json()
    assert by_source["total"] == 1

    by_status = client.get("/api/v1/queries?status=discovered", headers=org["headers"]).json()
    assert by_status["total"] == 2


def test_update_query_fields(client: TestClient, register_org) -> None:
    org = register_org()
    result = _import_json(client, org["headers"], "manual", [{"query": "قیمت ترنجبین"}])
    query_id = result.json()["items"][0]["query_id"]

    response = client.patch(
        f"/api/v1/queries/{query_id}", json={"search_volume": 500, "priority": "high"}, headers=org["headers"]
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["search_volume"] == 500
    assert body["priority"] == "high"


def test_archive_query(client: TestClient, register_org) -> None:
    org = register_org()
    result = _import_json(client, org["headers"], "manual", [{"query": "قیمت ترنجبین"}])
    query_id = result.json()["items"][0]["query_id"]

    response = client.post(f"/api/v1/queries/{query_id}/archive", headers=org["headers"])
    assert response.status_code == 200
    assert response.json()["status"] == "archived"

    double_archive = client.post(f"/api/v1/queries/{query_id}/archive", headers=org["headers"])
    assert double_archive.status_code == 422


def test_viewer_cannot_import_queries(client: TestClient, register_org) -> None:
    org = register_org()
    client.post(
        "/api/v1/users",
        json={"email": "query-viewer@example.dev", "name": "Viewer", "password": "supersecret123", "role": "viewer"},
        headers=org["headers"],
    )
    login = client.post("/api/v1/auth/login", data={"username": "query-viewer@example.dev", "password": "supersecret123"})
    viewer_headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    response = _import_json(client, viewer_headers, "manual", [{"query": "x"}])
    assert response.status_code == 403
