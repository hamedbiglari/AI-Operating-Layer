"""
Shared API schemas: pagination envelope and error shape.

Kept generic so every future list endpoint (knowledge, products,
queries, etc.) reuses the same contract instead of inventing its own.
"""

from enum import Enum
from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class PaginationParams(BaseModel):
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)


class SortDirection(str, Enum):
    ASC = "asc"
    DESC = "desc"


class SortParams(BaseModel):
    """Sorting, required by master spec section 51 (ADR-056).

    `sort_by` is validated against a per-model allow-list in
    `SORTABLE_FIELDS` below — never interpolated into SQL, and never
    silently ignored. An unknown field is a 422 naming the permitted
    values, because silently falling back means a consumer paginating a
    list gets a different order on every page and never learns why.
    """

    sort_by: str | None = Field(default=None, max_length=64)
    sort_dir: SortDirection | None = Field(default=None)


# ---------------------------------------------------------------------------
# THE SINGLE SOURCE OF TRUTH for what is sortable.
#
# Keyed by model class name; maps a PUBLIC field name to a model attribute.
# The indirection matters: the API contract is not tied to column names, so
# renaming a column does not break consumers, and an internal column can be
# excluded from the public contract simply by leaving it out.
#
# Every entry is a deliberate choice. Free-text bodies (`content`,
# `summary`, `description`) are excluded throughout: sorting a paginated
# list by a large text column is expensive, rarely meaningful, and would
# need an index nobody wants. Secrets and hashes are excluded for obvious
# reasons.
# ---------------------------------------------------------------------------

_TIMESTAMPS = {"created_at": "created_at", "updated_at": "updated_at"}
_CREATED_ONLY = {"created_at": "created_at"}

