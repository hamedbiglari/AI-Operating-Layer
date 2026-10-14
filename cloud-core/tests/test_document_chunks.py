"""
Integration tests for document chunking, embedding, and pgvector
similarity search — the technical core of Phase 3.
"""

from fastapi.testclient import TestClient


def _create_document(client: TestClient, headers: dict, content: str, title: str = "Doc") -> dict:
    source = client.post(
        "/api/v1/sources", json={"source_type": "website", "title": "Src"}, headers=headers
    ).json()
    return client.post(
        f"/api/v1/documents?source_id={source['id']}",
        json={"title": title, "content": content},
        headers=headers,
    ).json()


def test_process_chunks_and_embeds_short_document(client: TestClient, register_org) -> None:
    org = register_org()
    doc = _create_document(client, org["headers"], "A single short paragraph of text.")

    response = client.post(f"/api/v1/documents/{doc['id']}/process", headers=org["headers"])
    assert response.status_code == 200
    assert response.json()["extraction_status"] == "extracted"

    chunks = client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=org["headers"]).json()
    assert chunks["total"] == 1
    assert chunks["items"][0]["has_embedding"] is True
    assert chunks["items"][0]["chunk_index"] == 0


def test_process_splits_long_document_into_multiple_chunks(
    client: TestClient, register_org
) -> None:
    org = register_org()
    long_content = "\n\n".join(
        f"This is paragraph number {i}. " * 20 for i in range(10)
    )
    doc = _create_document(client, org["headers"], long_content)

    client.post(f"/api/v1/documents/{doc['id']}/process", headers=org["headers"])
    chunks = client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=org["headers"]).json()
    assert chunks["total"] > 1
    indices = sorted(item["chunk_index"] for item in chunks["items"])
    assert indices == list(range(len(indices)))


def test_process_empty_document_marks_failed(client: TestClient, register_org) -> None:
    org = register_org()
    doc = _create_document(client, org["headers"], "   ")

    response = client.post(f"/api/v1/documents/{doc['id']}/process", headers=org["headers"])
    assert response.status_code == 200
    assert response.json()["extraction_status"] == "failed"

    chunks = client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=org["headers"]).json()
    assert chunks["total"] == 0


def test_reprocessing_is_idempotent_not_additive(client: TestClient, register_org) -> None:
    org = register_org()
    doc = _create_document(client, org["headers"], "Some stable content that will not change.")

    client.post(f"/api/v1/documents/{doc['id']}/process", headers=org["headers"])
    client.post(f"/api/v1/documents/{doc['id']}/process", headers=org["headers"])
    client.post(f"/api/v1/documents/{doc['id']}/process", headers=org["headers"])

    chunks = client.get(f"/api/v1/documents/{doc['id']}/chunks", headers=org["headers"]).json()
    assert chunks["total"] == 1


def test_search_finds_exact_chunk_with_zero_distance(client: TestClient, register_org) -> None:
    org = register_org()
    text = "Taranjabin is a manna-like exudate used in traditional medicine."
    doc = _create_document(client, org["headers"], text)
    client.post(f"/api/v1/documents/{doc['id']}/process", headers=org["headers"])

    response = client.get(
        f"/api/v1/documents/chunks/search?q={text}", headers=org["headers"]
    )
    assert response.status_code == 200
    results = response.json()
    assert len(results) >= 1
    assert results[0]["distance"] == 0.0
    assert results[0]["content"] == text


def test_search_can_scope_to_single_document(client: TestClient, register_org) -> None:
    org = register_org()
    doc_a = _create_document(client, org["headers"], "Alpha content unique marker one.", "A")
    doc_b = _create_document(client, org["headers"], "Beta content unique marker two.", "B")
    client.post(f"/api/v1/documents/{doc_a['id']}/process", headers=org["headers"])
    client.post(f"/api/v1/documents/{doc_b['id']}/process", headers=org["headers"])

    response = client.get(
        f"/api/v1/documents/chunks/search?q=anything&document_id={doc_a['id']}",
        headers=org["headers"],
    )
    assert response.status_code == 200
    results = response.json()
    assert all(r["document_id"] == doc_a["id"] for r in results)


def test_search_scoped_to_nonexistent_document_returns_404(
    client: TestClient, register_org
) -> None:
    org = register_org()
    response = client.get(
        "/api/v1/documents/chunks/search?q=x&document_id=00000000-0000-0000-0000-000000000000",
        headers=org["headers"],
    )
    assert response.status_code == 404


def test_get_single_chunk_includes_embedding_vector(client: TestClient, register_org) -> None:
    org = register_org()
    doc = _create_document(client, org["headers"], "Content for embedding retrieval test.")
    client.post(f"/api/v1/documents/{doc['id']}/process", headers=org["headers"])
    chunk_summary = client.get(
        f"/api/v1/documents/{doc['id']}/chunks", headers=org["headers"]
    ).json()["items"][0]

    response = client.get(
        f"/api/v1/documents/{doc['id']}/chunks/{chunk_summary['id']}", headers=org["headers"]
    )
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["embedding"], list)
    assert len(body["embedding"]) == 1536


def test_chunk_from_sibling_document_404s_under_wrong_document_id(
    client: TestClient, register_org
) -> None:
    org = register_org()
    doc_a = _create_document(client, org["headers"], "Doc A content.", "A")
    doc_b = _create_document(client, org["headers"], "Doc B content.", "B")
    client.post(f"/api/v1/documents/{doc_a['id']}/process", headers=org["headers"])
    client.post(f"/api/v1/documents/{doc_b['id']}/process", headers=org["headers"])
    chunk_a = client.get(
        f"/api/v1/documents/{doc_a['id']}/chunks", headers=org["headers"]
    ).json()["items"][0]

    response = client.get(
        f"/api/v1/documents/{doc_b['id']}/chunks/{chunk_a['id']}", headers=org["headers"]
    )
    assert response.status_code == 404
