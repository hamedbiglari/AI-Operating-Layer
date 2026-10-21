"""
Agent-facing REST interface (Phase 11; master spec §62 "AI/REST
interfaces", §63 "REST API = primary interface").

WHAT THIS SURFACE IS FOR

The whole architecture exists so that an external AI system can ask
"what do you actually know, and how well do you know it?" and get an
answer that is honest about its own limits. These endpoints are that
question, made callable.

THREE PROPERTIES, each enforced structurally rather than by convention:

1. **READ-ONLY.** There is no POST that writes knowledge, evidence or
   trust. `ai:query` and `knowledge:read` are the only scopes involved and
   neither has a write counterpart. An external AI cannot author facts in
   someone else's tenant because the route does not exist.

2. **UNVERIFIED IS NEVER PRESENTED AS VERIFIED.** `/trust` returns only
   records where BOTH the trust record and its underlying Evidence are
   VERIFIED (ADR-032's two-layer rule, reused via the Commerce contract
   rather than reimplemented). Draft and rejected records are counted in
   `coverage`, never listed as facts.

3. **ABSENCE IS REPORTED, NOT OMITTED.** Every response carries a
   `coverage` block describing what the answer does not cover. An agent
   that receives only positive facts will present them as the whole
   picture; this is how the API states the edge of what it knows.

Section 33's constraint is honoured literally: no numeric score is
returned to an external consumer. `/ask` returns rank position and states,
because a 0-1 float would be quoted back as "9.2/10" the moment it left
the building.
"""

from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.prompt_safety import outbound
from app.contracts import commerce as commerce_contract
from app.db.session import get_db
from app.models.claim import Claim
from app.models.enums import (
    AdapterScope,
    ClaimEvidenceStrength,
    ClaimStatus,
    MappedObjectType,
    NeedLevel,
    ResponseMode,
    SignalState,
    VerificationStatus,
)
from app.models.knowledge_object import KnowledgeObject
from app.models.offer import Offer
from app.models.wordpress_mapping import WordPressMapping
from app.models.trust_record import TrustRecord
from app.schemas.ai import (
    AIAnswerProduct,
    AIAnswerResponse,
    AIAskRequest,
    AICapabilityDescriptor,
    AIClaim,
    AICoverage,
    AIKnowledgeResponse,
    AITrustRecord,
    AITrustResponse,
)
from app.security.machine_identity import MachineIdentity, get_machine_identity
from app.security.rate_limit import rate_limited
from app.services import recommendation_service

def _content_policy(response: Response) -> None:
    """Every answer to an external agent says, in a header, that its text fields are data (ADR-126)."""
    from app.ai.prompt_safety import OUTBOUND_POLICY_HEADER

    response.headers[OUTBOUND_POLICY_HEADER[0]] = OUTBOUND_POLICY_HEADER[1]


router = APIRouter(prefix="/ai", tags=["ai-interface"], dependencies=[Depends(_content_policy)])


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require(identity: MachineIdentity, scope: AdapterScope) -> None:
    if not identity.has_scope(scope):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Credential lacks required scope: {scope.value}",
        )