SORTABLE_FIELDS: dict[str, dict[str, str]] = {
    # --- AI Center (REQ-AIC-*, REQ-KW-*)
    "AIProvider": {**_TIMESTAMPS, "name": "name", "verification_status": "verification_status"},
    "AIProviderAccount": {**_TIMESTAMPS, "label": "label", "health_status": "health_status",
                          "failure_count": "failure_count", "last_used_at": "last_used_at"},
    "AIHealthEvent": {**_TIMESTAMPS, "observed_at": "observed_at", "status": "status"},
    "AIModel": {**_TIMESTAMPS, "name": "name", "status": "status", "context_window": "context_window"},
    "AIRoutingPolicy": {**_TIMESTAMPS, "name": "name", "mode": "mode"},
    "AIWorkingMemory": {**_TIMESTAMPS, "kind": "kind", "version": "version"},
    "AIDiscoveryEntry": {**_TIMESTAMPS, "name": "name", "status": "status", "last_verified_at": "last_verified_at"},
    "AgentDefinition": {**_TIMESTAMPS, "name": "name", "agent_type": "agent_type", "status": "status"},
    "WalletLedgerEntry": {**_TIMESTAMPS, "amount_cents": "amount_cents", "entry_type": "entry_type"},
    "WalletReservation": {**_TIMESTAMPS, "amount_cents": "amount_cents", "status": "status"},
    "Payment": {**_TIMESTAMPS, "amount_cents": "amount_cents", "status": "status"},
    "SynthesisRun": {**_TIMESTAMPS, "status": "status", "finished_at": "finished_at"},
    "WorkspaceCommand": {**_TIMESTAMPS, "title": "title", "state": "state", "last_activity_at": "last_activity_at"},
    "Conversation": {**_TIMESTAMPS, "title": "title", "state": "state",
                     "last_message_at": "last_message_at", "message_count": "message_count"},
    "ConversationMessage": {**_TIMESTAMPS, "position": "position", "role": "role",
                            "answer_state": "answer_state"},
    "ConversationResearchRequest": {**_TIMESTAMPS, "state": "state", "decided_at": "decided_at"},
    "SitePost": {**_TIMESTAMPS, "title": "title", "status": "status", "published_at": "published_at", "lang": "lang"},
    "NewsletterSubscriber": {**_TIMESTAMPS, "email": "email", "status": "status", "consented_at": "consented_at"},
    "Publication": {**_TIMESTAMPS, "publication_version": "publication_version", "status": "status", "title": "title"},
    "CoverageAudit": {**_TIMESTAMPS, "audit_version": "audit_version", "status": "status", "finished_at": "finished_at"},
    "Category": {**_TIMESTAMPS, "name": "name", "slug": "slug"},
    "SectionDefinition": {**_TIMESTAMPS, "position": "position", "key": "key"},
    "KnowledgeSection": {**_TIMESTAMPS, "status": "status", "section_key": "section_key"},
    "SectionPropagation": {**_TIMESTAMPS, "state": "state"},
    "ResearchQuerySet": {**_TIMESTAMPS, "name": "name", "run_count": "run_count", "last_run_at": "last_run_at"},
    "EvidenceCompletionTask": {**_TIMESTAMPS, "status": "status", "closed_at": "closed_at"},
    "EvidenceConflict": {**_TIMESTAMPS, "status": "status", "reviewed_at": "reviewed_at"},
    "ResearchQuestion": {**_TIMESTAMPS, "subject": "subject"},
    "DemandSignal": {**_TIMESTAMPS, "observed_at": "observed_at", "impressions": "impressions", "clicks": "clicks", "searches": "searches", "zero_result_searches": "zero_result_searches", "query_text": "query_text"},
    "KnowledgeKeyword": {**_TIMESTAMPS, "keyword": "keyword", "kind": "kind", "volume": "volume", "priority": "priority"},
    # --- Phase 17
    "AIExecution": {**_TIMESTAMPS, "started_at": "started_at", "completed_at": "completed_at",
                    "duration_ms": "duration_ms", "status": "status", "provider": "provider",
                    "model": "model", "total_tokens": "total_tokens"},  # no cost sort: cost is admin-only
    # --- Phase 1
    "User": {**_TIMESTAMPS, "email": "email", "name": "name", "role": "role"},
    "Site": {**_TIMESTAMPS, "name": "name", "domain": "domain"},
    # --- Phase 2
    "KnowledgeObject": {**_TIMESTAMPS, "canonical_name": "canonical_name",
                        "object_type": "object_type", "status": "status"},
    "Entity": {**_TIMESTAMPS, "canonical_name": "canonical_name", "entity_type": "entity_type"},
    "Claim": {**_TIMESTAMPS, "predicate": "predicate", "status": "status",
              "evidence_strength": "evidence_strength"},
    "Relationship": {**_TIMESTAMPS, "predicate": "predicate", "status": "status"},
    "KnowledgeGap": {**_TIMESTAMPS, "gap_type": "gap_type", "priority": "priority",
                     "status": "status"},
    # --- Phase 3
    "Source": {**_TIMESTAMPS, "title": "title", "source_type": "source_type",
               "reliability_score": "reliability_score", "publication_date": "publication_date"},
    "Document": {**_TIMESTAMPS, "title": "title", "extraction_status": "extraction_status"},
    # chunk_index is the natural reading order of a document, so it is both
    # sortable and the default.
    "DocumentChunk": {**_CREATED_ONLY, "chunk_index": "chunk_index"},
    # --- Phase 4
    "Evidence": {**_TIMESTAMPS, "study_type": "study_type", "evidence_strength": "evidence_strength",
                 "status": "status", "sample_size": "sample_size"},
    "ClaimEvidence": {**_TIMESTAMPS, "relation": "relation", "weight": "weight"},
    # --- Phase 5
    "ResearchProject": {**_TIMESTAMPS, "name": "name", "mode": "mode", "status": "status"},
    "ResearchTask": {**_TIMESTAMPS, "task_type": "task_type", "status": "status",
                     "started_at": "started_at", "completed_at": "completed_at"},
    "ResearchTaskReference": {**_CREATED_ONLY, "reference_type": "reference_type", "role": "role"},
    # --- Phase 6
    "Query": {**_TIMESTAMPS, "query": "query", "source": "source", "status": "status",
              "priority": "priority", "search_volume": "search_volume",
              "discovered_at": "discovered_at"},
    "Intent": {**_CREATED_ONLY, "intent_type": "intent_type", "confidence": "confidence",
               "is_primary": "is_primary"},
    "QueryGroup": {**_TIMESTAMPS, "name": "name", "primary_intent": "primary_intent",
                   "priority": "priority"},
    "QueryGroupMembership": _CREATED_ONLY,
    "QueryCluster": {**_TIMESTAMPS, "label": "label"},
    # --- Phase 7
    "Product": {**_TIMESTAMPS, "name": "name", "slug": "slug", "sku": "sku", "brand": "brand",
                "category": "category", "status": "status"},
    "Offer": {**_TIMESTAMPS, "price": "price", "availability": "availability",
              "stock_quantity": "stock_quantity", "valid_until": "valid_until"},
    "ProductEvidence": {**_CREATED_ONLY, "verification_status": "verification_status",
                        "verified_at": "verified_at"},
    "ProductRelation": {**_CREATED_ONLY, "relation_type": "relation_type", "confidence": "confidence"},
    "TrustRecord": {**_CREATED_ONLY, "trust_type": "trust_type",
                    "verification_status": "verification_status", "verified_at": "verified_at"},
    # --- Phase 8
    "CustomerContext": {**_TIMESTAMPS, "purchase_intent": "purchase_intent",
                        "consent_status": "consent_status", "source": "source"},
    "Recommendation": {**_TIMESTAMPS, "status": "status", "response_mode": "response_mode",
                       "final_score": "final_score"},
    # --- Phase 9
    "Installation": {**_TIMESTAMPS, "name": "name", "adapter_type": "adapter_type",
                     "status": "status", "last_seen_at": "last_seen_at"},
    # secret_hash is deliberately absent.
    "InstallationCredential": {**_TIMESTAMPS, "key_id": "key_id", "status": "status",
                               "expires_at": "expires_at", "last_used_at": "last_used_at"},
    "WordPressMapping": {**_TIMESTAMPS, "wordpress_post_id": "wordpress_post_id",
                         "sync_status": "sync_status", "last_synced_at": "last_synced_at"},
    # --- Phase 10
    "CommerceMapping": {**_TIMESTAMPS, "woo_product_id": "woo_product_id", "sku": "sku",
                        "sync_status": "sync_status", "last_synced_at": "last_synced_at"},
    "SyncJob": {**_TIMESTAMPS, "job_type": "job_type", "status": "status",
                "attempts": "attempts", "started_at": "started_at", "completed_at": "completed_at"},
    # --- Phase 12. `response` and `prompt` are excluded: they are free
    # text, expensive to sort, and meaningless as an ordering.
    "VisibilityTest": {**_TIMESTAMPS, "tested_at": "tested_at", "platform": "platform",
                       "test_type": "test_type", "mentioned": "mentioned", "cited": "cited",
                       "recommended": "recommended", "collection_method": "collection_method",
                       "estimated_cost": "estimated_cost"},
    "VisibilityBudget": {**_TIMESTAMPS, "period_key": "period_key",
                         "period_limit": "period_limit", "period_spent": "period_spent"},
    # --- P12-18 / P12-19
    "VisibilityProject": {**_TIMESTAMPS, "name": "name", "status": "status"},
    "VisibilityRun": {**_TIMESTAMPS, "status": "status", "platform": "platform",
                      "started_at": "started_at", "completed_at": "completed_at",
                      "queries_observed": "queries_observed"},
    "VisibilitySnapshot": {**_TIMESTAMPS, "captured_at": "captured_at",
                           "platform": "platform", "observations_tested": "observations_tested"},
    "VisibilityCompetitor": {**_TIMESTAMPS, "name": "name", "domain": "domain",
                             "origin": "origin", "is_approved": "is_approved"},
    "VisibilityEvent": {**_TIMESTAMPS, "observed_at": "observed_at",
                        "event_type": "event_type"},
    # `url`, `title` and `raw` are excluded: free text, expensive to sort.
    "SearchObservation": {**_TIMESTAMPS, "observed_date": "observed_date",
                          "position": "position", "impressions": "impressions",
                          "clicks": "clicks", "ctr": "ctr", "domain": "domain",
                          "data_source": "data_source", "market": "market"},
    # --- Phase 13. `ip_address` and `user_agent` are deliberately absent:
    # sorting a report by a visitor's IP is a lookup dressed as an
    # ordering, and it is exactly the operation a privacy review would
    # object to. Country, path and dwell are the analytical axes.
    "PageView": {**_CREATED_ONLY, "occurred_at": "occurred_at", "path": "path",
                 "actor_type": "actor_type", "dwell_ms": "dwell_ms",
                 "geo_country": "geo_country", "content_type": "content_type",
                 "access_decision": "access_decision", "status_code": "status_code"},
    # `total_views` is what the owner's "least seen to most seen, and the
    # reverse" requirement sorts on; every component count is sortable too
    # so "which page do AI answer engines read most?" is one request.
    "ContentViewDaily": {**_TIMESTAMPS, "view_date": "view_date", "path": "path",
                         "content_type": "content_type",
                         "total_views": "total_views", "human_views": "human_views",
                         "ai_crawler_views": "ai_crawler_views",
                         "ai_answer_views": "ai_answer_views",
                         "agent_views": "agent_views", "search_views": "search_views",
                         "unknown_views": "unknown_views",
                         "blocked_views": "blocked_views",
                         "dwell_ms_total": "dwell_ms_total",
                         "dwell_samples": "dwell_samples"},
    "AiAgent": {**_TIMESTAMPS, "display_name": "display_name", "signature": "signature",
                "actor_type": "actor_type", "declared_purpose": "declared_purpose",
                "confidence": "confidence", "origin": "origin",
                "vendor": "vendor", "first_seen_at": "first_seen_at",
                "last_seen_at": "last_seen_at",
                "observation_count": "observation_count"},
    "AccessPolicy": {**_TIMESTAMPS, "tier": "tier", "actor_type": "actor_type",
                     "purpose": "purpose", "specificity": "specificity"},
    "SearchDemandEvent": {**_CREATED_ONLY, "occurred_at": "occurred_at",
                          "demand_source": "demand_source", "actor_type": "actor_type",
                          "result_count": "result_count", "geo_country": "geo_country"},
}


