"""
Aggregates all /api/v1 routers.

As new API groups are implemented (recommendations, context — see
section 50 of the master spec), they are
included here. commerce/products (Phase 7) is the latest addition.
"""

from fastapi import APIRouter

from app.api.v1.ai import router as ai_router
from app.api.v1.auth import router as auth_router
from app.api.v1.claim_evidence import router as claim_evidence_router
from app.api.v1.claims import router as claims_router
from app.api.v1.commerce import router as commerce_router
from app.api.v1.documents import router as documents_router
from app.api.v1.entities import router as entities_router
from app.api.v1.evidence import router as evidence_router
from app.api.v1.health import router as health_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.knowledge import router as knowledge_router
from app.api.v1.knowledge_gaps import router as knowledge_gaps_router
from app.api.v1.organizations import router as organizations_router
from app.api.v1.queries import router as queries_router
from app.api.v1.recommendations import router as recommendations_router
from app.api.v1.relationships import router as relationships_router
from app.api.v1.research import router as research_router
from app.api.v1.sites import router as sites_router
from app.api.v1.sources import router as sources_router
from app.api.v1.telemetry import router as telemetry_router
from app.api.v1.users import router as users_router
from app.api.v1.visibility import router as visibility_router
from app.api.v1.ai_executions import router as ai_executions_router
from app.api.v1.ai_center import kw_router as knowledge_keywords_router, router as ai_center_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(auth_router)
api_router.include_router(organizations_router)
api_router.include_router(users_router)
api_router.include_router(sites_router)
api_router.include_router(knowledge_router)
api_router.include_router(entities_router)
api_router.include_router(claims_router)
api_router.include_router(relationships_router)
api_router.include_router(knowledge_gaps_router)
api_router.include_router(sources_router)
api_router.include_router(documents_router)
api_router.include_router(evidence_router)
api_router.include_router(claim_evidence_router)
api_router.include_router(research_router)
api_router.include_router(queries_router)
api_router.include_router(commerce_router)
api_router.include_router(recommendations_router)
api_router.include_router(integrations_router)
api_router.include_router(ai_router)
api_router.include_router(visibility_router)
# Phase 17 — canonical AI execution (read-only).
api_router.include_router(ai_executions_router)
# AI Center (REQ-AIC-*, REQ-KW-*).
api_router.include_router(ai_center_router)
api_router.include_router(knowledge_keywords_router)
# ADR-096 — Agent Network / Orchestration Layer.
from app.api.v1.agent_network import router as agent_network_router
from app.api.v1.keyword_trace import router as keyword_trace_router
api_router.include_router(agent_network_router)
api_router.include_router(keyword_trace_router)
from app.api.v1.demand import router as demand_router  # noqa: E402
api_router.include_router(demand_router)
from app.api.v1.preferences import router as preferences_router  # noqa: E402
api_router.include_router(preferences_router)
from app.api.v1.federated_research import router as federated_research_router  # noqa: E402
api_router.include_router(federated_research_router)
from app.api.v1.network_check import router as network_check_router  # noqa: E402
api_router.include_router(network_check_router)
from app.api.v1.billing import router as billing_router  # noqa: E402
api_router.include_router(billing_router)
from app.api.v1.conflicts import router as conflicts_router  # noqa: E402
api_router.include_router(conflicts_router)
from app.api.v1.memory_center import router as memory_center_router  # noqa: E402
api_router.include_router(memory_center_router)
from app.api.v1.research_planning import router as research_planning_router  # noqa: E402
api_router.include_router(research_planning_router)
from app.api.v1.knowledge_schema import router as knowledge_schema_router  # noqa: E402
api_router.include_router(knowledge_schema_router)
from app.api.v1.coverage_audit import router as coverage_audit_router  # noqa: E402
api_router.include_router(coverage_audit_router)
from app.api.v1.publications import router as publications_router  # noqa: E402
api_router.include_router(publications_router)
from app.api.v1.website import router as website_router  # noqa: E402
api_router.include_router(website_router)
# Phase 13 — analytics, demand intelligence, AI access control.
api_router.include_router(telemetry_router)
