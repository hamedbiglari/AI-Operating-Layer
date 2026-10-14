"""
THE GOLDEN TEST SUITE — Phase 3 edition (Sources, Documents, Chunks).

Continues the pattern from tests/test_tenant_isolation.py (Phase 1) and
tests/test_knowledge_tenant_isolation.py (Phase 2), applying the same
invariant to every Phase 3 resource: Organization A must never read,
list, or write anything belonging to Organization B's Sources/
Documents/Chunks — including the two-hop case (attaching a Document to
another org's Source) that the Phase 2 review specifically flagged as
something to stay disciplined about going into Phase 3.
"""

from fastapi.testclient import TestClient


def _create_source(client: TestClient, headers: dict, title: str = "Source") -> dict:
    return client.post(
        "/api/v1/sources", json={"source_type": "website", "title": title}, headers=headers
    ).json()


def _create_document(client: TestClient, headers: dict, source_id: str, content: str = "text") -> dict:
    return client.post(
        f"/api/v1/documents?source_id={source_id}",
        json={"title": "Doc", "content": content},
        headers=headers,
    ).json()


# --- Sources -----------------------------------------------------------


def test_user_cannot_read_another_orgs_source(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])

    response = client.get(f"/api/v1/sources/{source_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_update_another_orgs_source(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])

    response = client.patch(
        f"/api/v1/sources/{source_b['id']}", json={"title": "Hijacked"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_source_list_never_includes_other_orgs_sources(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    _create_source(client, org_a["headers"], "A Only")
    _create_source(client, org_b["headers"], "B Only")

    response = client.get("/api/v1/sources", headers=org_a["headers"])
    titles = [item["title"] for item in response.json()["items"]]
    assert "A Only" in titles
    assert "B Only" not in titles


# --- Documents (the critical two-hop case) ---------------------------------


def test_user_cannot_attach_document_to_another_orgs_source(
    client: TestClient, register_org
) -> None:
    """The exact scenario the Phase 2 review flagged as a principle to
    carry forward: a caller who is fully authenticated and authorized
    within their OWN organization must still be rejected when the
    resource they're pointing at (source_id) belongs to someone else."""
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])

    response = client.post(
        f"/api/v1/documents?source_id={source_b['id']}",
        json={"title": "Smuggled Document", "content": "x"},
        headers=org_a["headers"],
    )
    assert response.status_code == 404


def test_user_cannot_read_another_orgs_document(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])
    doc_b = _create_document(client, org_b["headers"], source_b["id"])

    response = client.get(f"/api/v1/documents/{doc_b['id']}", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_update_another_orgs_document(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])
    doc_b = _create_document(client, org_b["headers"], source_b["id"])

    response = client.patch(
        f"/api/v1/documents/{doc_b['id']}", json={"title": "Hijacked"}, headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_user_cannot_process_another_orgs_document(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])
    doc_b = _create_document(client, org_b["headers"], source_b["id"])

    response = client.post(f"/api/v1/documents/{doc_b['id']}/process", headers=org_a["headers"])
    assert response.status_code == 404


def test_document_list_never_includes_other_orgs_documents(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()
    source_a = _create_source(client, org_a["headers"])
    source_b = _create_source(client, org_b["headers"])
    _create_document(client, org_a["headers"], source_a["id"], "A content")
    _create_document(client, org_b["headers"], source_b["id"], "B content")

    response = client.get("/api/v1/documents", headers=org_a["headers"])
    ids = [item["id"] for item in response.json()["items"]]
    assert len(ids) == 1


def test_nested_documents_route_404s_for_foreign_source(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])

    response = client.get(f"/api/v1/sources/{source_b['id']}/documents", headers=org_a["headers"])
    assert response.status_code == 404


# --- Document Chunks / pgvector search --------------------------------------


def test_user_cannot_list_chunks_of_another_orgs_document(
    client: TestClient, register_org
) -> None:
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])
    doc_b = _create_document(client, org_b["headers"], source_b["id"], "Secret content.")
    client.post(f"/api/v1/documents/{doc_b['id']}/process", headers=org_b["headers"])

    response = client.get(f"/api/v1/documents/{doc_b['id']}/chunks", headers=org_a["headers"])
    assert response.status_code == 404


def test_user_cannot_read_another_orgs_chunk_by_id(client: TestClient, register_org) -> None:
    org_a = register_org()
    org_b = register_org()
    source_b = _create_source(client, org_b["headers"])
    doc_b = _create_document(client, org_b["headers"], source_b["id"], "Secret content.")
    client.post(f"/api/v1/documents/{doc_b['id']}/process", headers=org_b["headers"])
    chunk_b = client.get(
        f"/api/v1/documents/{doc_b['id']}/chunks", headers=org_b["headers"]
    ).json()["items"][0]

    response = client.get(
        f"/api/v1/documents/{doc_b['id']}/chunks/{chunk_b['id']}", headers=org_a["headers"]
    )
    assert response.status_code == 404


def test_similarity_search_never_returns_another_orgs_chunks(
    client: TestClient, register_org
) -> None:
    """The pgvector-specific version of the golden test: even though
    both organizations' chunks live in the SAME physical table and the
    SAME HNSW index, org A's search must never surface org B's content
    — proving the WHERE organization_id = ... filter is actually
    applied to the vector query, not just to REST-layer lookups by ID."""
    org_a = register_org()
    org_b = register_org()
    source_a = _create_source(client, org_a["headers"])
    source_b = _create_source(client, org_b["headers"])
    doc_a = _create_document(
        client, org_a["headers"], source_a["id"], "Org A's confidential research findings."
    )
    doc_b = _create_document(
        client, org_b["headers"], source_b["id"], "Org A's confidential research findings."
    )
    client.post(f"/api/v1/documents/{doc_a['id']}/process", headers=org_a["headers"])
    client.post(f"/api/v1/documents/{doc_b['id']}/process", headers=org_b["headers"])

    response = client.get(
        "/api/v1/documents/chunks/search?q=Org%20A%27s%20confidential%20research%20findings.",
        headers=org_a["headers"],
    )
    assert response.status_code == 200
    results = response.json()
    returned_doc_ids = {r["document_id"] for r in results}
    assert doc_a["id"] in returned_doc_ids
    assert doc_b["id"] not in returned_doc_ids