@router.get("/capabilities", response_model=AICapabilityDescriptor)
def capabilities() -> AICapabilityDescriptor:
    """Self-describing manifest — the seam an MCP server would wrap.

    §63 fixes MCP as a *future/secondary* interface, so Phase 11 does not
    build an MCP server (ADR-058). It builds the thing one would need: a
    machine-readable statement of what this API answers, what it refuses,
    and what its honesty guarantees are. Unauthenticated on purpose: a
    client must be able to discover the contract before holding a
    credential.
    """
    return AICapabilityDescriptor(
        api_version="v1",
        interface="rest",
        capabilities=[
            {
                "name": "knowledge.get",
                "method": "GET",
                "path": "/api/v1/ai/knowledge/{knowledge_object_id}",
                "description": "Claims about a knowledge object, each with its evidence standing.",
                "scope": AdapterScope.KNOWLEDGE_READ.value,
            },
            {
                "name": "trust.get",
                "method": "GET",
                "path": "/api/v1/ai/products/{product_id}/trust",
                "description": "Verified trust records for a product. Unverified records are counted, never listed.",
                "scope": AdapterScope.KNOWLEDGE_READ.value,
            },
            {
                "name": "ask",
                "method": "POST",
                "path": "/api/v1/ai/ask",
                "description": "Product suggestions for a stated need, or an explicit refusal to suggest.",
                "scope": AdapterScope.AI_QUERY.value,
            },
        ],
        guarantees=[
            "Absence of evidence is reported as UNKNOWN, never as a negative finding.",
            "Only evidence verified at BOTH the record and source level is presented as verified.",
            "Every response states what it does not cover, in a 'coverage' block.",
            "A refusal to answer is a successful response, not an error.",
            "Tenant is derived from the credential; it cannot be supplied by a caller.",
        ],
        refusals=[
            "No numeric score or rating is returned; internal decision scores are not external ratings.",
            "No write access to knowledge, evidence, trust or products exists on this interface.",
            "No claim is returned as fact on the strength of an unverified or rejected source.",
            "No customer conversation content is accepted or stored.",
        ],
    )


@router.get("/knowledge/{knowledge_object_id}", response_model=AIKnowledgeResponse)
def get_knowledge(
    knowledge_object_id: UUID,
    identity: MachineIdentity = Depends(rate_limited(limit=300)),
    db: Session = Depends(get_db),
) -> AIKnowledgeResponse:
    """What Core knows about one knowledge object, with each claim's
    evidence standing attached.

    Claims are returned regardless of status, because hiding DRAFT claims
    would misrepresent the picture as more settled than it is — but every
    claim carries its `status` and `evidence_strength`, and the `coverage`
    block counts them, so an agent can weight them correctly rather than
    treating all returned claims as equal.
    """
    _require(identity, AdapterScope.KNOWLEDGE_READ)

    ko = db.execute(
        select(KnowledgeObject).where(
            KnowledgeObject.id == knowledge_object_id,
            KnowledgeObject.organization_id == identity.organization_id,
        )
    ).scalar_one_or_none()
    if ko is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Knowledge object not found")

    claims = db.execute(
        select(Claim).where(
            Claim.organization_id == identity.organization_id,
            Claim.knowledge_object_id == knowledge_object_id,
        )
    ).scalars().all()

    out_claims: list[AIClaim] = []
    approved = disputed = unverified = 0
    for claim in claims:
        is_disputed = claim.evidence_strength == ClaimEvidenceStrength.CONFLICTING
        if claim.status == ClaimStatus.APPROVED:
            approved += 1
        if is_disputed or claim.status == ClaimStatus.DISPUTED:
            disputed += 1
        if claim.evidence_strength == ClaimEvidenceStrength.UNVERIFIED:
            unverified += 1

        out_claims.append(
            AIClaim(
                claim_id=claim.id,
                predicate=claim.predicate,
                object_value=outbound(claim.object_value),   # cleaned for external agents (ADR-126)
                object_entity_id=claim.object_entity_id,
                status=claim.status,
                evidence_strength=claim.evidence_strength,
                is_disputed=is_disputed,
                verified_evidence_count=sum(
                    1 for link in claim.evidence_links
                    if link.evidence is not None and link.evidence.status.value == "verified"
                ),
            )
        )

    # Evidence state for the object as a whole. CONFLICTING outranks
    # everything - a disputed body of knowledge must not read as
    # "established" just because most claims are fine.
    if not claims:
        state = SignalState.UNKNOWN
    elif disputed:
        state = SignalState.CONFLICTING
    elif approved and unverified == 0:
        state = SignalState.ESTABLISHED
    elif approved:
        state = SignalState.PARTIAL
    else:
        state = SignalState.UNKNOWN

    caveats: list[str] = []
    if not claims:
        caveats.append("No claims have been recorded for this object yet.")
    if unverified:
        caveats.append(f"{unverified} claim(s) have no verified evidence behind them.")
    if disputed:
        caveats.append(f"{disputed} claim(s) are disputed or supported by conflicting evidence.")

    return AIKnowledgeResponse(
        knowledge_object_id=ko.id,
        canonical_name=outbound(ko.canonical_name),
        object_type=ko.object_type,
        claims=out_claims,
        coverage=AICoverage(
            has_knowledge_object=True,
            claim_count=len(claims),
            approved_claim_count=approved,
            disputed_claim_count=disputed,
            unverified_claim_count=unverified,
            evidence_state=state,
            caveats=caveats,
        ),
        as_of=_now(),
    )


