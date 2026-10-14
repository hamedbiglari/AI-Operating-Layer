"""
Query service (master spec section 23).

`import_queries` is the one write path every source of demand signal
goes through — a CSV or Excel (`.xlsx`) upload, a JSON batch, or a
single manual entry (source=MANUAL) — per the approved design decision
to route manual creation through the same import path rather than
adding a bare `POST /queries` beyond section 50's literal endpoint
list. Every row is deduplicated against existing Query rows in the
same organization by `normalize_query()`: a match appends a new
QueryProvenance occurrence to the existing row (never silently
overwriting its fields); no match creates a brand-new Query + its
first QueryProvenance row.

Section 23 is explicit: "The system must accept manually uploaded
Excel/CSV query lists" — both formats are a literal MUST, not just
CSV. `parse_csv_rows` and `parse_excel_rows` share the same output
shape (`list[QueryImportRow]`) and the same validation rules (a
`query` column/header is required; blank rows are skipped, not
fatal), so `import_queries` itself is completely format-agnostic —
the API layer picks which parser to call based on the uploaded
file's extension/content-type (see app/api/v1/queries.py).

`status` is only ever touched here for the one manual action this
module owns — archiving. CLASSIFIED is set by
app/services/intent_service.py the moment a query gets its first
Intent row, never here.
"""

import csv
import io
from datetime import datetime, timezone
from uuid import UUID

import openpyxl
from fastapi import HTTPException, status as http_status
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import QueryPriority, QuerySource, QueryStatus
from app.models.intent import Intent
from app.models.query import Query
from app.models.query_provenance import QueryProvenance
from app.schemas.query import QueryImportRow
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log


def normalize_query(text: str) -> str:
    """Deterministic dedup/match key: lowercased, whitespace-collapsed.
    Deliberately simple for v1 — no stemming, no diacritic folding, no
    stopword removal. Good enough to catch exact-content duplicates
    that differ only in casing/spacing (the overwhelming majority of
    real-world CSV/Search-Console duplication); documented as a known
    limitation (see docs/ai-context/KNOWN_ISSUES.md) rather than
    over-built for v1."""
    return " ".join(text.strip().lower().split())


def _build_import_row(get) -> QueryImportRow | None:
    """Shared row-building logic for both parsers below — `get(key)`
    returns the (already-stringified) cell value for that column, or
    None if absent/blank. Returns None for a row with no usable
    `query` value, meaning "skip this row", not "fail the import"."""
    query_text = get("query")
    if not query_text:
        return None
    search_volume_raw = get("search_volume")
    commercial_value_raw = get("commercial_value")
    priority_raw = get("priority")
    return QueryImportRow(
        query=query_text,
        language=get("language") or "en",
        country=get("country"),
        search_volume=int(float(search_volume_raw)) if search_volume_raw else None,
        commercial_value=float(commercial_value_raw) if commercial_value_raw else None,
        priority=QueryPriority(priority_raw.lower()) if priority_raw else QueryPriority.MEDIUM,
    )


def parse_csv_rows(file_bytes: bytes) -> list[QueryImportRow]:
    """Parses an uploaded CSV into QueryImportRow objects. Only the
    `query` column is required; every other column is optional and
    ignored if absent. Uses the Python standard library `csv` module
    only — no new dependency for this format."""
    try:
        text = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="CSV file must be UTF-8 encoded."
        ) from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None or "query" not in {f.strip().lower() for f in reader.fieldnames}:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="CSV must have a 'query' column header.",
        )

    fieldmap = {f.strip().lower(): f for f in reader.fieldnames}

    def _get(row: dict, key: str) -> str | None:
        col = fieldmap.get(key)
        if col is None:
            return None
        value = row.get(col)
        return value.strip() if value else None

    rows: list[QueryImportRow] = []
    for row in reader:
        parsed = _build_import_row(lambda key, row=row: _get(row, key))
        if parsed is not None:
            rows.append(parsed)

    if not rows:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="CSV contained no usable query rows."
        )
    return rows


def parse_excel_rows(file_bytes: bytes) -> list[QueryImportRow]:
    """Parses an uploaded `.xlsx` workbook's first sheet into
    QueryImportRow objects — the other half of section 23's literal
    "Excel/CSV" requirement (see module docstring). Same validation
    rules as `parse_csv_rows`: a `query` header is required, every
    other column is optional, blank rows are skipped rather than
    failing the whole import. Reads with `openpyxl` in `read_only`
    mode (streams rows instead of loading the whole workbook into
    memory) and `data_only=True` (returns each formula cell's last
    computed value, not the formula text itself — a query list isn't
    expected to contain live formulas, and this is the only sane
    reading for one if it does)."""
    try:
        workbook = openpyxl.load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:  # openpyxl raises several different exception types for a corrupt/non-xlsx file
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="File is not a valid .xlsx workbook.",
        ) from exc

    try:
        sheet = workbook.worksheets[0]
        rows_iter = sheet.iter_rows(values_only=True)
        try:
            header_row = next(rows_iter)
        except StopIteration:
            raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Excel file is empty.")

        headers = [str(h).strip().lower() if h is not None else "" for h in header_row]
        if "query" not in headers:
            raise HTTPException(
                status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Excel file must have a 'query' column header (in its first sheet's first row).",
            )
        column_index = {header: i for i, header in enumerate(headers) if header}

        def _cell(row_values: tuple, key: str) -> str | None:
            idx = column_index.get(key)
            if idx is None or idx >= len(row_values):
                return None
            value = row_values[idx]
            if value is None:
                return None
            text = str(value).strip() if not isinstance(value, str) else value.strip()
            return text or None

        rows: list[QueryImportRow] = []
        for row_values in rows_iter:
            parsed = _build_import_row(lambda key, row_values=row_values: _cell(row_values, key))
            if parsed is not None:
                rows.append(parsed)
    finally:
        workbook.close()

    if not rows:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Excel file contained no usable query rows."
        )
    return rows


