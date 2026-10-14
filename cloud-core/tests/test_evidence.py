"""
Integration tests for Evidence: creation with each level of the
Source/Document/Chunk provenance chain, the chain-validation rules, and
the review lifecycle.
"""

from fastapi.testclient import TestClient


def _create_source(client: TestClient, headers: dict, title: str = "Source") -> dict:
    return client.post(
        "/api/v1/sources",
        json={"source_type": "scientific_paper", "title": title},
        headers=headers,
    ).json()


def _create_document(client: TestClient, headers: dict, source_id: str, content: str = "Some extracted text.") -> dict:
    return client.post(
        f"/api/v1/documents?source_id={source_id}",
        json={"title": "Doc", "content": content},
        headers=headers,
    ).json()


def _process_document(client: TestClient, headers: dict, document_id: str) -> dict:
    return client.post(f"/api/v1/documents/{document_id}/process", headers=headers).json()


def _get_first_chunk_id(client: TestClient, headers: dict, document_id: str) -> str:
    chunks = client.get(f"/api/v1/documents/{document_id}/chunks", headers=headers).json()
    return chunks["items"][0]["id"]


def test_create_evidence_with_source_only(client: TestClient, register_org) -> None:
    org = register_org()
    source = _create_source(client, org["headers"])

    response = client.post(
        "/api/v1/evidence",
        json={
            "source_id": source["id"],
            "study_type": "randomized_controlled_trial",
            "directness": "direct",
            "evidence_strength": "high",
            "summary": "An RCT of N=200 found the compound reduced symptom X by 30%.",
            "sample_size": 200,
            "population": "adult humans",
        },
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["source_id"] == source["id"]
    assert body["document_id"] is None
    assert body["document_chunk_id"] is None
    assert body["study_type"] == "randomized_controlled_trial"
    assert body["evidence_strength"] == "high"
    assert body["status"] == "draft"
    assert body["human_reviewed"] is False


def test_create_evidence_pinned_to_document_and_chunk(client: TestClient, register_org) -> None:
    org = register_org()
    source = _create_source(client, org["headers"])
    document = _create_document(client, org["headers"], source["id"])
    _process_document(client, org["headers"], document["id"])
    chunk_id = _get_first_chunk_id(client, org["headers"], document["id"])

    response = client.post(
        "/api/v1/evidence",
        json={
            "source_id": source["id"],
            "document_id": document["id"],
            "document_chunk_id": chunk_id,
            "summary": "Pinned to the exact excerpt.",
        },
        headers=org["headers"],
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["document_id"] == document["id"]
    assert body["document_chunk_id"] == chunk_id


def test_document_must_belong_to_given_source(client: TestClient, register_org) -> None:
    org = register_org()
    source_a = _create_source(client, org["headers"], "Source A")
    source_b = _create_source(client, org["headers"], "Source B")
    document_of_b = _create_document(client, org["headers"], source_b["id"])

    response = client.post(
        "/api/v1/evidence",
        json={
            "source_id": source_a["id"],
            "document_id": document_of_b["id"],
            "summary": "Mismatched provenance.",
        },
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_chunk_must_belong_to_given_document(client: TestClient, register_org) -> None:
    org = register_org()
    source = _create_source(client, org["headers"])
    document_a = _create_document(client, org["headers"], source["id"], content="Doc A content.")
    document_b = _create_document(client, org["headers"], source["id"], content="Doc B content.")
    _process_document(client, org["headers"], document_a["id"])
    _process_document(client, org["headers"], document_b["id"])
    chunk_of_a = _get_first_chunk_id(client, org["headers"], document_a["id"])

    response = client.post(
        "/api/v1/evidence",
        json={
            "source_id": source["id"],
            "document_id": document_b["id"],
            "document_chunk_id": chunk_of_a,
            "summary": "Mismatched chunk.",
        },
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_chunk_without_document_is_rejected(client: TestClient, register_org) -> None:
    org = register_org()
    source = _create_source(client, org["headers"])
    document = _create_document(client, org["headers"], source["id"])
    _process_document(client, org["headers"], document["id"])
    chunk_id = _get_first_chunk_id(client, org["headers"], document["id"])

    response = client.post(
        "/api/v1/evidence",
        json={
            "source_id": source["id"],
            "document_chunk_id": chunk_id,
            "summary": "Chunk without its document.",
        },
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_review_evidence_sets_verified_and_human_reviewed(client: TestClient, register_org) -> None:
    org = register_org()
    source = _create_source(client, org["headers"])
    evidence = client.post(
        "/api/v1/evidence",
        json={"source_id": source["id"], "summary": "Some finding."},
        headers=org["headers"],
    ).json()

    response = client.post(
        f"/api/v1/evidence/{evidence['id']}/review",
        json={"status": "verified", "evidence_strength": "moderate", "note": "Checked against the PDF."},
        headers=org["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "verified"
    assert body["evidence_strength"] == "moderate"
    assert body["human_reviewed"] is True


def test_update_evidence_summary(client: TestClient, register_org) -> None:
    org = register_org()
    source = _create_source(client, org["headers"])
    evidence = client.post(
        "/api/v1/evidence",
        json={"source_id": source["id"], "summary": "Original summary."},
        headers=org["headers"],
    ).json()

    response = client.patch(
        f"/api/v1/evidence/{evidence['id']}",
        json={"summary": "Corrected summary.", "sample_size": 50},
        headers=org["headers"],
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["summary"] == "Corrected summary."
    assert body["sample_size"] == 50


def test_list_evidence_filters_by_source(client: TestClient, register_org) -> None:
    org = register_org()
    source_a = _create_source(client, org["headers"], "Source A")
    source_b = _create_source(client, org["headers"], "Source B")
    client.post("/api/v1/evidence", json={"source_id": source_a["id"], "summary": "A finding."}, headers=org["headers"])
    client.post("/api/v1/evidence", json={"source_id": source_b["id"], "summary": "B finding."}, headers=org["headers"])

    response = client.get(f"/api/v1/evidence?source_id={source_a['id']}", headers=org["headers"])
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["source_id"] == source_a["id"]
