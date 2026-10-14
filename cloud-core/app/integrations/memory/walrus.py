"""
Optional semantic memory backend boundary: Walrus Memory (REQ-AIC-006, ADR-091).

Native PostgreSQL working memory is canonical. Walrus may only MIRROR items for
semantic recall. The namespace is always derived server-side from the tenant
(`org-<organization_id>`); a client can never submit one. Delegate credentials
live only in the server environment (WALRUS_API_URL / WALRUS_DELEGATE_KEY).

Status: the Walrus HTTP contract has NOT been verified in this environment
(no credentials, no reachable endpoint), so no client call is implemented —
inventing endpoints would be fake integration. health() reports that
truthfully and every write/recall degrades to "not mirrored".
"""
from dataclasses import dataclass
from uuid import UUID

from app.core.config import settings


@dataclass
class WalrusHealth:
    status: str       # DISCONNECTED | BLOCKED_EXTERNAL_DEPENDENCY
    detail: str


def namespace_for(organization_id: UUID) -> str:
    return f"org-{organization_id}"


def health() -> WalrusHealth:
    if not settings.WALRUS_API_URL or settings.WALRUS_DELEGATE_KEY is None:
        return WalrusHealth("DISCONNECTED", "Walrus is not configured; native memory only.")
    return WalrusHealth("BLOCKED_EXTERNAL_DEPENDENCY",
                        "Walrus is configured but its API contract has not been verified; no client is implemented.")


def mirror_write(organization_id: UUID, item: dict) -> bool:
    """Returns True only if the item was actually stored in Walrus."""
    return False


def recall(organization_id: UUID, query: str, limit: int = 5) -> list[dict]:
    return []
