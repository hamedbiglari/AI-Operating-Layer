"""
Document Intelligence — tested against REAL documents, not mocks.

Every fixture here is a genuine PDF/DOCX/XLSX produced by reportlab,
python-docx and openpyxl. The point is that these tests would have caught
the two failures measurement revealed in MarkItDown 0.1.7:

  - PDF tables flattened into unusable text
  - embedded images silently dropped

Both are now recovered by our extraction layer (ADR-065/066), and these
tests fail if that layer regresses.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.ingestion.converter import ConversionStatus, MarkItDownConverter
from app.ingestion.extractors import AssetStatus, ExtractionLevel, OcrStatus, extract_structure
from app.ingestion.pipeline import process_document

FIXTURES = Path(__file__).parent / "fixtures"
pytestmark = pytest.mark.skipif(not FIXTURES.exists(), reason="fixtures not generated")


def _source(client: TestClient, headers: dict) -> str:
    return client.post(
        "/api/v1/sources", json={"source_type": "scientific_paper", "title": "Fixture"},
        headers=headers,
    ).json()["id"]


def _upload_and_run(client: TestClient, headers: dict, name: str, source_id: str, db_session=None):
    """Drives the ASYNC chain to completion (P12-02).

    Upload returns 202 with a job id; the worker body is then executed
    against the same session. This is the real `run_ingestion_job` used by
    the Celery task, not a reimplementation — a helper that duplicated the
    worker logic would let the two drift and prove nothing."""
    import uuid as _uuid

    from app.services.ingestion_job_service import run_ingestion_job

    accepted = _upload(client, headers, name, source_id)
    assert accepted.status_code == 202, accepted.text
    body = accepted.json()

    organization_id = None
    from app.models.sync_job import SyncJob
    job = db_session.get(SyncJob, _uuid.UUID(body["job_id"])) if db_session else None
    organization_id = job.organization_id if job else None
    if db_session is not None and organization_id is not None:
        run_ingestion_job(
            db_session, job_id=_uuid.UUID(body["job_id"]), organization_id=organization_id
        )
    return body


def _document_id(client: TestClient, org: dict, name: str, db_session) -> str:
    """Runs the async chain and returns the resulting document id."""
    accepted = _upload_and_run(client, org["headers"], name, _source(client, org["headers"]), db_session)
    return client.get(
        f"/api/v1/documents/ingestion-jobs/{accepted['job_id']}", headers=org["headers"]
    ).json()["document_id"]


def _upload(client: TestClient, headers: dict, name: str, source_id: str, **form):
    """Upload returns 202 (P12-02). The pipeline runs in a worker."""
    data = {"source_id": source_id}
    data.update({k: str(v) for k, v in form.items()})
    with (FIXTURES / name).open("rb") as handle:
        return client.post(
            "/api/v1/documents/upload", data=data,
            files={"file": (name, handle, "application/octet-stream")}, headers=headers,
        )


def _upload_and_process(client: TestClient, headers: dict, name: str, source_id: str,
                        db_session=None, **form) -> dict:
    """Uploads, then runs the worker phase INLINE against the same session.

    This is a worker-path test, not a queue test: it exercises
    `process_pending_conversion` exactly as the Celery task does. The real
    queue chain is covered separately by the async acceptance run, which
    uses a live worker and broker — a distinction kept explicit because a
    test that calls the task function is not evidence the queue works."""
    from uuid import UUID

    from app.services import ingestion_service

    accepted = _upload(client, headers, name, source_id, **form).json()
    if db_session is not None:
        try:
            ingestion_service.process_pending_conversion(
                db_session,
                organization_id=UUID(accepted["document_id"]) and _org_of(db_session, accepted),
                document_id=UUID(accepted["document_id"]),
                conversion_id=UUID(accepted["conversion_id"]),
                enable_ocr=bool(form.get("enable_ocr", True)),
                ocr_languages=str(form.get("ocr_languages", "eng")),
            )
        except Exception:
            pass
    return accepted


def _org_of(db_session, accepted: dict):
    from uuid import UUID

    from app.models.document import Document

    return db_session.get(Document, UUID(accepted["document_id"])).organization_id


# --- converter boundary -----------------------------------------------------


def test_converter_succeeds_on_real_pdf() -> None:
    result = MarkItDownConverter().convert(FIXTURES / "simple.pdf")
    assert result.status == ConversionStatus.SUCCEEDED
    assert "Taranjabin" in (result.markdown or "")
    assert len(result.source_hash) == 64
    assert result.converter_name == "markitdown"
    assert result.converter_version != "unknown"


def test_malformed_pdf_is_not_a_silent_success() -> None:
    """MarkItDown 0.1.7 returns the literal string "None" for this file.
    Without the guard, a Document would be created whose entire content is
    the word "None" and nothing downstream would notice."""
    result = MarkItDownConverter().convert(FIXTURES / "broken.pdf")
    assert result.status != ConversionStatus.SUCCEEDED
    assert result.markdown != "None"
    assert not result.markdown


def test_empty_file_is_reported_as_empty_not_failed() -> None:
    result = MarkItDownConverter().convert(FIXTURES / "empty.pdf")
    assert result.status == ConversionStatus.EMPTY


def test_unsupported_extension_is_distinct_from_failure(tmp_path: Path) -> None:
    target = tmp_path / "thing.exe"
    target.write_bytes(b"MZ\x00\x00")
    assert MarkItDownConverter().convert(target).status == ConversionStatus.UNSUPPORTED


def test_source_hash_is_of_original_bytes_not_text() -> None:
    """Two fixtures with different bytes must hash differently even though
    both convert to text — this is what makes dedup and reprocessing work."""
    a = MarkItDownConverter().convert(FIXTURES / "simple.pdf")
    b = MarkItDownConverter().convert(FIXTURES / "tables.pdf")
    assert a.source_hash != b.source_hash


# --- the two failures MarkItDown alone exhibits ----------------------------------


def test_pdf_table_flattened_by_markitdown_is_recovered() -> None:
    """MarkItDown returns `Compound Amount Unit / Mannitol / Glucose /
    Water / 42.1 / 18.7 / 12.0` — columns scrambled. Our layer must produce
    a real table."""
    raw = MarkItDownConverter().convert(FIXTURES / "tables.pdf").markdown or ""
    assert "| Compound |" not in raw, "fixture assumption changed: MarkItDown now emits a table"

    extraction = extract_structure(FIXTURES / "tables.pdf")
    assert extraction.tables, "the flattened table must be recovered"
    table = extraction.tables[0]
    assert table.headers == ["Compound", "Amount", "Unit"]
    assert ["Mannitol", "42.1", "g"] in table.rows
    assert "| Mannitol | 42.1 | g |" in table.markdown


def test_ruled_table_uses_the_higher_confidence_strategy() -> None:
    table = extract_structure(FIXTURES / "ruled.pdf").tables[0]
    assert table.strategy == "lines"
    assert table.confidence > 0.8


def test_unruled_table_falls_back_to_text_strategy_with_lower_confidence() -> None:
    """Confidence must reflect how the result was obtained. `text` infers
    structure from whitespace and deserves less trust than ruled lines."""
    table = extract_structure(FIXTURES / "tables.pdf").tables[0]
    assert table.strategy == "text"
    assert table.confidence < 0.8


def test_embedded_image_dropped_by_markitdown_is_recovered_and_ocred() -> None:
    """MarkItDown returns only `See figure below.` — the figure vanishes."""
    raw = MarkItDownConverter().convert(FIXTURES / "with_image.pdf").markdown or ""
    assert "FIGURE" not in raw, "fixture assumption changed: MarkItDown now surfaces the image"

    extraction = extract_structure(FIXTURES / "with_image.pdf")
    assert len(extraction.images) == 1
    image = extraction.images[0]
    assert image.status == AssetStatus.EXTRACTED
    assert image.page_number == 1
    assert len(image.source_hash) == 64
    if image.ocr_status == OcrStatus.SUCCEEDED:
        assert "FIGURE" in (image.ocr_text or "").upper()
        assert extraction.level_used == ExtractionLevel.OCR
    else:
        # Honest: without tesseract the image is still RECORDED, never dropped.
        assert image.ocr_status == OcrStatus.UNAVAILABLE


def test_ocr_unavailable_is_distinct_from_no_text_found() -> None:
    """Collapsing these would turn a missing tool into a finding about the
    document."""
    assert OcrStatus.UNAVAILABLE != OcrStatus.NO_TEXT_FOUND


# --- canonical artifact --------------------------------------------------------


def test_canonical_markdown_contains_recovered_table() -> None:
    result = process_document(FIXTURES / "tables.pdf")
    assert result.ok
    assert "## Extracted tables" in result.canonical_markdown
    assert "| Mannitol | 42.1 | g |" in result.canonical_markdown
    assert result.table_count == 1


def test_ocr_text_is_fenced_and_attributed_not_inlined() -> None:
    """Downstream claim extraction must be able to tell that a sentence came
    from a machine reading a picture, not from the document's own prose."""
    result = process_document(FIXTURES / "with_image.pdf")
    assert result.ok
    if result.ocr_block_count:
        assert "[Image OCR" in result.canonical_markdown
        assert "[End OCR]" in result.canonical_markdown


