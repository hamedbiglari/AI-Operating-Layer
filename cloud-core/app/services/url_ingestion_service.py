"""
URL ingestion (P12-07, ADR-072).

WHAT WAS WRONG

`app/ingestion/url_source.py` contained a complete, careful SSRF
implementation — scheme and port allow-lists, per-hop redirect validation,
DNS resolution with every resolved address checked, connection pinned to
the validated IP, streamed size enforcement — and **nothing called it**. A
security control that no code path reaches protects nothing.

THE SHAPE

    POST /documents/ingest-url
      -> validate + tenant-check source        (HTTP, bounded)
      -> create job                            (durable)
      -> 202 + job_id
                                worker -> fetch (SSRF-guarded)
                                       -> retain original (P12-01)
                                       -> conversion pipeline

The fetch runs in the WORKER, not the request. That is not only about
latency: a fetch in the request handler makes the API itself the SSRF
probe, and its timing observable to the caller. Moving it behind a job
means a caller learns only that a job failed, not how long a connection
took — which is the difference between a rejection and a port scanner.

IDEMPOTENCY is tenant-scoped and keyed on the NORMALIZED url plus the
source, never on the URL alone: two organizations ingesting the same public
article are doing two separate, legitimate things.
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlsplit, urlunsplit
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.enums import SyncJobStatus, SyncJobType
from app.models.sync_job import SyncJob


def normalize_url(url: str) -> str:
    """Canonical form for deduplication.

    Lowercases scheme and host, drops a default port and a trailing empty
    path, and discards the fragment (never sent to a server anyway). The
    query string is PRESERVED verbatim: `?id=1` and `?id=2` are different
    documents, and normalising them together would silently merge them.
    """
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    port = parts.port
    if (scheme == "http" and port == 80) or (scheme == "https" and port == 443):
        port = None
    netloc = f"{host}:{port}" if port else host
    path = parts.path or "/"
    return urlunsplit((scheme, netloc, path, parts.query, ""))


def url_idempotency_key(
    *, organization_id: UUID, source_id: UUID, normalized_url: str
) -> str:
    """Tenant-scoped. Two organizations ingesting the same public article
    are doing two separate legitimate things, so the organization is part
    of the key."""
    material = f"url:{organization_id}:{source_id}:{normalized_url}"
    return hashlib.sha256(material.encode()).hexdigest()[:64]


def create_url_ingestion_job(
    db: Session, *, organization_id: UUID, source_id: UUID, url: str,
    title: str | None, language: str, idempotency_key: str | None = None,
) -> tuple[SyncJob, bool]:
    """Creates the durable job. No network activity happens here."""
    normalized = normalize_url(url)
    key = idempotency_key or url_idempotency_key(
        organization_id=organization_id, source_id=source_id, normalized_url=normalized
    )

    existing = db.execute(
        select(SyncJob).where(
            SyncJob.organization_id == organization_id,
            SyncJob.idempotency_key == key,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    job = SyncJob(
        organization_id=organization_id,
        site_id=None,
        job_type=SyncJobType.DOCUMENT_INGESTION,
        status=SyncJobStatus.QUEUED,
        idempotency_key=key,
        payload={
            "kind": "url",
            "source_id": str(source_id),
            "url": url,
            "normalized_url": normalized,
            "title": title,
            "language": language,
        },
    )
    db.add(job)
    db.flush()
    return job, True


def fetch_and_ingest_url(
    db: Session, *, organization_id: UUID, source_id: UUID, url: str,
    title: str | None = None, language: str = "en",
) -> dict:
    """Worker-side: fetch through the SSRF guard, then ingest.

    `UrlRejected` is deliberately allowed to propagate as a PERMANENT
    failure signal — a blocked target will be blocked identically on every
    retry, and retrying it would turn a rejection into a slow internal port
    scan."""
    from app.ingestion.url_source import UrlRejected, fetch_url, filename_for
    from app.services import ingestion_service

    resource = fetch_url(url)  # raises UrlRejected on any policy violation
    filename = filename_for(resource)

    document, conversion = ingestion_service.persist_source_only(
        db, organization_id=organization_id, actor_user_id=None,
        source_id=source_id, filename=filename, data=resource.content,
        title=title or resource.final_url[:200], language=language,
    )

    # URL provenance, recorded on the conversion's warnings/metadata rather
    # than as new columns: it is retrieval context, not conversion identity.
    warnings = dict(conversion.warnings or {})
    warnings["url_provenance"] = {
        "requested_url": url,
        "normalized_url": normalize_url(url),
        "final_url": resource.final_url,
        "redirect_chain": resource.redirects,
        "status_code": resource.status_code,
        "content_type": resource.content_type,
        "retrieved_bytes": len(resource.content),
        # The resolved IP is recorded for audit but is NOT echoed to API
        # callers - see the response schema.
        "resolved_ip": resource.resolved_ip,
    }
    conversion.warnings = warnings
    conversion.source_mime_type = resource.content_type
    db.commit()
    db.refresh(conversion)

    result = ingestion_service.process_pending_conversion(
        db, organization_id=organization_id, document_id=document.id,
        conversion_id=conversion.id, enable_ocr=True, ocr_languages="eng",
    )
    return {
        "document_id": str(document.id),
        "conversion_id": str(conversion.id),
        "final_url": resource.final_url,
        "redirects": len(resource.redirects),
        **result,
    }
