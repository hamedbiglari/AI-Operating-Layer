"""
Machine representations (§11/§12/§25, ADR-067).

The property under test: Markdown, JSON and JSON-LD all come from the SAME
canonical Knowledge Object and cannot disagree about claim status.
"""

from fastapi.testclient import TestClient


def _ko_with_claim(client: TestClient, headers: dict, approve: bool = False):
    ko = client.post("/api/v1/knowledge",
                     json={"canonical_name": "Taranjabin", "object_type": "plant",
                           "description": "A sweet exudate."},
                     headers=headers).json()
    entity = client.post("/api/v1/entities",
                         json={"knowledge_object_id": ko["id"], "entity_type": "plant",
                               "canonical_name": "Taranjabin"}, headers=headers).json()
    claim = client.post("/api/v1/claims",
                        json={"knowledge_object_id": ko["id"], "subject_entity_id": entity["id"],
                              "predicate": "contains", "object_value": "mannitol"},
                        headers=headers).json()
    if approve:
        client.post(f"/api/v1/claims/{claim['id']}/review",
                    json={"status": "approved", "note": "ok"}, headers=headers)
    return ko, claim


def test_markdown_comes_from_the_canonical_object(client: TestClient, register_org) -> None:
    org = register_org()
    ko, _ = _ko_with_claim(client, org["headers"])

    response = client.get(f"/api/v1/knowledge/{ko['id']}/markdown", headers=org["headers"])
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    body = response.text
    assert "# Taranjabin" in body
    assert str(ko["id"]) in body, "the canonical ID must appear so the artifact is traceable"
    assert "contains mannitol" in body


def test_markdown_states_claim_status_inline(client: TestClient, register_org) -> None:
    """A draft claim and an approved one must never render identically."""
    org = register_org()
    ko, _ = _ko_with_claim(client, org["headers"])

    body = client.get(f"/api/v1/knowledge/{ko['id']}/markdown", headers=org["headers"]).text
    assert "unverified" in body
    assert "must not be cited as established" in body


def test_markdown_declares_absence_is_not_negative(client: TestClient, register_org) -> None:
    org = register_org()
    ko = client.post("/api/v1/knowledge",
                     json={"canonical_name": "Empty", "object_type": "plant"},
                     headers=org["headers"]).json()

    body = client.get(f"/api/v1/knowledge/{ko['id']}/markdown", headers=org["headers"]).text
    assert "not a negative finding" in body.lower()


def test_json_and_markdown_agree_on_claim_status(client: TestClient, register_org) -> None:
    """THE anti-drift test: two representations of one object must not
    disagree."""
    org = register_org()
    ko, _ = _ko_with_claim(client, org["headers"])

    markdown = client.get(f"/api/v1/knowledge/{ko['id']}/markdown", headers=org["headers"]).text
    data = client.get(f"/api/v1/knowledge/{ko['id']}/representation",
                      headers=org["headers"]).json()

    assert data["coverage"]["unverified_claim_count"] == 1
    assert data["claims"][0]["is_established"] is False
    assert "unverified" in markdown
    assert data["canonical_name"] in markdown


def test_jsonld_excludes_unestablished_claims(client: TestClient, register_org) -> None:
    """A draft claim published as structured data is a public assertion the
    merchant cannot support."""
    org = register_org()
    ko, _ = _ko_with_claim(client, org["headers"], approve=False)

    document = client.get(f"/api/v1/knowledge/{ko['id']}/jsonld", headers=org["headers"]).json()
    assert document["@type"] == "DefinedTerm"
    assert "mannitol" not in str(document.get("additionalProperty", "")), (
        "an unverified claim must not become a schema.org assertion"
    )


def test_jsonld_has_stable_id_tied_to_the_knowledge_object(
    client: TestClient, register_org
) -> None:
    org = register_org()
    ko, _ = _ko_with_claim(client, org["headers"])

    document = client.get(f"/api/v1/knowledge/{ko['id']}/jsonld", headers=org["headers"]).json()
    assert document["@id"].endswith(ko["id"])
    assert document["@context"] == "https://schema.org"


def test_representations_are_tenant_scoped(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    ko_b, _ = _ko_with_claim(client, org_b["headers"])

    for path in ("markdown", "representation", "jsonld"):
        assert client.get(
            f"/api/v1/knowledge/{ko_b['id']}/{path}", headers=org_a["headers"]
        ).status_code == 404


def test_json_representation_is_language_neutral(client: TestClient, register_org) -> None:
    """§56: the canonical Knowledge Object carries no language; localized
    representations do."""
    org = register_org()
    ko, _ = _ko_with_claim(client, org["headers"])

    data = client.get(f"/api/v1/knowledge/{ko['id']}/representation",
                      headers=org["headers"]).json()
    assert data["language"] == "und"