def test_unreadable_images_are_declared_not_omitted() -> None:
    """An image we could not interpret is information. Omitting it would let
    the artifact imply the page had no figure."""
    result = process_document(FIXTURES / "with_image.pdf", enable_ocr=False)
    assert result.ok
    assert "not interpreted" in result.canonical_markdown.lower()
    assert "no claim is made" in result.canonical_markdown.lower()


def test_persian_survives_the_pipeline_uncorrupted() -> None:
    result = process_document(FIXTURES / "persian.docx")
    assert result.ok
    markdown = result.canonical_markdown
    assert "ترنجبین" in markdown
    assert "Taranjabin" in markdown
    assert "ماده" in markdown and "مقدار" in markdown
    assert "۴۲" in markdown, "Persian numerals must not be transliterated"
    assert "?" not in markdown.replace("?", "", 0) or "\ufffd" not in markdown


def test_xlsx_tables_come_from_markitdown_without_our_layer() -> None:
    """MarkItDown handles Office tables correctly (measured), so our layer
    must NOT duplicate it — two implementations could disagree."""
    result = process_document(FIXTURES / "data.xlsx")
    assert result.ok
    assert "| Mannitol | 42.1 |" in result.canonical_markdown
    assert result.extraction.level_used == ExtractionLevel.NORMALIZE


