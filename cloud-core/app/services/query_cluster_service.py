"""
QueryCluster service — automatic similarity grouping (master spec
section 25: "The system should cluster semantically related queries").

**Algorithm choice, explicitly recorded (see docs/DECISIONS.md
ADR-016):** word n-gram (unigram + bigram) Jaccard similarity, computed
over `normalized_query`. NOT pgvector-embedding-based, for one concrete
reason: `app/integrations/embeddings/deterministic.py`'s own docstring
documents that its vectors are "NOT semantically meaningful — this is a
placeholder, not a real embedding" (Phase 3). Clustering on top of that
placeholder would produce clusters with no real semantic basis while
looking numerically legitimate — worse than a simpler method that is
honest about what it can and can't do. Token-overlap clustering has no
such gap: it groups queries that genuinely share vocabulary, which is
a real (if limited) signal, using only the standard library. When a
real embedding provider exists, an embedding-based `QueryClusterMembership.score`
can be populated by a different clustering function without any schema
change (`score` is provider-agnostic on purpose).

Every run **replaces** the organization's clustering wholesale (deletes
all existing QueryCluster/QueryClusterMembership rows for the org, then
recomputes from scratch) — the same "reprocessing is idempotent, not
additive" precedent `document_chunk_service.process_document` already
established, rather than trying to incrementally patch a previous
clustering run.
"""

from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.schemas.common import SortDirection, SortParams, apply_sort

from app.models.enums import QueryStatus
from app.models.query import Query
from app.models.query_cluster import QueryCluster
from app.models.query_cluster_membership import QueryClusterMembership
from app.security.tenant import get_tenant_scoped_or_404
from app.services.audit import record_audit_log

# Documented, revisitable constant (same spirit as
# claim_evidence_service's conflict-weight threshold) - two queries
# join the same cluster when their word-shingle Jaccard similarity is
# at or above this.
_SIMILARITY_THRESHOLD = 0.5


def _shingles(normalized_query: str) -> set[str]:
    """Word unigrams + adjacent-word bigrams. Bigrams give some
    order-sensitivity (so "buy price" and "price buy" share fewer
    shingles than two truly-identical phrasings), unigrams alone would
    treat those as 100% similar."""
    tokens = normalized_query.split()
    shingles = set(tokens)
    shingles.update(f"{a} {b}" for a, b in zip(tokens, tokens[1:]))
    return shingles


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    intersection = len(a & b)
    union = len(a | b)
    return intersection / union if union else 0.0


def cluster_queries(db: Session, *, organization_id: UUID, actor_user_id: UUID | None) -> tuple[int, int]:
    """Returns (cluster_count, clustered_query_count)."""
    db.execute(
        delete(QueryClusterMembership).where(QueryClusterMembership.organization_id == organization_id)
    )
    db.execute(delete(QueryCluster).where(QueryCluster.organization_id == organization_id))
    db.flush()

    queries = db.execute(
        select(Query).where(
            Query.organization_id == organization_id, Query.status != QueryStatus.ARCHIVED
        ).order_by(Query.discovered_at.asc())
    ).scalars().all()

    # cluster_id -> (QueryCluster, list[(Query, shingles)])
    clusters: list[tuple[QueryCluster, list[tuple[Query, set[str]]]]] = []

    for query in queries:
        shingles = _shingles(query.normalized_query)
        best_cluster = None
        best_score = 0.0
        for cluster, members in clusters:
            # compare against the cluster's first (representative) member
            rep_shingles = members[0][1]
            score = _jaccard(shingles, rep_shingles)
            if score >= _SIMILARITY_THRESHOLD and score > best_score:
                best_cluster, best_score = cluster, score

        if best_cluster is not None:
            for cluster, members in clusters:
                if cluster is best_cluster:
                    members.append((query, shingles))
                    db.add(
                        QueryClusterMembership(
                            organization_id=organization_id,
                            query_cluster_id=cluster.id,
                            query_id=query.id,
                            score=round(best_score, 3),
                        )
                    )
                    break
        else:
            new_cluster = QueryCluster(organization_id=organization_id, label=query.query[:300])
            db.add(new_cluster)
            db.flush()
            db.add(
                QueryClusterMembership(
                    organization_id=organization_id,
                    query_cluster_id=new_cluster.id,
                    query_id=query.id,
                    score=1.0,
                )
            )
            clusters.append((new_cluster, [(query, shingles)]))

    # Re-label each cluster with its longest member query (more
    # descriptive than "whichever query happened to arrive first").
    for cluster, members in clusters:
        longest = max(members, key=lambda pair: len(pair[0].query))[0]
        cluster.label = longest.query[:300]

    db.flush()
    record_audit_log(
        db,
        organization_id=organization_id,
        user_id=actor_user_id,
        action="query.clustered",
        resource_type="query_cluster_run",
        resource_id=None,
        new_value={"cluster_count": len(clusters), "clustered_query_count": len(queries)},
    )
    db.commit()
    return len(clusters), len(queries)


def list_clusters(
    db: Session, *, organization_id: UUID, limit: int, offset: int, sort: SortParams | None = None
) -> tuple[list[QueryCluster], int]:
    base = select(QueryCluster).where(QueryCluster.organization_id == organization_id)
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = db.execute(apply_sort(base, QueryCluster, sort, "created_at", SortDirection.DESC).limit(limit).offset(offset)).scalars().all()
    return list(rows), total


def get_cluster_or_404(db: Session, *, cluster_id: UUID, organization_id: UUID) -> QueryCluster:
    return get_tenant_scoped_or_404(
        db, QueryCluster, cluster_id, organization_id=organization_id, not_found_message="Query cluster not found"
    )


def list_cluster_members(
    db: Session, *, cluster_id: UUID, organization_id: UUID, limit: int, offset: int, sort: SortParams | None = None
) -> tuple[list[QueryClusterMembership], int]:
    get_cluster_or_404(db, cluster_id=cluster_id, organization_id=organization_id)
    base = select(QueryClusterMembership).where(
        QueryClusterMembership.query_cluster_id == cluster_id,
        QueryClusterMembership.organization_id == organization_id,
    )
    total = db.execute(select(func.count()).select_from(base.subquery())).scalar_one()
    rows = (
        db.execute(base.order_by(QueryClusterMembership.score.desc().nullslast()).limit(limit).offset(offset))
        .scalars()
        .all()
    )
    return list(rows), total