def import_queries(
    db: Session,
    *,
    organization_id: UUID,
    source: QuerySource,
    rows: list[QueryImportRow],
    actor_user_id: UUID,
) -> list[tuple[Query, bool]]:
    """Returns a list of (Query, created) pairs, `created=False` meaning
    an existing row was matched and a provenance occurrence was
    appended instead."""
    results: list[tuple[Query, bool]] = []
    created_count = 0

    for row in rows:
        normalized = normalize_query(row.query)
        existing = db.execute(
            select(Query).where(Query.organization_id == organization_id, Query.normalized_query == normalized)
        ).scalar_one_or_none()

        if existing is not None:
            db.add(
                QueryProvenance(
                    organization_id=organization_id,
                    query_id=existing.id,
                    source=source,
                    raw_query=row.query,
                )
            )
            results.append((existing, False))
            continue

        query = Query(
            organization_id=organization_id,
            query=row.query,
            normalized_query=normalized,
            language=row.language,
            country=row.country,
            source=source,
            search_volume=row.search_volume,
            commercial_value=row.commercial_value,
            priority=row.priority,
            status=QueryStatus.DISCOVERED,
            discovered_at=row.discovered_at or datetime.now(timezone.utc),
        )
        db.add(query)
        db.flush()  # need query.id for the provenance row below
        db.add(
            QueryProvenance(
                organization_id=organization_id,
                query_id=query.id,
                source=source,
                raw_query=row.query,
            )
        )
        results.append((query, True))
        created_count += 1

    db.flush()
    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="query.imported",
        resource_type="query_import_batch",
        resource_id=None,
        new_value={
            "source": source.value,
            "row_count": len(rows),
            "created_count": created_count,
            "matched_count": len(rows) - created_count,
        },
    )
    db.commit()
    for query, _ in results:
        db.refresh(query)
    return results


def list_queries(
    db: Session,
    *,
    organization_id: UUID,
    status_filter: QueryStatus | None,
    source: QuerySource | None,
    intent_type=None,
    sort: SortParams | None = None,
    limit: int,
    offset: int,
) -> tuple[list[Query], int]:
    base = select(Query).where(Query.organization_id == organization_id)
    if status_filter:
        base = base.where(Query.status == status_filter)
    if source:
        base = base.where(Query.source == source)
    if intent_type:
        base = base.where(
            exists().where(Intent.query_id == Query.id, Intent.intent_type == intent_type)
        )

    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(apply_sort(base, Query, sort, "discovered_at", SortDirection.DESC).limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_query_or_404(db: Session, *, query_id: UUID, organization_id: UUID) -> Query:
    return get_tenant_scoped_or_404(
        db, Query, query_id, organization_id=organization_id, not_found_message="Query not found"
    )


def update_query(
    db: Session,
    *,
    query: Query,
    search_volume: int | None,
    commercial_value: float | None,
    priority: QueryPriority | None,
    actor_user_id: UUID,
) -> Query:
    old_value = {"search_volume": query.search_volume, "priority": query.priority.value}

    if search_volume is not None:
        query.search_volume = search_volume
    if commercial_value is not None:
        query.commercial_value = commercial_value
    if priority is not None:
        query.priority = priority

    db.flush()
    record_audit_log(
        db,
        organization_id=query.organization_id,
        user_id=actor_user_id,
        action="query.updated",
        resource_type="query",
        resource_id=query.id,
        old_value=old_value,
        new_value={"search_volume": query.search_volume, "priority": query.priority.value},
    )
    db.commit()
    db.refresh(query)
    return query


def archive_query(db: Session, *, query: Query, actor_user_id: UUID) -> Query:
    if query.status == QueryStatus.ARCHIVED:
        raise HTTPException(status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Query is already archived.")

    old_status = query.status
    query.status = QueryStatus.ARCHIVED

    db.flush()
    record_audit_log(
        db,
        organization_id=query.organization_id,
        user_id=actor_user_id,
        action="query.archived",
        resource_type="query",
        resource_id=query.id,
        old_value={"status": old_status.value},
        new_value={"status": query.status.value},
    )
    db.commit()
    db.refresh(query)
    return query