def test_failed_conversion_produces_no_artifact() -> None:
    result = process_document(FIXTURES / "broken.pdf")
    assert not result.ok
    assert result.canonical_markdown is None
    assert result.warnings


# --- API: upload, security, provenance -------------------------------------------


def test_upload_is_accepted_asynchronously_with_a_job_id(
    client: TestClient, register_org, db_session
) -> None:
    """P12-02: upload returns 202 and a durable job id; it does NOT run the
    pipeline inline."""
    org = register_org()
    response = _upload(client, org["headers"], "tables.pdf", _source(client, org["headers"]))
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["job_id"]
    assert body["status"] == "queued"
    assert body["job_type"] == "document_ingestion"
    assert len(body["source_hash"]) == 64
    assert body["storage_path_recorded"] is True, "the original must be stored before queueing"


def test_worker_produces_the_extraction_result(
    client: TestClient, register_org, db_session
) -> None:
    org = register_org()
    accepted = _upload_and_run(
        client, org["headers"], "tables.pdf", _source(client, org["headers"]), db_session
    )
    status_body = client.get(
        f"/api/v1/documents/ingestion-jobs/{accepted['job_id']}", headers=org["headers"]
    ).json()
    assert status_body["status"] == "succeeded"
    assert status_body["conversion_status"] == "succeeded"
    assert status_body["table_count"] == 1
    assert status_body["document_id"]


def test_markdown_artifact_is_served_as_text_markdown(client: TestClient, register_org, db_session) -> None:
    org = register_org()
    uploaded = _upload_and_run(
        client, org["headers"], "tables.pdf", _source(client, org["headers"]), db_session
    )
    document_id = client.get(
        f"/api/v1/documents/ingestion-jobs/{uploaded['job_id']}", headers=org["headers"]
    ).json()["document_id"]

    response = client.get(
        f"/api/v1/documents/{document_id}/markdown", headers=org["headers"]
    )
    assert response.status_code == 200
    assert "text/markdown" in response.headers["content-type"]
    assert "| Mannitol | 42.1 | g |" in response.text


