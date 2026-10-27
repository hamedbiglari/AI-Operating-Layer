"""
Enum vocabularies for Phase 1 entities.

These map to native PostgreSQL ENUM types via SQLAlchemy. They cover
closed, well-defined vocabularies (organization status, user role, site
platform/status) per master spec section 10. Open-ended, extensible
vocabularies (e.g. future knowledge_object.object_type) are deliberately
NOT modeled as DB enums — those use plain strings so the list can grow
without a migration, per section 11 ("This list must be extensible").
"""

import enum


class OrganizationStatus(str, enum.Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"
    CANCELLED = "cancelled"


class UserRole(str, enum.Enum):
    OWNER = "owner"
    ADMIN = "admin"
    RESEARCHER = "researcher"
    EDITOR = "editor"
    ANALYST = "analyst"
    VIEWER = "viewer"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INVITED = "invited"
    SUSPENDED = "suspended"
    DEACTIVATED = "deactivated"


class SitePlatform(str, enum.Enum):
    WORDPRESS = "wordpress"
    CUSTOM = "custom"
    OTHER = "other"


class SiteStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ARCHIVED = "archived"


# Roles that may manage organization/user/site settings (used by the
# tenant/authorization guards in app.security).
ADMIN_ROLES = frozenset({UserRole.OWNER, UserRole.ADMIN})

# Roles that may create/edit Knowledge Core data (knowledge objects,
# entities, claims, relationships, gaps). ANALYST and VIEWER are
# read-only for this domain — they consume knowledge, they don't author
# it. Section 10 lists RESEARCHER/EDITOR alongside ADMIN/OWNER as the
# roles with a clear authoring mandate over knowledge content.
KNOWLEDGE_EDITOR_ROLES = frozenset(
    {UserRole.OWNER, UserRole.ADMIN, UserRole.RESEARCHER, UserRole.EDITOR}
)


# ---------------------------------------------------------------------
# Phase 2 — Knowledge Core
#
# Per the same design principle as above: CLOSED vocabularies (a fixed,
# enumerable set of states) become native Postgres ENUM types. OPEN
# vocabularies that the spec explicitly calls "extensible"
# (knowledge_object.object_type, entity.entity_type, claim.predicate/
# claim_type, relationship.predicate) are deliberately plain `String`
# columns on the models themselves, not enums here — adding a new
# object_type or predicate must never require a migration.
# ---------------------------------------------------------------------


class KnowledgeObjectStatus(str, enum.Enum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ClaimStatus(str, enum.Enum):
    """Section 44: 'Do not automatically publish uncertain ... claims
    without appropriate review.' New claims start at DRAFT and must be
    explicitly reviewed before APPROVED."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    DISPUTED = "disputed"
    DEPRECATED = "deprecated"


class ClaimEvidenceStrength(str, enum.Enum):
    """Section 16: 'Extraction confidence is NOT evidence strength.'
    This is the Claim's AGGREGATE assessment, recomputed from every
    linked, VERIFIED Evidence row (Phase 4) by
    app/services/claim_evidence_service.py::recompute_claim_aggregate.
    UNVERIFIED is the correct/default value whenever a Claim has zero
    linked VERIFIED Evidence rows — not a placeholder waiting for Phase
    4, but the honest steady-state for any claim nothing has been
    linked to yet."""

    UNVERIFIED = "unverified"
    INSUFFICIENT = "insufficient"
    WEAK = "weak"
    MODERATE = "moderate"
    STRONG = "strong"
    CONFLICTING = "conflicting"


class RelationshipStatus(str, enum.Enum):
    ACTIVE = "active"
    DISPUTED = "disputed"
    DEPRECATED = "deprecated"


class GraphNodeType(str, enum.Enum):
    """What a Relationship's subject_id/object_id points at. Postgres
    can't hold a real foreign key to 'one of several tables', so this
    tags the target type and the service layer resolves + tenant-checks
    it against the right table (see app/services/relationship_service.py)."""

    ENTITY = "entity"
    KNOWLEDGE_OBJECT = "knowledge_object"


class GapType(str, enum.Enum):
    CONTENT_GAP = "content_gap"
    ENTITY_GAP = "entity_gap"
    CLAIM_GAP = "claim_gap"
    EVIDENCE_GAP = "evidence_gap"
    SOURCE_GAP = "source_gap"
    ACCESS_GAP = "access_gap"
    RELATION_GAP = "relation_gap"
    FRESHNESS_GAP = "freshness_gap"
    CONFLICT_GAP = "conflict_gap"
    RESEARCH_GAP = "research_gap"
    STRUCTURE_GAP = "structure_gap"      # the knowledge object's own shape is incomplete
    RETRIEVAL_GAP = "retrieval_gap"      # the answer exists but is not findable
    UX_GAP = "ux_gap"                    # a person cannot act on what we know
    COMMERCE_GAP = "commerce_gap"        # knowledge exists but no offer connects to it


class GapPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class GapStatus(str, enum.Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"


class GapRecommendedAction(str, enum.Enum):
    SEARCH_MORE = "search_more"
    EXPAND_SEARCH = "expand_search"
    SEARCH_RELATED_ENTITY = "search_related_entity"
    SEARCH_COMPOUND = "search_compound"
    SEARCH_MECHANISM = "search_mechanism"
    SEARCH_RELATED_PLANT = "search_related_plant"
    SEARCH_CLINICAL_DATABASE = "search_clinical_database"
    SEARCH_PRIMARY_STUDIES = "search_primary_studies"
    SEARCH_SECONDARY_STUDIES = "search_secondary_studies"
    REQUEST_FULL_TEXT = "request_full_text"
    REQUEST_USER_SOURCE = "request_user_source"
    REQUEST_PDF = "request_pdf"
    REQUEST_DATASET = "request_dataset"
    REQUEST_EXPERT_REVIEW = "request_expert_review"
    RUN_ANALYSIS = "run_analysis"
    COMPARE_EVIDENCE = "compare_evidence"
    RESOLVE_CONFLICT = "resolve_conflict"
    WAIT_FOR_NEW_EVIDENCE = "wait_for_new_evidence"
    KEEP_GAP_OPEN = "keep_gap_open"


# --- Phase 3: Sources, Documents, Document Chunks ---------------------
#
# source_type (Source) and mime_type (Document) are deliberately plain
# indexed strings, not enums here — same rationale as
# object_type/entity_type/predicate: master spec section 13 lists a
# starting vocabulary (scientific_paper, book, pdf, website, government,
# dataset, supplier_document, lab_report, user_upload, first_party,
# review, news) but new source formats (patents, podcasts, video
# transcripts, etc.) will keep appearing as ingestion grows, and that
# growth must never require a migration. access_status, rights_status,
# and extraction_status ARE closed workflow states, so those are native
# Postgres ENUMs, consistent with every other status field in the schema.


class SourceAccessStatus(str, enum.Enum):
    """Distinguishes 'we know this source exists' from 'we could
    actually read it' (master spec section 13: "Do not assume an
    inaccessible source does not exist")."""

    UNKNOWN = "unknown"
    ACCESSIBLE = "accessible"
    PAYWALLED = "paywalled"
    RESTRICTED = "restricted"
    UNAVAILABLE = "unavailable"


class SourceRightsStatus(str, enum.Enum):
    """A lightweight per-Source rights signal. The full Rights Engine
    (rights_policies, discovery/retrieval/training/bulk/commercial
    access) is Phase 13 — this field only records what's known about
    THIS source's licensing today, so Evidence built on it (Phase 4)
    can inherit an honest provenance trail."""

    UNKNOWN = "unknown"
    OPEN = "open"
    LICENSED = "licensed"
    RESTRICTED = "restricted"
    PROPRIETARY = "proprietary"


class DocumentExtractionStatus(str, enum.Enum):
    """Where a Document is in the ingestion pipeline (master spec
    section 44: INPUT -> PARSER -> CLEANER -> ... -> EMBEDDING).
    Phase 3 implements PENDING -> EXTRACTED synchronously via the
    /documents/{id}/process endpoint; FAILED is reachable if chunking
    fails (e.g. empty content)."""

    PENDING = "pending"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    FAILED = "failed"


# --- Phase 4: Evidence, Claim/Evidence, Conflict foundations -----------
#
# study_type (Evidence) is deliberately a plain indexed string, not an
# enum — same rationale as source_type/entity_type/predicate: master
# spec section 9 lists a starting vocabulary (randomized_controlled_
# trial, meta_analysis, systematic_review, cohort_study, case_control_
# study, case_report, in_vitro, animal_study, observational_study,
# expert_opinion, traditional_use, narrative_review, mechanistic_study)
# but study taxonomies keep growing as ingestion covers more domains,
# and that growth must never require a migration. directness,
# evidence_strength, status, and relation ARE closed, well-defined
# vocabularies, so those are native Postgres ENUMs, consistent with
# every other status/rating field in the schema.


class EvidenceDirectness(str, enum.Enum):
    """GRADE-style dimension: does this evidence apply directly to the
    exact subject/predicate/object it's cited for, or only indirectly
    (a related species, a different dose or population, a surrogate
    outcome)? A closed either/or judgment, unlike study_type's open
    vocabulary."""

    DIRECT = "direct"
    INDIRECT = "indirect"


class EvidenceStrength(str, enum.Enum):
    """GRADE-style certainty rating of ONE piece of evidence (a property
    of the study itself, e.g. a meta-analysis of 20 RCTs vs. a single
    case report). Deliberately a separate enum from Claim's
    evidence_strength (ClaimEvidenceStrength, Phase 2): that one is the
    CLAIM's aggregate, rolled up from every linked Evidence row by
    app/services/claim_evidence_service.py::recompute_claim_aggregate;
    this one rates a single Evidence row in isolation. VERY_LOW is the
    honest default for a freshly-created, unreviewed row rather than
    silently defaulting to something stronger."""

    VERY_LOW = "very_low"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"


class EvidenceStatus(str, enum.Enum):
    """Same review-lifecycle principle as ClaimStatus (section 44): an
    extracted Evidence row must not count toward any Claim's aggregate
    until a human confirms it actually says what it's claimed to say.
    Only VERIFIED evidence is counted by recompute_claim_aggregate."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    VERIFIED = "verified"
    REJECTED = "rejected"


class EvidenceRelation(str, enum.Enum):
    """How a piece of Evidence relates to the specific Claim it's linked
    to via claim_evidence — the raw signal
    recompute_claim_aggregate() reads to detect SUPPORTS-vs-CONTRADICTS
    disagreement on the same Claim (the "Conflict foundations" this
    phase adds). This lives on the LINK, not on Evidence itself, because
    one study can support one claim while contradicting another."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    MIXED = "mixed"
    NEUTRAL = "neutral"


# --- Phase 5: Research Engine ------------------------------------------
#
# task_type (ResearchTask) stays a plain indexed string, same
# open-vocabulary rationale as source_type/study_type: which research
# providers exist (web_search, pubmed_lookup, doi_lookup,
# manual_entry, document_reingest, ...) is expected to keep growing as
# app/integrations/research/ gains real providers (section 18), and
# that growth must never require a migration. mode, and both lifecycle
# statuses, ARE closed, well-defined vocabularies, so those are native
# Postgres ENUMs, consistent with every other status/workflow field.


class ResearchMode(str, enum.Enum):
    """The four research modes the master spec names. Lives on
    ResearchProject, not ResearchTask: a project's mode describes WHY
    the whole investigation exists (its driving methodology), and every
    task under one project shares that project's reason for being —
    duplicating it per-task would just be redundant, unvalidated data
    that could drift from the project's own mode."""

    GAP_DRIVEN = "gap_driven"
    USER_DRIVEN = "user_driven"
    EXPLORATORY = "exploratory"
    CONTINUOUS = "continuous"


class ResearchProjectStatus(str, enum.Enum):
    """A deliberately small, project-level lifecycle - the master spec
    offered DRAFT/QUEUED/RUNNING/COMPLETED/FAILED/CANCELLED/ARCHIVED as
    *possible* states for both ResearchProject and ResearchTask and
    explicitly said not to implement all of them blindly. QUEUED/
    RUNNING/FAILED describe EXECUTION, which happens to individual
    ResearchTasks, not to a project as a whole (a project doesn't
    "run" - its tasks do; see ResearchTaskStatus for that lifecycle).
    A project's own lifecycle is about whether the INVESTIGATION itself
    is still open: DRAFT (being defined) -> ACTIVE (accepting/running
    tasks) -> COMPLETED or CANCELLED -> ARCHIVED (terminal, retained for
    provenance). See app/services/research_project_service.py for the
    validated transition table."""

    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ARCHIVED = "archived"


class ResearchTaskStatus(str, enum.Enum):
    """The execution lifecycle the master spec describes almost
    literally in section 17: "ResearchTask created -> queued -> worker
    execution -> result -> completed / failed". CANCELLED is the one
    addition beyond that literal diagram, needed as an escape hatch for
    a task that should never run (see
    app/services/research_task_service.py for the validated transition
    table). ARCHIVED is deliberately NOT part of this lifecycle -
    archiving is a project-level concept (see ResearchProjectStatus);
    a task's own history stays visible under its project."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ResearchReferenceType(str, enum.Enum):
    """What a ResearchTaskReference's `reference_id` points at. Same
    polymorphic-pointer technique Relationship already established for
    subject_type/object_type (app/models/relationship.py) - deliberately
    a SEPARATE, Phase-5-scoped enum rather than extending the shared
    `graph_node_type` used by Relationship since Phase 2: research
    provenance ("this task referenced/discovered X") and knowledge-graph
    edges ("this entity contains that compound") are different kinds of
    fact, and altering a production enum type already exercised by
    Phase 2-4 tests for a Phase 5-only need was judged riskier than
    adding one small, independently-scoped enum (see
    app/services/research_task_service.py's resolver dict, mirroring
    relationship_service.py's `_resolve_and_check_node`)."""

    SOURCE = "source"
    DOCUMENT = "document"
    EVIDENCE = "evidence"
    CLAIM = "claim"
    KNOWLEDGE_OBJECT = "knowledge_object"
    KNOWLEDGE_GAP = "knowledge_gap"
    # Phase 6 additions (additive only - see migration 0007 and
    # docs/DECISIONS.md ADR-015): a ResearchProject/Task can now trace
    # back to the Query/QueryGroup demand signal that motivated it,
    # using the SAME provenance table Phase 5 already built for exactly
    # this purpose, rather than Phase 6 inventing its own link table.
    QUERY = "query"
    QUERY_GROUP = "query_group"


class ResearchReferenceRole(str, enum.Enum):
    """How a reference relates to the task that recorded it - the two
    questions the research-trail requirement (section 10) actually
    needs answered: was this given TO the task as a starting point, or
    was it FOUND/PRODUCED BY the task's execution?"""

    INPUT = "input"
    OUTPUT = "output"


# --- Phase 6: Query Engine, Intent, Query Clustering --------------------
#
# `source` (Query/QueryProvenance) and `intent_type` (Intent) ARE closed
# vocabularies - section 23 and section 24 both give an explicit,
# finite list ("Possible sources:", "Intent types:") with no "this list
# must be extensible" language the way object_type/entity_type/predicate
# get elsewhere in the spec - so, consistent with the project's own
# rule (closed spec-given vocabulary -> native Postgres ENUM), these are
# ENUMs, not plain strings.


class QuerySource(str, enum.Enum):
    """Section 23's literal, closed source list."""

    SEARCH_CONSOLE = "search_console"
    EXCEL = "excel"
    CSV = "csv"
    SITE_SEARCH = "site_search"
    KEYWORD_TOOL = "keyword_tool"
    CUSTOMER = "customer"
    RESEARCH = "research"
    SERP = "serp"
    AI_TEST = "ai_test"
    MANUAL = "manual"


class QueryStatus(str, enum.Enum):
    """A true 3-state lifecycle (see app/services/query_service.py's
    module docstring for the full reasoning): DISCOVERED is the only
    entry state; CLASSIFIED is set automatically the moment the query
    gets its first Intent row (never a manual PATCH target); ARCHIVED
    is the one genuinely manual action, same soft-deprioritize pattern
    Site/KnowledgeObject already use. "Clustered" and "grouped" are
    deliberately NOT states here - they're derived facts, answered by
    checking for QueryClusterMembership/QueryGroupMembership rows, not
    stored as a status value (a query can be classified AND clustered
    AND grouped simultaneously, which a single-valued status enum
    can't represent without inventing invalid combinations)."""

    DISCOVERED = "discovered"
    CLASSIFIED = "classified"
    ARCHIVED = "archived"


class QueryPriority(str, enum.Enum):
    """Same LOW/MEDIUM/HIGH/CRITICAL shape as GapPriority, but a
    deliberately separate enum: a query's business priority and a
    knowledge gap's priority are different judgments about different
    things, even though they happen to share four labels. Shared by
    both `Query.priority` and `QueryGroup.priority` (unlike
    Evidence/Claim's deliberately split strength enums, there is no
    single-item-vs-aggregate distinction here - both really are "how
    important is this demand", just at two different granularities."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IntentType(str, enum.Enum):
    """Section 24's literal, closed intent-type list."""

    INFORMATION = "information"
    EDUCATION = "education"
    PROBLEM = "problem"
    COMPARISON = "comparison"
    PRICE = "price"
    QUALITY = "quality"
    AUTHENTICITY = "authenticity"
    TRUST = "trust"
    ORIGIN = "origin"
    SUPPLIER = "supplier"
    WHOLESALE = "wholesale"
    LOCAL = "local"
    AVAILABILITY = "availability"
    COMMERCIAL = "commercial"
    TRANSACTIONAL = "transactional"
    RECOMMENDATION = "recommendation"


class IntentClassificationSource(str, enum.Enum):
    """Not a spec-literal field on its own, but required for the
    explainability/multi-intent requirements this phase's instructions
    called for (see app/services/intent_classifier.py) - which actor
    produced this Intent row. RULE_ENGINE is the only automated source
    implemented today; ML_MODEL is a placeholder for a future, real
    classifier (same swappable-provider spirit as EmbeddingProvider/
    ResearchProvider, without building the actual model now)."""

    RULE_ENGINE = "rule_engine"
    MANUAL = "manual"
    ML_MODEL = "ml_model"


# --- Phase 7: Commerce & Product Knowledge -----------------------------
#
# `category`/`brand` (Product) stay plain indexed strings, same
# open-vocabulary rationale as source_type/entity_type/study_type: a
# merchant's category taxonomy is their own and must never require a
# migration to extend. `status`, `availability`, `condition`,
# `relation_type`, `verification_status`, `trust_type`, and
# `subject_type` ARE closed vocabularies (sections 26/27/29/30 each
# give a finite list, or the value set is a fixed workflow), so those
# are native Postgres ENUMs.


class ProductStatus(str, enum.Enum):
    """Section 26's `status`. Deliberately the same four values as
    KnowledgeObjectStatus rather than an invented set: a Product is
    explicitly "a normalized Product Knowledge Object" (section 26), so
    it follows the same publication lifecycle the rest of the knowledge
    layer already uses - DRAFT by default, never auto-published."""

    DRAFT = "draft"
    IN_REVIEW = "in_review"
    PUBLISHED = "published"
    ARCHIVED = "archived"


class ProductProvenance(str, enum.Enum):
    """Where a Product row's data actually came from. Not in section
    26's literal field list; added because the Phase 7 brief requires
    the system to "distinguish these origins" and to "not represent all
    information as equally authoritative" - a merchant-typed product
    and a WooCommerce-synced product are not equally authoritative
    about the same field, and without this column that distinction is
    unrecoverable after import. See docs/DECISIONS.md ADR-021."""

    MERCHANT = "merchant"
    WOOCOMMERCE = "woocommerce"
    SUPPLIER = "supplier"
    IMPORTED_DOCUMENT = "imported_document"
    RESEARCH = "research"
    EXTERNAL = "external"


class OfferAvailability(str, enum.Enum):
    """Section 27's `availability`. Values follow schema.org's
    ItemAvailability vocabulary (the same vocabulary search engines and
    AI shopping agents already consume) rather than an invented set -
    section 27's whole stated purpose is future marketplace/seller
    interoperability."""

    IN_STOCK = "in_stock"
    OUT_OF_STOCK = "out_of_stock"
    PREORDER = "preorder"
    BACKORDER = "backorder"
    DISCONTINUED = "discontinued"


class OfferCondition(str, enum.Enum):
    """Section 27's `condition`."""

    NEW = "new"
    USED = "used"
    REFURBISHED = "refurbished"


class ProductRelationType(str, enum.Enum):
    """Section 29's literal, closed relation-type list."""

    ALTERNATIVE = "alternative"
    COMPLEMENTARY = "complementary"
    SIMILAR = "similar"
    FREQUENTLY_BOUGHT_TOGETHER = "frequently_bought_together"
    REPLACEMENT = "replacement"


class VerificationStatus(str, enum.Enum):
    """Shared by product_evidence (section 28) and trust_records
    (section 30) - both spec sections name a `verification_status`
    field for the same purpose (has a human confirmed this evidence
    actually supports this claim?), so they share one enum rather than
    two identical ones.

    UNVERIFIED is the only valid entry state. Section 28 is explicit:
    "Do not allow unsupported marketing claims to be presented as
    verified evidence" - so a newly-created product_evidence or
    trust_record row is NEVER born VERIFIED, exactly as Claim and
    Evidence are never born APPROVED/VERIFIED in Phases 2/4."""

    UNVERIFIED = "unverified"
    PENDING_REVIEW = "pending_review"
    VERIFIED = "verified"
    REJECTED = "rejected"


class TrustType(str, enum.Enum):
    """Section 30's trust chain, expressed as the kind of trust a
    record asserts. Derived from the chain the spec draws (Website ->
    Business Identity -> Supplier -> Origin -> Product -> Quality
    Evidence -> Testing -> Reviews -> Policies -> Customer Experience);
    section 30 gives no literal enum, so these name the chain's own
    stages rather than inventing an unrelated vocabulary."""

    BUSINESS_IDENTITY = "business_identity"
    SUPPLIER = "supplier"
    ORIGIN = "origin"
    QUALITY = "quality"
    TESTING = "testing"
    CERTIFICATION = "certification"
    POLICY = "policy"
    REVIEW = "review"


class TrustSubjectType(str, enum.Enum):
    """What a trust_record's `subject_id` points at (section 30's
    `subject_type`). Same polymorphic-pointer technique Relationship
    (Phase 2) and ResearchTaskReference (Phase 5) already use, and -
    per the reasoning recorded in ADR-014 - deliberately its own
    Phase-7-scoped enum rather than an extension of a shared one:
    trust subjects and knowledge-graph nodes are different kinds of
    thing, and altering a production enum already exercised by earlier
    phases' tests is riskier than adding a small scoped one."""

    ORGANIZATION = "organization"
    # SITE added in Phase 9 (B2): section 30's trust chain begins at
    # "Website", and Phase 9 introduces site-scoped adapter
    # installations that may carry site-level trust assertions.
    # Additive enum extension, same pattern as ADR-018.
    SITE = "site"
    PRODUCT = "product"
    CLAIM = "claim"


# --- Phase 8: Customer Context & Recommendation -------------------------
#
# Section 32/33/34. `topic` and `product_interest` on CustomerContext
# stay open strings (a merchant's topic vocabulary is their own);
# everything below is a closed, spec-named vocabulary and therefore a
# native Postgres ENUM, consistent with every prior phase.


class ContextType(str, enum.Enum):
    """Section 32's `context_type` - where this context came from.
    ANONYMOUS is the default and the privacy-safe one: a context with
    no customer_id and no session_id is still perfectly usable for a
    single recommendation call."""

    ANONYMOUS = "anonymous"
    SESSION = "session"
    CUSTOMER = "customer"


class ContextSource(str, enum.Enum):
    """Section 32's `source`. AI_ASSISTANT exists so an integration can
    say where a context came from, but section 32 is explicit that raw
    external AI conversations must NOT be stored by default - so this
    records the CHANNEL, never the transcript."""

    WEB = "web"
    SITE_SEARCH = "site_search"
    AI_ASSISTANT = "ai_assistant"
    MERCHANT = "merchant"
    API = "api"


class PurchaseIntent(str, enum.Enum):
    """Section 32's `purchase_intent` - how close this person is to
    buying, which directly gates whether product recommendation is
    appropriate at all (section 34: "Do not push products when the
    user's intent does not justify it")."""

    NONE = "none"
    RESEARCHING = "researching"
    COMPARING = "comparing"
    READY = "ready"


class NeedLevel(str, enum.Enum):
    """Shared by `evidence_need` and `trust_need` (section 32). How
    much this person needs evidence/trust established before a
    recommendation is appropriate for them - a researcher checking
    authenticity has a HIGH evidence_need; someone reordering a known
    product has LOW."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"


class PriceSensitivity(str, enum.Enum):
    """Section 32's `price_sensitivity`. UNKNOWN is the default and is
    deliberately distinct from LOW - not knowing someone's price
    sensitivity is not the same as knowing they don't care."""

    UNKNOWN = "unknown"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ConsentStatus(str, enum.Enum):
    """Section 32: "Context must be consent-aware and privacy-safe."
    NOT_REQUIRED covers a genuinely anonymous, non-persisted-identity
    context; GRANTED/WITHDRAWN cover contexts tied to an identifiable
    customer. WITHDRAWN contexts are excluded from recommendation by a
    hard gate, never merely down-ranked."""

    NOT_REQUIRED = "not_required"
    GRANTED = "granted"
    WITHDRAWN = "withdrawn"


class ResponseMode(str, enum.Enum):
    """Section 34's literal five modes. Determines whether product
    recommendation is appropriate at all, BEFORE any scoring happens -
    see app/services/recommendation_policy.py."""

    EDUCATE = "educate"
    COMPARE = "compare"
    REASSURE = "reassure"
    RECOMMEND = "recommend"
    TRANSACT = "transact"


class RecommendationStatus(str, enum.Enum):
    """The outcome of one product's evaluation.

    NO_RECOMMENDATION is a first-class result, not a failure: section
    34 forbids pushing products when intent doesn't justify it, and a
    system that cannot abstain will always find something to sell.
    NOT_ELIGIBLE is different - it means a hard gate rejected this
    specific product (wrong tenant, unpublished, no purchasable offer),
    whereas NO_RECOMMENDATION means the engine declined to recommend
    anything at all for this request."""

    NOT_ELIGIBLE = "not_eligible"
    NO_RECOMMENDATION = "no_recommendation"
    RECOMMENDED_WITH_CAVEAT = "recommended_with_caveat"
    RECOMMENDED = "recommended"


class SignalState(str, enum.Enum):
    """The tri-state every evidence/trust signal carries alongside its
    numeric score - the single most important semantic in this phase.

    UNKNOWN ("nothing established yet") is NOT the same as NEGATIVE
    ("actively contradicted or rejected"). A product with no evidence
    is not a bad product; it is an unevaluated one. Collapsing the two
    into a low number would silently punish new products and reward
    whoever uploaded the most paperwork, which is the exact failure
    mode sections 28/30 exist to prevent. Scores alone cannot express
    this distinction, which is why every signal carries both."""

    UNKNOWN = "unknown"
    PARTIAL = "partial"
    ESTABLISHED = "established"
    CONFLICTING = "conflicting"
    NEGATIVE = "negative"


# --- Phase 9: Machine Identity & Adapter Integration --------------------
#
# These belong to the INTEGRATION domain, not to WordPress. Nothing here
# names a WordPress concept except `AdapterType.WORDPRESS`, which is one
# value among several deliberately-anticipated ones - see ADR-036.


class AdapterType(str, enum.Enum):
    """What KIND of machine client an Installation represents.

    WordPress is one value, not the model. A future MCP server, REST
    integration, or another CMS adapter is a different value on the
    same model - which is the point: the identity layer must not have
    to be rebuilt for the second adapter. `OTHER` exists so an
    unanticipated integration can be registered without a migration."""

    WORDPRESS = "wordpress"
    REST = "rest"
    MCP = "mcp"
    OTHER = "other"


class InstallationStatus(str, enum.Enum):
    """SUSPENDED and REVOKED are deliberately distinct: suspension is
    reversible (a merchant pauses an integration, or ops throttles a
    misbehaving one), revocation is terminal. Collapsing them would
    make "we turned it off temporarily" indistinguishable from "this
    installation must never authenticate again"."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    REVOKED = "revoked"


class CredentialStatus(str, enum.Enum):
    """A credential's own lifecycle, separate from its installation's.
    Rotation creates a NEW credential and marks the old one ROTATED
    rather than deleting it, so an audit log entry referencing a
    retired key still resolves to something."""

    ACTIVE = "active"
    ROTATED = "rotated"
    REVOKED = "revoked"


class AdapterScope(str, enum.Enum):
    """Capability grants on a credential. Deliberately coarse and few:
    a large permission matrix invented before anyone needs it is
    guesswork. These four cover what a Phase 9 adapter actually does.

    Note what is NOT here and cannot be granted: there is no scope that
    lets an adapter verify evidence, verify trust, publish a product,
    or write a recommendation. Those are Core decisions (sections
    28/30/44), and an adapter must not be able to reach them at all -
    not even with a misconfigured scope."""

    MAPPINGS_READ = "mappings:read"
    MAPPINGS_WRITE = "mappings:write"
    CATALOG_READ = "catalog:read"
    RECOMMENDATIONS_READ = "recommendations:read"
    # Phase 10. COMMERCE_WRITE is deliberately narrow: it permits offer
    # price/stock sync and commerce mapping, and nothing else. There is
    # still no scope - and no code path - that can publish a product,
    # verify evidence or verify trust.
    COMMERCE_READ = "commerce:read"
    COMMERCE_WRITE = "commerce:write"
    # Phase 13 (ADR-076). TELEMETRY_WRITE lets an adapter report what
    # visited it; TELEMETRY_READ lets it read back its own aggregates to
    # render a dashboard. Neither can create knowledge, evidence, claims
    # or products - the Phase 9 rule that no scope reaches a Core
    # judgment is unchanged.
    TELEMETRY_WRITE = "telemetry:write"
    TELEMETRY_READ = "telemetry:read"
    # Phase 11. The agent-facing read surface. Deliberately READ-ONLY:
    # there is no ai:write, because an external AI system must never be
    # able to author knowledge, evidence or trust in someone's tenant.
    AI_QUERY = "ai:query"
    KNOWLEDGE_READ = "knowledge:read"


class MappedObjectType(str, enum.Enum):
    """Which Core object a WordPress post is mapped to (master spec
    section 39's `object_type`). Same polymorphic-pointer technique as
    Relationship/ResearchTaskReference/TrustRecord, resolved and
    tenant-checked in the service layer."""

    KNOWLEDGE_OBJECT = "knowledge_object"
    PRODUCT = "product"


class SyncStatus(str, enum.Enum):
    """Section 39's `sync_status`. STALE is the interesting one: it
    means Core has changed since the last successful push, so the
    WordPress representation is known to be behind. That is different
    from FAILED (a push was attempted and errored) and from PENDING
    (never pushed yet) - collapsing them would lose the distinction
    between "out of date" and "broken"."""

    PENDING = "pending"
    SYNCED = "synced"
    STALE = "stale"
    FAILED = "failed"


# --- Phase 10: WooCommerce / commerce mapping & sync jobs ---------------


class CommerceSyncStatus(str, enum.Enum):
    """Section 40's `sync_status`, mirroring Phase 9's SyncStatus shape but
    kept as its OWN enum rather than shared.

    Reason: `wordpress_mappings.sync_status` describes a content
    projection, `commerce_mappings.sync_status` describes a commercial
    record. They happen to share four words today; if either needs a fifth
    (say CONFLICTED for a price disagreement) it must be able to get one
    without silently widening the other's contract. Sharing an enum across
    two domains is how vocabularies drift into each other."""

    PENDING = "pending"
    SYNCED = "synced"
    STALE = "stale"
    FAILED = "failed"


class SyncJobType(str, enum.Enum):
    """Section 41's `job_type`. Deliberately a closed enum, not an open
    string: a worker must be able to refuse a job type it does not
    recognise, and an open vocabulary would mean silently dropping work
    whose name was mistyped."""

    COMMERCE_PRODUCT_SYNC = "commerce_product_sync"
    COMMERCE_OFFER_SYNC = "commerce_offer_sync"
    CONTENT_MAPPING_SYNC = "content_mapping_sync"
    # Phase 3 completion (P12-02): document conversion/OCR is heavy and must
    # not run in an HTTP request. It reuses SyncJob rather than introducing a
    # second job model - the contract's "extend the canonical model" rule.
    DOCUMENT_INGESTION = "document_ingestion"


class SyncJobStatus(str, enum.Enum):
    """Section 41's `status`.

    DEAD_LETTER is one value beyond the obvious set, and it earns its place:
    without it, a job that has exhausted its retries is indistinguishable
    from one that failed once and will be retried. An operator needs to know
    which jobs have stopped trying, because those are the ones that need a
    human. See ADR-051."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    # RETRYING is distinct from FAILED: it says a retry is scheduled, so an
    # operator can tell work that is still moving from work that has
    # stopped. DEAD_LETTER remains the terminal "stopped trying" state.
    RETRYING = "retrying"
    DEAD_LETTER = "dead_letter"
    CANCELLED = "cancelled"


class SyncJobStageKey(str, enum.Enum):
    """A stage of a document-ingestion job, as the Processing view shows it (Step 7C-3)."""

    UPLOAD = "upload"
    SECURITY = "security"
    CONVERSION = "conversion"
    STRUCTURE = "structure"
    OCR = "ocr"
    CHUNKING = "chunking"
    EVIDENCE = "evidence"
    KNOWLEDGE = "knowledge"


class SyncJobStageState(str, enum.Enum):
    """NOT_TRACKED says the backend kept no record of the stage, rather than guessing one."""

    PENDING = "pending"
    ACTIVE = "active"
    DONE = "done"
    FAILED = "failed"
    NOT_TRACKED = "not_tracked"


# --- Phase 12: AI Visibility (master spec section 31) -------------------


class VisibilityPlatform(str, enum.Enum):
    """Section 31's platform list, plus OTHER so an unanticipated platform
    can be recorded without a migration. Closed otherwise: a worker and a
    dashboard both need to know the vocabulary."""

    GOOGLE = "google"
    BING = "bing"
    CHATGPT = "chatgpt"
    GEMINI = "gemini"
    PERPLEXITY = "perplexity"
    COPILOT = "copilot"
    OTHER = "other"


class VisibilityTestType(str, enum.Enum):
    """What KIND of probe produced this observation. Section 31 names a
    `test_type` without enumerating values."""

    DIRECT_QUERY = "direct_query"
    BRAND_QUERY = "brand_query"
    PRODUCT_QUERY = "product_query"
    COMPARISON_QUERY = "comparison_query"
    CITATION_CHECK = "citation_check"


class SignalPresence(str, enum.Enum):
    """THE most important enum in this phase.

    Section 31 lists `mentioned`, `cited`, `recommended`, `product_present`
    and `url_present` — which read naturally as booleans. They must not be
    booleans, because `false` would conflate two entirely different facts:

        "we looked, and it was not cited"        (a real negative finding)
        "we did not check whether it was cited"  (no finding at all)

    A dashboard that averages those together produces a number that is
    simply wrong. This is the same UNKNOWN-vs-NEGATIVE rule as ADR-028
    (recommendation signals) and ADR-057 (agent responses), applied to
    observation. See ADR-061.

    NOT_CHECKED is the default, because an observation that did not examine
    a signal has said nothing about it."""

    PRESENT = "present"
    ABSENT = "absent"
    NOT_CHECKED = "not_checked"


class VisibilityCollectionMethod(str, enum.Enum):
    """How the observation was obtained. Recorded on every row because an
    observation's trustworthiness is inseparable from its provenance: a
    human pasting a ChatGPT answer and an automated API call are not
    equally reliable, and a dashboard must be able to tell them apart.

    MANUAL_PASTE is expected to dominate early: most AI platforms have no
    API that permits automated visibility probing, and pretending otherwise
    would be the easiest way to fabricate data."""

    MANUAL_PASTE = "manual_paste"
    PLATFORM_API = "platform_api"
    AUTOMATED_BROWSER = "automated_browser"
    IMPORTED = "imported"



# --- Phase 3 completion: Document Intelligence (ADR-065) ----------------


class DocumentConversionStatus(str, enum.Enum):
    """Outcome of normalization. UNSUPPORTED and FAILED are distinct: one is
    a missing capability, the other a bad file, and an operator responds to
    them differently. EMPTY is separate again - it is how a malformed PDF
    that MarkItDown reports as the string "None" is recorded honestly."""

    PENDING = "pending"
    SUCCEEDED = "succeeded"
    EMPTY = "empty"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class DocumentExtractionLevel(int, enum.Enum):
    """Which cost tier actually ran. Stored, never inferred, so a reader can
    tell cheap extraction from expensive interpretation."""

    NORMALIZE = 1
    STRUCTURE = 2
    OCR = 3
    VISION = 4


class DocumentAssetStatus(str, enum.Enum):
    DETECTED_NOT_EXTRACTED = "detected_not_extracted"
    EXTRACTED = "extracted"
    FAILED = "failed"


class DocumentOcrStatus(str, enum.Enum):
    """NO_TEXT_FOUND and UNAVAILABLE must never collapse: "we read it and it
    had no text" is a finding, "we had no OCR engine" is not."""

    NOT_ATTEMPTED = "not_attempted"
    SUCCEEDED = "succeeded"
    NO_TEXT_FOUND = "no_text_found"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"


# --- Phase 12: P12-18 Visibility infrastructure / P12-19 Search ---------


class VisibilityProjectStatus(str, enum.Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    ARCHIVED = "archived"


class VisibilityRunStatus(str, enum.Enum):
    """Run lifecycle. PARTIAL is the value that earns its place: a run over
    twenty queries where three providers failed is neither SUCCEEDED nor
    FAILED, and forcing it into either loses the distinction between
    "everything worked" and "most things worked"."""

    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ProviderOutcome(str, enum.Enum):
    """How a provider call ended (P12-19 §27).

    UNAVAILABLE, FAILED, RATE_LIMITED and AUTH_REQUIRED are separate
    because converting any of them into "no results" is semantically
    false - it turns an absence of measurement into a measurement of
    absence."""

    SUCCESS = "success"
    PARTIAL = "partial"
    UNAVAILABLE = "unavailable"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    AUTH_REQUIRED = "auth_required"
    NOT_CONFIGURED = "not_configured"


class CompetitorOrigin(str, enum.Enum):
    """How a competitor entered the set. A brand that merely appeared in an
    answer is a CANDIDATE, not a competitor - declaring it one silently
    would put words in the merchant's mouth."""

    MERCHANT_DEFINED = "merchant_defined"
    SYSTEM_DISCOVERED = "system_discovered"
    USER_APPROVED = "user_approved"


class VisibilityEventType(str, enum.Enum):
    """Observed CHANGES between snapshots. Every name is descriptive, not
    causal: `RANK_CHANGED`, never `RANK_IMPROVED_BY_SEO`."""

    FIRST_OBSERVED = "first_observed"
    DISAPPEARED = "disappeared"
    MENTION_CHANGED = "mention_changed"
    CITATION_CHANGED = "citation_changed"
    RECOMMENDATION_CHANGED = "recommendation_changed"
    PRODUCT_APPEARED = "product_appeared"
    PRODUCT_DISAPPEARED = "product_disappeared"
    URL_APPEARED = "url_appeared"
    URL_DISAPPEARED = "url_disappeared"
    RANK_CHANGED = "rank_changed"
    COMPETITOR_APPEARED = "competitor_appeared"
    COMPETITOR_DISAPPEARED = "competitor_disappeared"


class SearchSurface(str, enum.Enum):
    """Search surfaces are distinct from AI surfaces (P12-18 §12).

    Search yields position/URL/result; AI yields mention/citation/
    recommendation. They may share query and market metadata, but their
    observation semantics never merge."""

    GOOGLE_WEB = "google_web"
    GOOGLE_IMAGES = "google_images"
    GOOGLE_NEWS = "google_news"
    BING_WEB = "bing_web"
    OTHER = "other"


class SearchDataSource(str, enum.Enum):
    """Where a search observation came from. SEARCH_CONSOLE is first-party
    performance data; SERP is an external observation of a result page.
    They answer different questions and must stay distinguishable."""

    SEARCH_CONSOLE = "search_console"
    SERP_PROVIDER = "serp_provider"
    MANUAL_IMPORT = "manual_import"
    FIXTURE = "fixture"


class SearchResultType(str, enum.Enum):
    ORGANIC = "organic"
    FEATURED_SNIPPET = "featured_snippet"
    KNOWLEDGE_PANEL = "knowledge_panel"
    LOCAL_PACK = "local_pack"
    SHOPPING = "shopping"
    VIDEO = "video"
    AI_OVERVIEW = "ai_overview"
    OTHER = "other"


# ===========================================================================
# Phase 13 — Analytics, Demand Intelligence and AI Access Control
# (ADR-076 … ADR-081)
#
# WHY THESE LIVE HERE AND NOT IN THE PLUGIN
#
# `AIOL_Actors` (plugin, ADR-046) already classifies actors, and Phase 13
# does NOT introduce a second classifier. What it does is move the
# *vocabulary* into Core, because Core is the source of truth (§52) and a
# merchant with two sites must see one agent list, not two. The plugin
# keeps its own local constants for the request-time hot path and maps them
# onto these values on the wire; a conformance test asserts the two sets
# are identical, so they cannot drift silently.
# ===========================================================================


class ActorType(str, enum.Enum):
    """WHO made the request. Mirrors `AIOL_Actors` exactly (ADR-076).

    Deliberately NOT a bot/human boolean: a crawler indexing for later, an
    AI answering a live user question, and an agent acting on a user's
    behalf have three different commercial meanings, and the access
    policy the merchant wants to set differs for each.
    """

    HUMAN = "human"
    SEARCH_CRAWLER = "search_crawler"
    AI_CRAWLER = "ai_crawler"
    AI_USER_AGENT = "ai_user_agent"
    AGENT_TOOL = "agent_tool"
    UNKNOWN = "unknown"


class ActorConfidence(str, enum.Enum):
    """HOW SURE we are. A User-Agent is a claim, not an identity.

    `VERIFIED` is reachable only by reverse-DNS or published IP-range
    confirmation. Nothing in Phase 13 sets it; it exists so that a later
    verifier has a value to write and so a report can say "self-reported"
    honestly rather than presenting a header match as fact.
    """

    DETECTED = "detected"
    PROBABLE = "probable"
    VERIFIED = "verified"
    UNKNOWN = "unknown"


class AccessPurpose(str, enum.Enum):
    """WHY the agent is fetching. This is the axis the merchant actually
    wants to price, and it is the axis Cloudflare's AI controls use too:
    a merchant who is happy to be quoted in an answer may still refuse to
    be scraped into a training corpus.

    `UNKNOWN` is a real value, not a placeholder. Most agents do not
    declare purpose; guessing one would manufacture a fact.
    """

    TRAINING = "training"          # corpus collection for model training
    SEARCH_INDEXING = "search_indexing"
    ANSWERING = "answering"        # fetching to answer a live user question
    AGENT_ACTION = "agent_action"  # acting on a user's behalf (buy, book)
    PREVIEW = "preview"            # link unfurling / preview cards
    UNKNOWN = "unknown"


class AccessTier(str, enum.Enum):
    """The merchant's decision for a (agent, purpose) pair.

    `UNSET` is distinct from `FREE`. A policy row that has never been
    decided must not be reported as "the merchant allows this"; the
    dashboard shows it as *Not decided* and offers the choice.
    """

    FREE = "free"
    PAID = "paid"
    FORBIDDEN = "forbidden"
    UNSET = "unset"


class AccessDecision(str, enum.Enum):
    """The evaluated outcome for one request. Recorded on the page view so
    a report can answer "what did we actually do to this agent?" rather
    than "what does the policy table say today?" — policies change, history
    must not."""

    ALLOWED = "allowed"
    PAYMENT_REQUIRED = "payment_required"   # HTTP 402
    BLOCKED = "blocked"                     # HTTP 403
    NOT_CONFIGURED = "not_configured"       # no policy matched; allowed, and said so


class AgentRegistrationOrigin(str, enum.Enum):
    """Where an `AiAgent` row came from.

    `DISCOVERED` is the important one and is why this registry is NOT an
    allow-list: an agent nobody has ever heard of gets a row the first
    time it arrives, so the merchant can see it and decide. A registry
    that only contains agents somebody pre-approved cannot answer "who is
    visiting my site?", which is the question being asked.
    """

    SEEDED = "seeded"          # shipped signature list
    DISCOVERED = "discovered"  # first seen in live traffic
    MANUAL = "manual"          # merchant added it


class SearchDemandSource(str, enum.Enum):
    """Where a recorded search came from.

    Kept separate from Phase 12's `SearchDataSource` (Search Console /
    SERP provider) because these are observations of OUR OWN surface, not
    of a search engine's results page. Mixing them would make "impressions"
    and "on-site searches" share a column with no way to tell them apart.
    """

    ONSITE_SEARCH = "onsite_search"      # visitor used the site's search box
    AGENT_QUERY = "agent_query"          # agent supplied a query parameter
    REFERRER_QUERY = "referrer_query"    # query recoverable from the referrer
    ADAPTER_REPORTED = "adapter_reported"


class GeoResolutionMethod(str, enum.Enum):
    """HOW the location was obtained. Required, never defaulted silently.

    There is no `IP_DATABASE` value because no IP-geolocation database is
    bundled or called (ADR-079). `EDGE_HEADER` means an upstream CDN
    already resolved it and told us; `NONE` means we do not know, and the
    dashboard says *Not available* rather than drawing an empty map pin.
    """

    EDGE_HEADER = "edge_header"      # CF-IPCountry and friends
    ADAPTER_REPORTED = "adapter_reported"
    NONE = "none"


# ---------------------------------------------------------------------------
# Phase 17 — canonical AI execution (Phase 16 architecture C, locked).
# Stored as CHECK-constrained VARCHAR, not native Postgres ENUM types: the
# arc/parent vocabulary must grow one value at a time as each domain starts
# invoking a model, and migration 0016 showed how brittle native-enum
# extension is in this codebase.
# ---------------------------------------------------------------------------
class AIExecutionStatus(str, enum.Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RATE_LIMITED = "rate_limited"
    CANCELLED = "cancelled"
    # A row found still RUNNING long after any provider timeout could have
    # elapsed (worker crash). The provider may or may not have executed and
    # billed the call — the outcome is genuinely unknown, so it is neither
    # FAILED nor SUCCEEDED, and its cost stays NULL.
    ABANDONED = "abandoned"


AI_EXECUTION_TERMINAL_STATUSES = frozenset(
    s for s in AIExecutionStatus if s is not AIExecutionStatus.RUNNING
)


class AIOperationType(str, enum.Enum):
    CHAT = "chat"
    COMPLETION = "completion"
    EMBEDDING = "embedding"
    RERANK = "rerank"
    VISION = "vision"


class AIAttemptReason(str, enum.Enum):
    RETRY = "retry"
    MANUAL_RETRY = "manual_retry"
    PROVIDER_FALLBACK = "provider_fallback"
    MODEL_FALLBACK = "model_fallback"
    # AI Center: same provider, a different ACCOUNT (provider ≠ account ≠ model).
    ACCOUNT_FALLBACK = "account_fallback"


class AIParentType(str, enum.Enum):
    """Exclusive-arc discriminator. One value per domain that ACTUALLY
    invokes a model — added together with its typed FK column, never
    speculatively (Phase 16 ADR-P16-AI-004)."""

    VISIBILITY_RUN = "visibility_run"
    # AI Center multi-item processing job (REQ-AIC-004); arc column ai_job_id.
    AI_JOB = "ai_job"
