"""v4 document intelligence (ADR-122): the canonical representation, providers, fallback, rendering,
history, evidence location. Ground truth for layout tests is the code that drew the PDF (tests/pdf_writer.py)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import httpx
import pytest
from sqlalchemy import exc, select, text

from app.ingestion import orchestrator, render
from app.ingestion.cdr import CanonicalDocument, Confidence, Element, detect_script, guess_language, normalize_text
from app.ingestion.providers import classify as C
from app.ingestion.providers import ocr as tess
from app.ingestion.providers.base import Availability, DocumentExtractionProvider, ProviderCapabilities, ProviderFailed
from app.ingestion.providers.local_pdf import LocalPdfProvider
from app.ingestion.providers.markitdown_provider import MarkItDownProvider, parse_markdown
from app.ingestion.providers.mathpix import MathpixProvider, normalize_lines_json
from app.models.document_artifact import DocumentConversion, DocumentTable
from app.models.document_element import DocumentElement
from tests.pdf_writer import PdfPage, build_pdf, two_column_paper

FIX = Path(__file__).parent / "fixtures"
D = "/api/v1/documents"


@pytest.fixture()
def paper(tmp_path):
    data, truth = two_column_paper(3)
    p = tmp_path / "paper.pdf"
    p.write_bytes(data)
    return p, truth


def _types(doc):
    return [e.element_type for e in doc.elements]


# ---------------------------------------------------------------------- layout (§8, §9)
def test_two_columns_are_read_column_by_column_not_line_by_line(paper):
    path, truth = paper
    doc = LocalPdfProvider().extract(path)
    page1 = [e for e in doc.elements if e.page == 1]
    texts = [e.text for e in page1]
    left = next(i for i, t in enumerate(texts) if t and t.startswith(truth["left_first"]))
    right = next(i for i, t in enumerate(texts) if t and t.startswith(truth["right_first"]))
    assert left < right
    # the left paragraph is one block holding all four of its own lines, none of the right column's
    assert "were compared in this study." in texts[left] and "Glucose" not in texts[left]


def test_running_headers_and_page_numbers_are_typed_not_deleted(paper):
    doc = LocalPdfProvider().extract(paper[0])
    headers = [e for e in doc.elements if e.element_type == "header"]
    numbers = [e for e in doc.elements if e.element_type == "page_number"]
    assert len(headers) == 3 and {e.page for e in headers} == {1, 2, 3}
    assert headers[0].attributes["detected_by"] == "repetition_across_pages"
    assert [e.text for e in numbers] == ["1", "2", "3"]
    assert "Journal of Manna" not in doc.text_content()          # excluded from body text, still in the CDR


def test_every_element_has_page_and_geometry(paper):
    doc = LocalPdfProvider().extract(paper[0])
    for e in doc.elements:
        assert e.page in (1, 2, 3)
        assert e.bbox is not None and len(e.bbox) == 4 and e.bbox[0] <= e.bbox[2] and e.bbox[1] <= e.bbox[3]
        assert e.block_id
    assert doc.pages[0].width == 612 and doc.pages[0].height == 792


def test_ruled_table_keeps_cells_and_its_caption(paper):
    path, truth = paper
    doc = LocalPdfProvider().extract(path)
    table = next(e for e in doc.elements if e.element_type == "table")
    assert table.attributes["rows"] == truth["table_rows"]
    assert table.attributes["strategy"] == "lines" and table.confidence == 0.9
    cell = next(c for c in table.attributes["cells"] if c["text"] == "Mannitol")
    assert (cell["row"], cell["col"]) == (1, 0) and cell["bbox"] is not None
    caption = next(e for e in doc.elements if e.element_type == "caption")
    assert caption.parent_block_id == table.block_id and table.attributes["caption"].startswith("Table 1.")


def test_equation_is_a_low_confidence_candidate_never_fake_latex(paper):
    doc = LocalPdfProvider().extract(paper[0])
    eq = next(e for e in doc.elements if e.element_type == "equation_display")
    assert eq.attributes["latex"] is None and eq.attributes["recognised"] is False
    assert eq.attributes["equation_number"] == "1"
    assert eq.confidence == 0.35 and doc.confidence.equation == 0.35
    assert doc.confidence.overall == 0.35            # the weakest measured dimension, not an average


def test_chemistry_list_link_and_references(paper):
    doc = LocalPdfProvider().extract(paper[0])
    chem = next(e for e in doc.elements if e.element_type == "chemical")
    assert chem.attributes["chemical_formulas"] == ["C6H12O6", "O2", "CO2", "H2O"]
    assert sum(1 for e in doc.elements if e.element_type == "list_item") == 2
    link = next(e for e in doc.elements if e.element_type == "link")
    assert link.attributes["href"] == "https://example.org/manna"
    refs = [e for e in doc.elements if e.element_type == "reference"]
    assert len(refs) == 2 and refs[0].text.startswith("1. Smith")


def test_confidence_is_differentiated_and_none_means_not_measured(tmp_path):
    doc = LocalPdfProvider().extract(FIX / "simple.pdf")
    c = doc.confidence
    assert c.text == 0.97 and c.layout == 0.9
    assert c.table is None and c.equation is None and c.figure is None      # nothing of that kind: not 0
    assert c.overall == 0.9


def test_page_limit_is_explicit_partial_processing(paper):
    doc = LocalPdfProvider(max_pages=2).extract(paper[0])
    assert doc.unprocessed_pages == [3] and doc.partially_processed
    assert "page_limit_exceeded" in doc.review_reasons
    assert any("NOT processed" in w for w in doc.warnings)


def test_scanned_page_without_ocr_is_listed_unprocessed(tmp_path, monkeypatch):
    monkeypatch.setattr(tess, "tesseract_available", lambda: False)
    blank = build_pdf([PdfPage()])                        # no text layer at all
    p = tmp_path / "scan.pdf"
    p.write_bytes(blank)
    doc = LocalPdfProvider().extract(p)
    assert doc.unprocessed_pages == [1] and doc.pages[0].text_source == "none"
    assert "ocr_unavailable_for_scanned_pages" in doc.review_reasons
    assert doc.document_class == "scanned"


def test_ocr_tsv_keeps_word_geometry_and_confidence():
    tsv = ("level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"
           "5\t1\t1\t1\t1\t1\t10\t20\t30\t10\t90\tMannitol\n"
           "5\t1\t1\t1\t1\t2\t45\t20\t20\t10\t70\t42.1\n"
           "5\t1\t1\t1\t2\t1\t10\t40\t50\t10\t-1\tgrams\n")
    paras = tess.parse_tsv(tsv)
    assert len(paras) == 1 and paras[0].text == "Mannitol 42.1\ngrams"
    assert paras[0].lines[0].bbox == [10, 20, 65, 30] and paras[0].lines[0].confidence == 0.8
    assert paras[0].lines[1].confidence is None                     # -1 = no opinion, never 0


# ---------------------------------------------------------------------- text and scripts (§8.1, §26)
def test_normalisation_expands_ligatures_but_keeps_superscripts():
    assert normalize_text("ﬁnal x²") == "final x²"


@pytest.mark.parametrize("text,script,direction,lang", [
    ("ترنجبین یک ماده شیرین است", "Arab", "rtl", "fa"),
    ("Taranjabin is sweet", "Latn", "ltr", None),
    ("مانیتول mannitol mannitol", "Latn+Arab", "ltr", None),
])
def test_script_direction_and_conservative_language(text, script, direction, lang):
    s, d = detect_script(text)
    assert (s, d) == (script, direction)
    assert guess_language(text, s) == lang


def test_persian_docx_keeps_original_text_through_markitdown_provider():
    doc = MarkItDownProvider().extract(FIX / "persian.docx")
    assert doc.document_class == "not_paginated" and all(e.page is None and e.bbox is None for e in doc.elements)
    persian = next(e for e in doc.elements if e.text and "ترنجبین" in e.text)
    assert persian.direction == "rtl" and persian.language == "fa"
    assert doc.confidence.layout is None                   # no geometry: layout not measured, not zero


def test_markdown_parser_recognises_structure_and_never_drops_text():
    els = parse_markdown("# Title\n\nPara one.\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\n- item\n\n$$x^2$$\n\n???", method="t")
    assert [e.element_type for e in els] == ["heading", "paragraph", "table", "list_item", "equation_display",
                                             "paragraph"]
    assert els[2].attributes["rows"] == [["a", "b"], ["1", "2"]]
    assert els[4].attributes["latex"] == "x^2" and els[-1].text == "???"


def test_chemistry_detector_ignores_ordinary_capitalised_words():
    assert C.chemical_formulas("Mannitol and Glucose are sugars") == []
    assert C.chemical_formulas("dissolved in H2O") == ["H2O"]


# ---------------------------------------------------------------------- Mathpix (§4, §11)
LINES = {"pages": [{"page": 1, "page_width": 1000, "page_height": 1400, "lines": [
    {"type": "text", "text": "Mannitol content \\( x_1 \\) varies.", "cnt": [[10, 10], [500, 10], [500, 40], [10, 40]],
     "confidence": 0.98, "id": "a1", "is_printed": True, "is_handwritten": False},
    {"type": "math", "text": "\\[ E=mc^2 \\tag{3} \\]", "region": {"top_left_x": 100, "top_left_y": 60, "width": 300,
     "height": 40}, "confidence_rate": 0.91, "id": "a2"},
    {"type": "table", "text": "\\begin{tabular}...", "confidence": 0.8, "id": "a3"},
    {"type": "spaceship", "text": "???", "id": "a4", "novel_field": 7},
]}]}


def test_mathpix_lines_are_normalised_and_unknown_fields_kept():
    doc = normalize_lines_json(LINES)
    assert _types(doc) == ["paragraph", "equation_display", "table", "unclassified"]
    p, eq, table, odd = doc.elements
    assert p.bbox == [10.0, 10.0, 500.0, 40.0] and p.attributes["inline_math"] == [" x_1 "]
    assert eq.attributes["latex"] == "E=mc^2 \\tag{3}" and eq.attributes["equation_number"] == "3"
    assert eq.attributes["recognised"] is True and eq.bbox == [100.0, 60.0, 400.0, 100.0]
    assert odd.attributes["original_type"] == "spaceship" and odd.attributes["provider_raw"] == {"novel_field": 7}
    assert doc.confidence.equation == 0.91 and doc.confidence.layout is None


def test_mathpix_unrecognised_output_is_flagged_not_empty_success():
    doc = normalize_lines_json({"unexpected": True})
    assert doc.elements == [] and "provider_output_unrecognised" in doc.review_reasons


def _mathpix(handler, **kw):
    return MathpixProvider(transport=httpx.MockTransport(handler), app_id="id", app_key="key",
                           base_url="https://mathpix.test", poll_interval=0, sleep=lambda s: None, **kw)


def test_mathpix_submit_poll_download_against_documented_endpoints(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(two_column_paper(1)[0])
    seen = []
    polls = iter([{"status": "split"}, {"status": "completed", "num_pages": 1}])

    def handler(req: httpx.Request):
        seen.append((req.method, req.url.path))
        assert req.headers["app_id"] == "id" and req.headers["app_key"] == "key"
        if req.method == "POST":
            assert b'name="options_json"' in req.content
            return httpx.Response(200, json={"pdf_id": "p1"})
        if req.url.path == "/v3/pdf/p1":
            return httpx.Response(200, json=next(polls))
        if req.url.path == "/v3/pdf/p1.lines.json":
            return httpx.Response(200, json=LINES)
        if req.url.path == "/v3/pdf/p1.mmd":
            return httpx.Response(200, text="# mmd")
        return httpx.Response(404)

    doc = _mathpix(handler).extract(pdf)
    assert seen == [("POST", "/v3/pdf"), ("GET", "/v3/pdf/p1"), ("GET", "/v3/pdf/p1"),
                    ("GET", "/v3/pdf/p1.lines.json"), ("GET", "/v3/pdf/p1.mmd")]
    assert doc.raw_outputs["mmd"] == "# mmd" and doc.config["pdf_id"] == "p1"


def test_mathpix_error_and_unconfigured_are_distinct(tmp_path):
    pdf = tmp_path / "a.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    assert MathpixProvider(app_id=None, app_key=None).availability().available is False

    def failing(req):
        if req.method == "POST":
            return httpx.Response(200, json={"pdf_id": "p"})
        return httpx.Response(200, json={"status": "error", "error": "bad file"})
    with pytest.raises(ProviderFailed) as e:
        _mathpix(failing).extract(pdf)
    assert "processing error" in str(e.value) and not e.value.retryable

    def overloaded(req):
        return httpx.Response(503)
    with pytest.raises(ProviderFailed) as e:
        _mathpix(overloaded).extract(pdf)
    assert e.value.retryable and "key" not in str(e.value)          # credentials never echoed


# ---------------------------------------------------------------------- fallback (§12)
class _Fake(DocumentExtractionProvider):
    capabilities = ProviderCapabilities(formats=(".pdf",))

    def __init__(self, name, *, conf=None, fail=False, available=True, text_="same text"):
        self.name, self.conf, self.fail, self.ok, self.text = name, conf, fail, available, text_

    def availability(self):
        return Availability(self.ok, None if self.ok else "not configured")

    def extract(self, path, *, options=None):
        if self.fail:
            raise ProviderFailed("boom", retryable=True)
        d = CanonicalDocument(provider=self.name, provider_version="1",
                              elements=[Element("paragraph", 1, 0, text=self.text)],
                              confidence=Confidence(text=self.conf))
        return d.finalize()


def test_fallback_tries_the_next_provider_and_keeps_every_candidate(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF")
    out = orchestrator.run(p, providers={"a": _Fake("a", fail=True), "b": _Fake("b", available=False),
                                         "c": _Fake("c", conf=0.3), "d": _Fake("d", conf=0.9)},
                           order=["a", "b", "c", "d"], min_confidence=0.5)
    assert [(c.provider, c.status) for c in out.candidates] == [("a", "failed"), ("b", "skipped"),
                                                                 ("c", "succeeded"), ("d", "succeeded")]
    assert out.selected.provider == "d" and out.candidates[1].reason == "not configured"
    assert out.candidates[0].retryable and out.processing_state == "processed"


def test_disagreeing_providers_are_flagged_never_merged(tmp_path):
    p = tmp_path / "x.pdf"
    p.write_bytes(b"%PDF")
    out = orchestrator.run(p, providers={"a": _Fake("a", conf=0.4, text_="mannitol 42 g"),
                                         "b": _Fake("b", conf=0.45, text_="completely different reading")},
                           order=["a", "b"], min_confidence=0.5)
    assert {"providers_disagree", "low_extraction_confidence"} <= set(out.review_reasons)
    assert out.processing_state == "needs_review"
    assert out.selected.document.elements[0].text in ("mannitol 42 g", "completely different reading")


def test_an_unreadable_image_is_still_recorded(tmp_path, monkeypatch):
    monkeypatch.setattr(tess, "tesseract_available", lambda: False)
    out = orchestrator.run(FIX / "figure.png", order=["image_ocr"])
    assert out.selected.provider == "inventory" and out.processing_state == "partially_processed"
    assert out.selected.document.elements[0].element_type == "figure"
    assert "ocr_unavailable_for_image" in out.review_reasons


# ---------------------------------------------------------------------- rendering (§7)
def test_every_format_comes_from_the_same_representation(paper):
    doc = LocalPdfProvider().extract(paper[0])
    md, html, tex = render.render(doc, "markdown"), render.render(doc, "html"), render.render(doc, "latex")
    for out in (md, html, tex):
        assert "Mannitol" in out and "42.1" in out
    assert "| Mannitol | 42.1 | g |" in md and "**Table 1. Sugar content" in md
    assert "Equation (not recognised — text as printed, no. 1)" in md and "$$" not in md
    assert "running header/footer/page-number element(s) are omitted" in md
    assert 'data-page="1"' in html and "<caption>Table 1." in html and "<th>Compound</th>" in html
    assert json.loads(render.render(doc, "json"))["elements"][0]["block_id"]
    assert md.count("Journal of Manna") == 0


def test_html_keeps_merged_cells_markdown_says_it_cannot():
    table = Element("table", 1, 0, block_id="t", attributes={
        "header_rows": 1, "spans_inferred": True, "rows": [["A", "B"], ["x", None]],
        "cells": [{"row": 0, "col": 0, "text": "A", "rowspan": 1, "colspan": 1},
                  {"row": 0, "col": 1, "text": "B", "rowspan": 1, "colspan": 1},
                  {"row": 1, "col": 0, "text": "x", "rowspan": 1, "colspan": 2}]})
    doc = CanonicalDocument(provider="t", provider_version="1", elements=[table]).finalize()
    assert 'colspan=2' in render.to_html(doc).replace('"', "")
    assert "Merged cells are flattened in Markdown" in render.to_markdown(doc)


def test_recognised_latex_is_emitted_and_docx_is_refused_honestly():
    eq = Element("equation_display", 1, 0, text="E=mc^2", attributes={"latex": "E=mc^2", "recognised": True})
    doc = CanonicalDocument(provider="t", provider_version="1", elements=[eq]).finalize()
    assert "$$\nE=mc^2\n$$" in render.render(doc, "markdown")
    assert "\\[\nE=mc^2\n\\]" in render.render(doc, "mmd")
    with pytest.raises(render.UnsupportedFormat, match="no DOCX writer"):
        render.render(doc, "docx")


# ---------------------------------------------------------------------- persistence + API
def _source(client, h):
    return client.post("/api/v1/sources", headers=h, json={"title": "Paper", "source_type": "scientific_paper"}).json()["id"]


def _upload(client, h, name, data, source_id, db_session):
    """Upload, then run the worker body on the test session (the eager Celery task opens its own session and
    cannot see this test's uncommitted transaction — the same arrangement the existing ingestion tests use)."""
    from app.services import ingestion_job_service

    r = client.post(f"{D}/upload", headers=h, data={"source_id": source_id},
                    files={"file": (name, data, "application/octet-stream")})
    assert r.status_code == 202, r.text
    body = r.json()
    ingestion_job_service.run_ingestion_job(db_session, job_id=uuid.UUID(body["job_id"]))
    db_session.expire_all()
    return body


def _run_reprocess(client, h, doc_id, db_session, **json_):
    from app.services import ingestion_job_service

    r = client.post(f"{D}/{doc_id}/reprocess", headers=h, json=json_ or None)
    assert r.status_code == 202, r.text
    ingestion_job_service.run_ingestion_job(db_session, job_id=uuid.UUID(r.json()["job_id"]))
    db_session.expire_all()
    return r.json()


def test_worker_persists_the_canonical_representation(client, register_org, db_session):
    org = register_org()
    h = org["headers"]
    body = _upload(client, h, "paper.pdf", two_column_paper(2)[0], _source(client, h), db_session)
    doc_id = body["document_id"]
    convs = client.get(f"{D}/{doc_id}/conversions", headers=h).json()
    assert len(convs) == 1
    c = convs[0]
    assert c["is_current"] and c["layout_provider"] == "local_pdf" and c["document_class"] == "digital"
    assert c["confidence"]["equation"] == 0.35 and c["confidence"]["overall"] == 0.35
    assert c["processing_state"] == "needs_review" and "low_extraction_confidence" in c["review_reasons"]
    assert {x["provider"]: x["status"] for x in c["candidates"]} == {"local_pdf": "succeeded", "mathpix": "skipped"}
    page2 = client.get(f"{D}/{doc_id}/elements?page=2", headers=h).json()
    assert page2["total"] >= 3 and all(e["page"] == 2 and e["bbox"] for e in page2["items"])
    tables = client.get(f"{D}/{doc_id}/elements?element_type=table", headers=h).json()["items"]
    assert tables[0]["attributes"]["rows"][1] == ["Mannitol", "42.1", "g"]
    # Markdown served to chunking is rendered from the CDR
    md = client.get(f"{D}/{doc_id}/markdown", headers=h).text
    assert "| Mannitol | 42.1 | g |" in md and "Equation (not recognised" in md
    for fmt in ("html", "mmd", "latex", "json"):
        assert client.get(f"{D}/{doc_id}/render/{fmt}", headers=h).status_code == 200
    assert client.get(f"{D}/{doc_id}/render/docx", headers=h).status_code == 501


def test_reprocess_supersedes_but_never_deletes_the_previous_extraction(client, register_org, db_session):
    org = register_org()
    h = org["headers"]
    body = _upload(client, h, "tables.pdf", (FIX / "tables.pdf").read_bytes(), _source(client, h), db_session)
    doc_id = body["document_id"]
    first = client.get(f"{D}/{doc_id}/conversions", headers=h).json()[0]
    _run_reprocess(client, h, doc_id, db_session, trigger="technology_upgrade")
    convs = client.get(f"{D}/{doc_id}/conversions", headers=h).json()
    assert len(convs) == 2
    new, old = convs
    assert new["is_current"] and not old["is_current"] and old["superseded_at"] and new["trigger"] == "technology_upgrade"
    assert old["id"] == first["id"]
    db_session.expire_all()
    tables = db_session.execute(select(DocumentTable).where(DocumentTable.document_id == uuid.UUID(doc_id))).scalars().all()
    assert {str(t.conversion_id) for t in tables} == {old["id"], new["id"]}           # both extractions kept
    assert len(client.get(f"{D}/{doc_id}/artifacts", headers=h).json()["tables"]) == 1   # current one by default
    old_tables = client.get(f"{D}/{doc_id}/artifacts?conversion_id={old['id']}", headers=h).json()["tables"]
    assert len(old_tables) == 1
    assert client.get(f"{D}/{doc_id}/elements?conversion_id={old['id']}", headers=h).json()["total"] > 0


def test_a_failed_reprocess_leaves_the_current_extraction_in_force(client, register_org, db_session, monkeypatch):
    from app.ingestion import pipeline
    from app.ingestion.converter import ConversionResult, ConversionStatus
    from app.ingestion.extractors import ExtractionLevel, ExtractionResult
    from app.services import ingestion_service

    org = register_org()
    h = org["headers"]
    body = _upload(client, h, "simple.pdf", (FIX / "simple.pdf").read_bytes(), _source(client, h), db_session)
    doc_id = body["document_id"]
    before = client.get(f"{D}/{doc_id}/markdown", headers=h).text

    def broken(*a, **kw):
        return pipeline.PipelineResult(
            conversion=ConversionResult(ConversionStatus.FAILED, None, "markitdown", "x", "h", 1, None, 0, 0.0, "boom"),
            extraction=ExtractionResult(level_used=ExtractionLevel.NORMALIZE), canonical_markdown=None)
    monkeypatch.setattr(ingestion_service, "process_document", broken)
    monkeypatch.setattr(ingestion_service.orchestrator, "run",
                        lambda *a, **kw: orchestrator.ExtractionOutcome(review_reasons=["no_provider_succeeded"]))
    _run_reprocess(client, h, doc_id, db_session)
    convs = client.get(f"{D}/{doc_id}/conversions", headers=h).json()
    failed = next(c for c in convs if not c["is_current"])
    assert failed["processing_state"] == "failed" and failed["superseded_at"] is None
    assert client.get(f"{D}/{doc_id}/markdown", headers=h).text == before


def test_one_current_extraction_is_enforced_by_the_database(client, register_org, db_session):
    org = register_org()
    h = org["headers"]
    body = _upload(client, h, "simple.pdf", (FIX / "simple.pdf").read_bytes(), _source(client, h), db_session)
    conv = db_session.get(DocumentConversion, uuid.UUID(body["conversion_id"]))
    with pytest.raises(exc.IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text(
                "INSERT INTO document_conversions (id, organization_id, document_id, original_filename, source_hash, "
                "source_size_bytes, converter_name, converter_version, conversion_status, extraction_level, "
                "is_current, created_at, updated_at) SELECT gen_random_uuid(), organization_id, document_id, "
                "original_filename, source_hash, source_size_bytes, converter_name, converter_version, "
                "conversion_status, extraction_level, true, now(), now() FROM document_conversions WHERE id = :i"),
                {"i": conv.id})
    with pytest.raises(exc.IntegrityError):
        with db_session.begin_nested():
            db_session.execute(text("UPDATE document_conversions SET needs_review = true, review_reasons = '[]' "
                                    "WHERE id = :i"), {"i": conv.id})


def test_evidence_points_at_a_page_and_claims_are_found_by_page(client, register_org, db_session):
    org = register_org()
    h = org["headers"]
    src = _source(client, h)
    body = _upload(client, h, "paper.pdf", two_column_paper(2)[0], src, db_session)
    doc_id = body["document_id"]
    table = client.get(f"{D}/{doc_id}/elements?element_type=table", headers=h).json()["items"][0]
    ev = client.post("/api/v1/evidence", headers=h, json={
        "source_id": src, "document_id": doc_id, "document_element_id": table["id"], "summary": "Mannitol 42.1 g/100 g"})
    assert ev.status_code == 201, ev.text
    ev = ev.json()
    assert ev["page_number"] == 1 and ev["location"]["bbox"] == table["bbox"]
    assert ev["location"]["provider"] == "local_pdf" and ev["location"]["element_type"] == "table"
    ko = client.post("/api/v1/knowledge", headers=h, json={"canonical_name": "Taranjabin", "object_type": "plant"}).json()
    ent = client.post("/api/v1/entities", headers=h, json={"knowledge_object_id": ko["id"], "entity_type": "plant",
                                                            "canonical_name": "Taranjabin"}).json()
    claim = client.post("/api/v1/claims", headers=h, json={"knowledge_object_id": ko["id"], "subject_entity_id": ent["id"],
                                                           "predicate": "contains", "object_value": "mannitol"}).json()
    client.post("/api/v1/claim-evidence", headers=h, json={"claim_id": claim["id"], "evidence_id": ev["id"],
                                                           "relation": "supports"})
    on1 = client.get(f"{D}/{doc_id}/pages/1/claims", headers=h).json()
    assert [c["claim_id"] for c in on1["claims"]] == [claim["id"]] and on1["evidence_on_page"] == 1
    assert client.get(f"{D}/{doc_id}/pages/2/claims", headers=h).json()["claims"] == []


def test_an_element_from_another_document_or_tenant_is_refused(client, register_org, db_session):
    org = register_org()
    h = org["headers"]
    src = _source(client, h)
    a = _upload(client, h, "paper.pdf", two_column_paper(1)[0], src, db_session)
    b = _upload(client, h, "simple.pdf", (FIX / "simple.pdf").read_bytes(), src, db_session)
    el = client.get(f"{D}/{a['document_id']}/elements", headers=h).json()["items"][0]
    wrong_doc = client.post("/api/v1/evidence", headers=h, json={
        "source_id": src, "document_id": b["document_id"], "document_element_id": el["id"], "summary": "x"})
    assert wrong_doc.status_code == 422
    other = register_org()
    assert client.get(f"{D}/{a['document_id']}/elements", headers=other["headers"]).status_code == 404
    assert client.get(f"{D}/{a['document_id']}/render/markdown", headers=other["headers"]).status_code == 404
    assert client.post(f"{D}/{a['document_id']}/reprocess", headers=other["headers"]).status_code == 404


def test_extraction_produced_by_older_technology_is_listed(client, register_org, db_session):
    org = register_org()
    h = org["headers"]
    body = _upload(client, h, "simple.pdf", (FIX / "simple.pdf").read_bytes(), _source(client, h), db_session)
    stale = client.get(f"{D}/extraction/stale", headers=h).json()
    assert body["document_id"] not in [s["document_id"] for s in stale["items"]]
    db_session.execute(text("UPDATE document_conversions SET layout_provider_version = 'pdfplumber-0.0.1' WHERE id = :i"),
                       {"i": body["conversion_id"]})
    db_session.flush()
    stale = client.get(f"{D}/extraction/stale", headers=h).json()
    hit = next(s for s in stale["items"] if s["document_id"] == body["document_id"])
    assert "pdfplumber-0.0.1" in hit["reason"]
    providers = client.get(f"{D}/extraction/providers", headers=h).json()
    by = {p["name"]: p for p in providers["providers"]}
    assert by["mathpix"]["available"] is False and by["mathpix"]["capabilities"]["runs_locally"] is False
    assert providers["vision"]["available"] is False


# ---------------------------------------------------------------------- benchmark (§57, §58)
def _paper_truth(truth):
    from tests.pdf_writer import LEFT_COL, RIGHT_COL

    return {"blocks": [{"text": truth["title"]}, {"text": " ".join(LEFT_COL)}, {"text": " ".join(RIGHT_COL)}],
            "headings": [truth["title"], "References"], "tables": [truth["table_rows"]],
            "equations": ["a + b = g"], "captions": {"Table 1. Sugar content per 100 g of manna.": "table"}}


def test_benchmark_measures_the_local_provider_against_ground_truth(paper):
    from app.ingestion import benchmark

    path, truth = paper
    r = benchmark.evaluate(LocalPdfProvider().extract(path), _paper_truth(truth), name="paper")
    m = r.metrics
    assert m["reading_order_tau"] == 1.0 and m["blocks_matched"] == "3/3"
    assert m["heading_f1"] == 1.0 and m["table_cell_accuracy"] == 1.0 and m["caption_association"] == 1.0
    assert m["equation_recall"] == 1.0 and m["equations_recognised_as_latex"] == 0       # located, not recognised
    assert m["provenance_completeness"] == 1.0 and m["information_loss"] == 0.0
    assert m["confidence_calibration"] is not None


def test_benchmark_detects_a_degraded_reading():
    from app.ingestion import benchmark

    truth = {"blocks": [{"text": "first block"}, {"text": "second block"}, {"text": "third block"}]}
    swapped = CanonicalDocument(provider="t", provider_version="1", elements=[
        Element("paragraph", 1, 0, text="third block", bbox=[0, 0, 1, 1], confidence=0.9),
        Element("paragraph", 1, 1, text="second block", confidence=0.9),
        Element("paragraph", 1, 2, text="fir", bbox=[0, 0, 1, 1], confidence=0.9)]).finalize()
    m = benchmark.evaluate(swapped, truth).metrics
    assert m["reading_order_tau"] == -1.0 and m["information_loss"] > 0
    assert m["provenance_completeness"] == round(2 / 3, 4)
    assert m["heading_f1"] is None and m["table_cell_accuracy"] is None          # nothing to measure: not 0


def test_benchmark_reports_an_unavailable_provider_instead_of_scoring_it(monkeypatch):
    from app.ingestion import benchmark

    out = benchmark.run("mathpix", [])
    assert out["available"] is False and "MATHPIX" in out["reason"]