def sortable_fields(model) -> dict[str, str]:
    return SORTABLE_FIELDS.get(model.__name__, dict(_CREATED_ONLY))


def apply_sort(stmt, model, params, default_field: str, default_dir: SortDirection = SortDirection.DESC):
    """THE canonical sort implementation. Every list endpoint routes through
    this; no service builds its own ordering logic.

    `params=None` or an unset `sort_by` preserves the endpoint's documented
    default ordering exactly, so adding sorting changed no existing
    behaviour.

    A secondary ordering by `id` is always appended. Without it, sorting by
    a non-unique column (status, category, price) gives Postgres freedom to
    return rows in any order within a tie — so page 2 could repeat or skip
    rows from page 1. Deterministic pagination is not optional.
    """
    from fastapi import HTTPException, status as http_status

    allowed = sortable_fields(model)
    field = (params.sort_by if params is not None else None) or default_field
    direction = (params.sort_dir if params is not None and params.sort_dir else None) or (
        default_dir if (params is None or not params.sort_by) else SortDirection.DESC
    )

    if field not in allowed:
        raise HTTPException(
            status_code=http_status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Cannot sort by '{field}'. Allowed values: "
                f"{', '.join(sorted(allowed))}."
            ),
        )

    column = getattr(model, allowed[field])
    ordered = column.asc() if direction == SortDirection.ASC else column.desc()
    # nullslast so rows with a NULL in the sort column do not dominate the
    # first page; stable tiebreak on id.
    return stmt.order_by(ordered.nullslast(), model.id.asc())