@router.get("/products/{product_id}/trust", response_model=AITrustResponse)
def get_product_trust(
    product_id: UUID,
    identity: MachineIdentity = Depends(rate_limited(limit=300)),
    db: Session = Depends(get_db),
) -> AITrustResponse:
    """Verified trust records only.

    "Verified" means the two-layer rule from ADR-032: the trust record is
    VERIFIED **and** the Evidence beneath it is VERIFIED. Reusing
    `commerce_contract.get_trust_summaries()` rather than querying
    TrustRecord directly is deliberate - it is the single place that rule
    lives, and a second implementation here would be the obvious way for
    the two to drift.

    Unverified and rejected records are COUNTED in coverage but never
    listed, because listing them is how an unverified claim becomes a
    quoted fact.
    """
    _require(identity, AdapterScope.KNOWLEDGE_READ)

    product = commerce_contract.get_product(
        db, product_id=product_id, organization_id=identity.organization_id
    )
    if product is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    summary = commerce_contract.get_trust_summaries(
        db, subject_ids=[product_id], organization_id=identity.organization_id
    ).get(product_id)

    verified_types = set(summary.verified_trust_types) if summary else set()
    records = db.execute(
        select(TrustRecord).where(
            TrustRecord.organization_id == identity.organization_id,
            TrustRecord.subject_id == product_id,
            TrustRecord.verification_status == VerificationStatus.VERIFIED,
        )
    ).scalars().all()
    # Second gate: only records whose type survived the contract's
    # effective-verification check are surfaced.
    listed = [
        AITrustRecord(trust_type=r.trust_type, claim=outbound(r.claim), verified_at=r.verified_at)
        for r in records
        if r.trust_type in verified_types
    ]

    caveats: list[str] = []
    if summary is None or not summary.has_any_record:
        state = SignalState.UNKNOWN
        caveats.append("No trust records exist for this product yet. This is not a negative finding.")
    elif summary.rejected and not summary.verified:
        state = SignalState.NEGATIVE
        caveats.append(f"{summary.rejected} trust assertion(s) were reviewed and rejected.")
    elif summary.rejected:
        state = SignalState.CONFLICTING
        caveats.append(f"{summary.verified} verified and {summary.rejected} rejected trust record(s).")
    elif not summary.verified:
        state = SignalState.UNKNOWN
        caveats.append("Trust records exist but none are verified yet; they are not presented as facts.")
    else:
        state = SignalState.ESTABLISHED if summary.verified >= 2 else SignalState.PARTIAL

    return AITrustResponse(
        product_id=product.id,
        product_name=product.name,
        verified_trust=listed,
        coverage=AICoverage(
            has_knowledge_object=product.knowledge_object_id is not None,
            claim_count=(summary.verified + summary.pending_review + summary.unverified + summary.rejected) if summary else 0,
            approved_claim_count=summary.verified if summary else 0,
            disputed_claim_count=summary.rejected if summary else 0,
            unverified_claim_count=(summary.pending_review + summary.unverified) if summary else 0,
            evidence_state=state,
            caveats=caveats,
        ),
        as_of=_now(),
    )