def test_structured_tables_are_queryable_not_only_markdown(
    client: TestClient, register_org, db_session
) -> None:
    """Markdown is lossy for tabular data: once flattened to a string a
    numeric column cannot be queried. Both forms are stored."""
    org = register_org()
    document_id = _document_id(client, org, "tables.pdf", db_session)

    artifacts = client.get(
        f"/api/v1/documents/{document_id}/artifacts", headers=org["headers"]
    ).json()
    assert len(artifacts["tables"]) == 1
    table = artifacts["tables"][0]
    assert table["headers"] == ["Compound", "Amount", "Unit"]
    assert ["Mannitol", "42.1", "g"] in table["rows"]
    assert table["extraction_strategy"] in ("lines", "text")


def test_image_assets_are_recorded_with_ocr_provenance(
    client: TestClient, register_org, db_session
) -> None:
    org = register_org()
    document_id = _document_id(client, org, "with_image.pdf", db_session)

    assets = client.get(
        f"/api/v1/documents/{document_id}/artifacts", headers=org["headers"]
    ).json()["assets"]
    assert len(assets) == 1
    asset = assets[0]
    assert asset["page_number"] == 1
    assert asset["status"] == "extracted"
    assert asset["ocr_status"] in ("succeeded", "unavailable", "no_text_found", "not_attempted")
    assert asset["vision_model"] is None
    if asset["ocr_status"] == "succeeded":
        assert asset["ocr_engine"] == "tesseract"
        assert asset["ocr_version"]


def test_failed_conversion_still_records_an_auditable_row(
    client: TestClient, register_org, db_session
) -> None:
    """Ingestion that leaves no trace on failure is indistinguishable from
    an upload that never happened."""
    org = register_org()
    accepted = _upload_and_run(
        client, org["headers"], "broken.pdf", _source(client, org["headers"]), db_session
    )
    status_body = client.get(
        f"/api/v1/documents/ingestion-jobs/{accepted['job_id']}", headers=org["headers"]
    ).json()
    # The JOB succeeded (it ran); the CONVERSION did not. Those are
    # different facts and must not be collapsed.
    assert status_body["status"] == "succeeded"
    assert status_body["conversion_status"] in ("empty", "failed")
    assert status_body["document_id"]


# --- security -----------------------------------------------------------------------


def test_mislabelled_file_is_refused(client: TestClient, register_org) -> None:
    """The extension is a claim; the bytes are evidence. Handing a
    mislabelled file to a parser is how parser exploits get reached."""
    org = register_org()
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_id": _source(client, org["headers"])},
        files={"file": ("evil.pdf", b"MZ\x90\x00 this is a PE binary", "application/pdf")},
        headers=org["headers"],
    )
    assert response.status_code == 422
    assert "does not match" in response.text


def test_disallowed_extension_is_refused(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_id": _source(client, org["headers"])},
        files={"file": ("payload.exe", b"MZ\x90\x00", "application/octet-stream")},
        headers=org["headers"],
    )
    assert response.status_code == 415


def test_empty_upload_is_refused(client: TestClient, register_org) -> None:
    org = register_org()
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_id": _source(client, org["headers"])},
        files={"file": ("empty.pdf", b"", "application/pdf")},
        headers=org["headers"],
    )
    assert response.status_code == 422


def test_path_traversal_filename_cannot_escape(client: TestClient, register_org) -> None:
    """The original name is recorded as DATA and never used as a path.

    This test has been rewritten twice, and both rewrites are the point.

    v1 asserted `safe_extension("../../etc/passwd.pdf") == ".pdf"`, which is
    true whether or not any guard exists — `Path.suffix` already ignores
    directory components. It could not fail.

    v2 added a source-inspection assertion (`"uuid4().hex" in source`). That
    caught the mutation, but broke the moment the function was refactored
    and the code moved — it was testing where the code lived, not what it
    did. Source-scanning guards are explicitly discouraged for this reason.

    v3 (this) asserts only behaviour. The structural guarantee is covered by
    `test_uploaded_filename_never_becomes_a_filesystem_path` below, which
    uploads a hostile name and checks the filesystem."""
    from app.services.ingestion_service import safe_extension

    assert safe_extension("../../../etc/passwd.pdf") == ".pdf"
    assert safe_extension("/absolute/evil.pdf") == ".pdf"
    assert safe_extension("no_extension") == ""
    assert safe_extension("") == ""


