"""
Original source retention (P12-01, ADR-070).

THE DEFECT THIS FIXES

Ingestion discarded the uploaded bytes after conversion and wrote
`storage_path=None`. That breaks the architecture's own rule — the original
is authoritative and Markdown is derived — and it is irreversible: once a
converter upgrade makes better Markdown possible, there is nothing left to
reconvert.

    Original Source -> Conversion -> Canonical Markdown -> Derived
    NOT
    Original Source -> Markdown -> original discarded

STORAGE LAYOUT

    <root>/<organization_id>/<sha256[:2]>/<sha256>[.ext]

Content-addressed, so the same bytes are stored once, and the tenant is a
path component so a directory listing cannot mix tenants. The uploaded
filename is NEVER part of the path — it is recorded as data. That is what
makes `../../etc/passwd` inert rather than merely unlikely.

This is a filesystem backend behind a narrow interface. An object-store
implementation slots in without touching callers; what matters is that the
bytes are kept and addressable.
"""

from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

# Extensions permitted in a stored filename. Anything else is stored
# without a suffix - a stored file must never be executable or
# interpretable by something that scans the directory.
SAFE_SUFFIXES = {
    ".pdf", ".docx", ".pptx", ".xlsx", ".xls", ".csv", ".txt", ".md",
    ".html", ".htm", ".json", ".xml", ".epub",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff",
}


@dataclass(frozen=True)
class StoredObject:
    storage_path: str
    source_hash: str
    byte_size: int
    deduplicated: bool


class OriginalSourceStore:
    """Content-addressed storage for original uploads."""

    def __init__(self, root: Path | str | None = None) -> None:
        self._root = Path(
            root or os.environ.get("AIOL_SOURCE_STORE", "/var/lib/aiol/sources")
        )

    @property
    def root(self) -> Path:
        return self._root

    @staticmethod
    def _safe_suffix(filename: str) -> str:
        suffix = Path(Path(filename or "").name).suffix.lower()
        return suffix if suffix in SAFE_SUFFIXES else ""

    def _path_for(self, organization_id: UUID, source_hash: str, suffix: str) -> Path:
        # organization_id is a UUID object, so it cannot carry separators.
        return self._root / str(organization_id) / source_hash[:2] / f"{source_hash}{suffix}"

    def put(self, *, organization_id: UUID, data: bytes, filename: str) -> StoredObject:
        """Stores bytes. Identical content is stored once.

        Written to a temporary name then renamed, so a crash mid-write
        cannot leave a truncated file at the content-addressed path where
        it would be mistaken for the real thing."""
        source_hash = hashlib.sha256(data).hexdigest()
        suffix = self._safe_suffix(filename)
        target = self._path_for(organization_id, source_hash, suffix)

        if target.exists() and target.stat().st_size == len(data):
            return StoredObject(str(target), source_hash, len(data), deduplicated=True)

        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.partial")
        temporary.write_bytes(data)
        # 0600: readable only by the service account.
        os.chmod(temporary, 0o600)
        temporary.replace(target)
        return StoredObject(str(target), source_hash, len(data), deduplicated=False)

    def get(self, *, organization_id: UUID, storage_path: str) -> bytes:
        """Reads a stored original, with the tenant enforced by PATH.

        The caller's organization is resolved from its credential and used
        to build the expected prefix. A path that does not resolve inside
        that prefix is refused - so a stored path from another tenant, or a
        traversal attempt, cannot be read even if the database row were
        somehow wrong."""
        resolved = Path(storage_path).resolve()
        tenant_root = (self._root / str(organization_id)).resolve()
        if not str(resolved).startswith(str(tenant_root) + os.sep):
            raise PermissionError(
                "Refusing to read a source outside the caller's tenant directory."
            )
        if not resolved.is_file():
            raise FileNotFoundError(storage_path)
        return resolved.read_bytes()

    def delete_tenant(self, organization_id: UUID) -> None:
        shutil.rmtree(self._root / str(organization_id), ignore_errors=True)


_store: OriginalSourceStore | None = None


def get_store() -> OriginalSourceStore:
    global _store
    if _store is None:
        _store = OriginalSourceStore()
    return _store


def set_store(store: OriginalSourceStore) -> None:
    """Test seam so a temporary root can be injected."""
    global _store
    _store = store
