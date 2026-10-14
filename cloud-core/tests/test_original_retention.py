"""
Original source retention (P12-01, ADR-070).

The defect: uploaded bytes were discarded and `storage_path` was NULL.
Irreversible — once a converter upgrade makes better Markdown possible,
there is nothing left to reconvert.
"""

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingestion.storage import OriginalSourceStore, set_store

FIXTURES = Path(__file__).parent / "fixtures"
pytestmark = pytest.mark.skipif(not FIXTURES.exists(), reason="fixtures not generated")


@pytest.fixture(autouse=True)
def temp_store(tmp_path):
    """Isolated store per test; never touches the real root."""
    store = OriginalSourceStore(root=tmp_path / "sources")
    set_store(store)
    yield store
    set_store(OriginalSourceStore())


def _source(client: TestClient, headers: dict) -> str:
    return client.post("/api/v1/sources",
                       json={"source_type": "scientific_paper", "title": "S"},
                       headers=headers).json()["id"]


def _upload(client: TestClient, headers: dict, name: str, source_id: str):
    with (FIXTURES / name).open("rb") as handle:
        return client.post("/api/v1/documents/upload", data={"source_id": source_id},
                           files={"file": (name, handle, "application/octet-stream")},
                           headers=headers)


def _upload_and_run(client: TestClient, org: dict, name: str, db_session):
    """Drives the async chain (P12-02) and returns the document id.

    Note the ordering this proves: the original is retained during the
    REQUEST, before the worker runs. That is what makes a never-drained
    queue non-destructive."""
    import uuid as _uuid

    from app.models.sync_job import SyncJob
    from app.services.ingestion_job_service import run_ingestion_job

    accepted = _upload(client, org["headers"], name, _source(client, org["headers"]))
    assert accepted.status_code == 202, accepted.text
    job_id = _uuid.UUID(accepted.json()["job_id"])
    job = db_session.get(SyncJob, job_id)
    run_ingestion_job(db_session, job_id=job_id, organization_id=job.organization_id)
    return client.get(
        f"/api/v1/documents/ingestion-jobs/{job_id}", headers=org["headers"]
    ).json()["document_id"], accepted.json()


def test_original_bytes_are_retained_and_byte_identical(
    client: TestClient, register_org, db_session
) -> None:
    """THE P12-01 test: what comes back must be the file that went in."""
    org = register_org()
    original = (FIXTURES / "tables.pdf").read_bytes()
    document_id, accepted = _upload_and_run(client, org, "tables.pdf", db_session)

    response = client.get(
        f"/api/v1/documents/{document_id}/original", headers=org["headers"]
    )
    assert response.status_code == 200
    assert response.content == original
    assert hashlib.sha256(response.content).hexdigest() == accepted["source_hash"]


def test_storage_path_is_populated_not_null(client: TestClient, register_org, db_session) -> None:
    import uuid as _uuid

    from sqlalchemy import select

    from app.models.document_artifact import DocumentConversion

    org = register_org()
    _upload_and_run(client, org, "simple.pdf", db_session)

    row = db_session.execute(
        select(DocumentConversion).where(
            DocumentConversion.organization_id == _uuid.UUID(org["organization"]["id"])
        )
    ).scalars().first()
    assert row.storage_path, "storage_path must no longer be NULL"


def test_original_is_retained_even_when_conversion_fails(
    client: TestClient, register_org, db_session
) -> None:
    """The case where keeping the bytes matters MOST: conversion failed, so
    the original is the only remaining copy."""
    org = register_org()
    document_id, _ = _upload_and_run(client, org, "broken.pdf", db_session)

    response = client.get(
        f"/api/v1/documents/{document_id}/original", headers=org["headers"]
    )
    assert response.status_code == 200
    assert response.content == (FIXTURES / "broken.pdf").read_bytes()


def test_identical_content_is_stored_once(temp_store, register_org) -> None:
    import uuid as _uuid

    organization_id = _uuid.uuid4()
    data = b"%PDF-1.4 identical"
    first = temp_store.put(organization_id=organization_id, data=data, filename="a.pdf")
    second = temp_store.put(organization_id=organization_id, data=data, filename="b.pdf")

    assert first.storage_path == second.storage_path
    assert second.deduplicated is True


def test_tenant_cannot_read_another_tenants_original(
    client: TestClient, register_org, db_session
) -> None:
    org_a, org_b = register_org(), register_org()
    document_id, _ = _upload_and_run(client, org_b, "simple.pdf", db_session)

    assert client.get(
        f"/api/v1/documents/{document_id}/original", headers=org_a["headers"]
    ).status_code == 404


def test_store_refuses_a_path_outside_the_callers_tenant(temp_store) -> None:
    """Second line of defence: even a wrong database row cannot become a
    cross-tenant file read."""
    import uuid as _uuid

    org_a, org_b = _uuid.uuid4(), _uuid.uuid4()
    stored = temp_store.put(organization_id=org_b, data=b"%PDF-1.4 b", filename="b.pdf")

    with pytest.raises(PermissionError):
        temp_store.get(organization_id=org_a, storage_path=stored.storage_path)


def test_store_refuses_traversal_in_the_stored_path(temp_store) -> None:
    import uuid as _uuid

    organization_id = _uuid.uuid4()
    temp_store.put(organization_id=organization_id, data=b"%PDF-1.4 x", filename="x.pdf")

    with pytest.raises((PermissionError, FileNotFoundError)):
        temp_store.get(
            organization_id=organization_id,
            storage_path=str(temp_store.root / str(organization_id) / ".." / ".." / "etc" / "passwd"),
        )


def test_uploaded_filename_never_appears_in_the_storage_path(temp_store) -> None:
    """Content-addressed: the path is the hash, never the caller's name."""
    import uuid as _uuid

    organization_id = _uuid.uuid4()
    stored = temp_store.put(
        organization_id=organization_id, data=b"%PDF-1.4 y",
        filename="../../../etc/passwd.pdf",
    )
    assert "passwd" not in stored.storage_path
    assert "etc" not in Path(stored.storage_path).name
    assert stored.source_hash in stored.storage_path


def test_unsafe_suffix_is_not_carried_into_storage(temp_store) -> None:
    """A stored file must never be executable or interpretable by something
    that scans the directory."""
    import uuid as _uuid

    stored = temp_store.put(
        organization_id=_uuid.uuid4(), data=b"binary", filename="payload.sh"
    )
    assert not stored.storage_path.endswith(".sh")


def test_stored_file_is_not_world_readable(temp_store) -> None:
    import uuid as _uuid

    stored = temp_store.put(
        organization_id=_uuid.uuid4(), data=b"%PDF-1.4 z", filename="z.pdf"
    )
    mode = Path(stored.storage_path).stat().st_mode & 0o777
    assert mode == 0o600, f"stored original is mode {oct(mode)}, expected 0600"


def test_original_download_is_attachment_with_nosniff(
    client: TestClient, register_org, db_session
) -> None:
    """A stored HTML/SVG original must not execute in the caller's origin."""
    org = register_org()
    document_id, _ = _upload_and_run(client, org, "simple.pdf", db_session)

    response = client.get(
        f"/api/v1/documents/{document_id}/original", headers=org["headers"]
    )
    assert "attachment" in response.headers["content-disposition"]
    assert response.headers["x-content-type-options"] == "nosniff"