@router.post("/ask", response_model=AIAnswerResponse)
def ask(
    payload: AIAskRequest,
    identity: MachineIdentity = Depends(rate_limited(limit=120)),
    db: Session = Depends(get_db),
) -> AIAnswerResponse:
    """Product suggestions for a stated need — or an explicit refusal.

    Delegates entirely to Phase 8's `recommendation_service`; no ranking
    logic exists here. That matters for a reason beyond tidiness: if this
    endpoint had its own scoring, an external agent and the merchant's own
    dashboard could receive different answers to the same question, and
    neither would be wrong.

    `answerable: false` is a complete, successful answer. §34 forbids
    pushing products when intent does not justify it, and an interface
    that cannot say "I won't suggest anything" will always suggest
    something.

    No numeric score is returned - see the module docstring.
    """
    _require(identity, AdapterScope.AI_QUERY)

    # A researching user is not a buying user. The mapping is deliberately
    # conservative: only an explicit "ready" reaches a transactional mode.
    mode = {
        "none": ResponseMode.EDUCATE,
        "researching": ResponseMode.EDUCATE,
        "comparing": ResponseMode.COMPARE,
        "ready": ResponseMode.RECOMMEND,
    }.get(payload.purchase_intent.lower(), ResponseMode.EDUCATE)

    overall, explanation, rows, rejected = recommendation_service.recommend(
        db,
        organization_id=identity.organization_id,
        response_mode=mode,
        customer_context=None,
        query_id=None,
        knowledge_object_id=payload.knowledge_object_id,
        category=payload.category,
        brand=None,
        product_ids=None,
        limit=payload.limit,
        persist=False,  # an external question is not a merchant decision to audit
        actor_user_id=identity.installation_id,
    )

    products = [
        AIAnswerProduct(
            product_id=row.product_id,
            name="",  # filled below from the contract, not from the row
            evidence_state=row.evidence_state,
            trust_state=row.trust_state,
            caveats=list((row.reason or {}).get("caveats", [])),
            rank=index + 1,
        )
        for index, row in enumerate(rows)
    ]
    if products:
        names = {
            p.id: p.name
            for p in commerce_contract.find_candidate_products(
                db,
                organization_id=identity.organization_id,
                product_ids=[p.product_id for p in products],
                include_non_recommendable=True,
                limit=len(products),
            )
        }
        for p in products:
            p.name = names.get(p.product_id, "")
        # Merchant purchase destination (see AIAnswerProduct.merchant_url).
        # Tenant-scoped at every lookup; only http(s) URLs are returned.
        product_ids = [p.product_id for p in products]
        offer_ids = [row.offer_id for row in rows if row.offer_id is not None]
        offer_urls = {
            o.product_id: o.url
            for o in db.execute(select(Offer).where(
                Offer.organization_id == identity.organization_id, Offer.id.in_(offer_ids),
            )).scalars()
            if o.url
        } if offer_ids else {}
        page_urls = {
            m.object_id: m.wordpress_url
            for m in db.execute(select(WordPressMapping).where(
                WordPressMapping.organization_id == identity.organization_id,
                WordPressMapping.object_type == MappedObjectType.PRODUCT,
                WordPressMapping.object_id.in_(product_ids),
                WordPressMapping.wordpress_url.is_not(None),
            ).order_by(WordPressMapping.updated_at.desc())).scalars()
        }
        for p in products:
            url = offer_urls.get(p.product_id) or page_urls.get(p.product_id)
            p.merchant_url = url if url and url.lower().startswith(("http://", "https://")) else None

    caveats: list[str] = []
    if not rows:
        caveats.append(explanation)
    if rejected:
        caveats.append(f"{len(rejected)} candidate product(s) were excluded as ineligible.")

    return AIAnswerResponse(
        answerable=bool(rows),
        reason=explanation,
        products=products,
        coverage=AICoverage(
            has_knowledge_object=payload.knowledge_object_id is not None,
            claim_count=len(rows) + len(rejected),
            approved_claim_count=len(rows),
            disputed_claim_count=0,
            unverified_claim_count=len(rejected),
            evidence_state=SignalState.UNKNOWN if not rows else SignalState.PARTIAL,
            caveats=caveats,
        ),
        as_of=_now(),
    )