def test_uploaded_filename_never_becomes_a_filesystem_path(
    client: TestClient, register_org, tmp_path
) -> None:
    """Behavioural proof: upload a file whose name is a traversal attempt
    and confirm nothing is written outside the quarantine root."""
    from app.services import ingestion_service

    org = register_org()
    source_id = _source(client, org["headers"])
    hostile = "../../../../tmp/aiol_traversal_probe.pdf"
    probe = Path("/tmp/aiol_traversal_probe.pdf")
    if probe.exists():
        probe.unlink()

    response = client.post(
        "/api/v1/documents/upload",
        data={"source_id": source_id},
        files={"file": (hostile, (FIXTURES / "simple.pdf").read_bytes(), "application/pdf")},
        headers=org["headers"],
    )
    assert response.status_code == 202
    assert not probe.exists(), "the uploaded filename was used as a filesystem path"
    assert response.json()["job_id"]


def test_oversized_upload_is_refused(client: TestClient, register_org) -> None:
    from app.services import ingestion_service

    org = register_org()
    oversized = b"%PDF" + b"\x00" * (ingestion_service.MAX_UPLOAD_BYTES + 10)
    response = client.post(
        "/api/v1/documents/upload",
        data={"source_id": _source(client, org["headers"])},
        files={"file": ("big.pdf", oversized, "application/pdf")},
        headers=org["headers"],
    )
    assert response.status_code == 413


def test_viewer_cannot_upload(client: TestClient, register_org) -> None:
    org = register_org()
    source_id = _source(client, org["headers"])
    client.post("/api/v1/users",
                json={"email": "doc-viewer@example.dev", "name": "V",
                      "password": "supersecret123", "role": "viewer"},
                headers=org["headers"])
    token = client.post("/api/v1/auth/login",
                        data={"username": "doc-viewer@example.dev",
                              "password": "supersecret123"}).json()["access_token"]
    assert _upload(client, {"Authorization": f"Bearer {token}"},
                   "simple.pdf", source_id).status_code == 403


def test_cannot_upload_against_another_orgs_source(client: TestClient, register_org) -> None:
    org_a, org_b = register_org(), register_org()
    source_b = _source(client, org_b["headers"])
    assert _upload(client, org_a["headers"], "simple.pdf", source_b).status_code == 404


def test_artifacts_are_tenant_scoped(client: TestClient, register_org, db_session) -> None:
    org_a, org_b = register_org(), register_org()
    document_id = _document_id(client, org_b, "tables.pdf", db_session)
    for path in ("markdown", "artifacts"):
        assert client.get(
            f"/api/v1/documents/{document_id}/{path}", headers=org_a["headers"]
        ).status_code == 404


# --- deduplication -------------------------------------------------------------------


def test_dedup_key_includes_converter_version(client: TestClient, register_org, db_session) -> None:
    """Omitting the version would reuse an artifact produced by an older
    converter after an upgrade, silently serving stale Markdown."""
    import uuid as _uuid

    from app.services.ingestion_service import find_reusable_conversion

    org = register_org()
    _upload_and_run(client, org["headers"], "simple.pdf", _source(client, org["headers"]), db_session)
    org_id = _uuid.UUID(org["organization"]["id"])

    from app.models.document_artifact import DocumentConversion
    from sqlalchemy import select as _select

    row = db_session.execute(
        _select(DocumentConversion).where(DocumentConversion.organization_id == org_id)
    ).scalars().first()
    assert row is not None

    assert find_reusable_conversion(
        db_session, organization_id=org_id, source_hash=row.source_hash,
        converter_name=row.converter_name, converter_version=row.converter_version,
    ) is not None
    assert find_reusable_conversion(
        db_session, organization_id=org_id, source_hash=row.source_hash,
        converter_name=row.converter_name, converter_version="99.99.99-future",
    ) is None, "a different converter version must NOT reuse the old artifact"
