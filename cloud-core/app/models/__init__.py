"""
Central model registry.

Every ORM model module MUST be imported here. `migrations/env.py`
imports this package (not individual model modules) so that
`alembic revision --autogenerate` always sees the full schema —
this directly addresses the Phase 0 review finding: forgetting to
import a new model module would otherwise make autogenerate produce
an empty/incorrect migration.
"""

from app.models.access_policy import AccessPolicy
from app.models.ai_agent import AiAgent
from app.models.audit_log import AuditLog
from app.models.auth_session import AuthSession
from app.models.coverage_audit import CoverageAudit
from app.models.website import NewsletterSubscriber, SitePost, SitePostRevision, SiteSection
from app.models.publication import (
    Publication, PublicationReference, PublicationSection, PublicationSentence, SentenceSource,
)
from app.models.claim import Claim
from app.models.claim_evidence import ClaimEvidence
from app.models.commerce_mapping import CommerceMapping
from app.models.customer_context import CustomerContext
from app.models.document import Document
from app.models.document_artifact import DocumentAsset, DocumentConversion, DocumentTable
from app.models.document_element import DocumentElement
from app.models.synthesis import SynthesisRun, SynthesisUnit
from app.models.workspace import WorkspaceCommand, WorkspaceCommandVersion
from app.models.knowledge_transfer import KnowledgeTransferRecord
from app.models.conversation import (
    ChatSettings, Conversation, ConversationCitation, ConversationFeedback,
    ConversationMessage, ConversationResearchRequest,
)
from app.models.document_chunk import DocumentChunk
from app.models.entity import Entity
from app.models.evidence_conflict import EvidenceConflict
from app.models.evidence import Evidence
from app.models.installation import Installation, InstallationCredential
from app.models.intent import Intent
from app.models.knowledge_gap import KnowledgeGap
from app.models.knowledge_schema import Category, KnowledgeSection, SectionDefinition, SectionPropagation
from app.models.knowledge_object import KnowledgeObject
from app.models.knowledge_version import KnowledgeVersion
from app.models.offer import Offer
from app.models.organization import Organization
from app.models.product import Product
from app.models.product_evidence import ProductEvidence
from app.models.product_relation import ProductRelation
from app.models.query import Query
from app.models.recommendation import Recommendation
from app.models.query_cluster import QueryCluster
from app.models.query_cluster_membership import QueryClusterMembership
from app.models.query_group import QueryGroup
from app.models.query_group_membership import QueryGroupMembership
from app.models.query_provenance import QueryProvenance
from app.models.relationship import Relationship
from app.models.research_project import ResearchProject
from app.models.research_task import ResearchTask
from app.models.research_task_reference import ResearchTaskReference
from app.models.site import Site
from app.models.source import Source
from app.models.sync_job import SyncJob
from app.models.trust_record import TrustRecord
from app.models.user import User
from app.models.content_view_daily import ContentViewDaily
from app.models.page_view import PageView
from app.models.search_demand_event import SearchDemandEvent
from app.models.search_observation import SearchObservation
from app.models.visibility import VisibilityTest
from app.models.ai_execution import AIExecution
from app.models.ai_center import (AIDiscoveryEntry, AIHealthEvent, AIModel, AIProvider, AIProviderAccount,
                                  AIRoutingDecision, AIRoutingPolicy, AIRoutingStep, AIWorkingMemory, KnowledgeKeyword,
                                  AIJob, AIJobItem)
from app.models.login_code import LoginCode, LoginCodeThrottle
from app.models.signup_code import SignupCode
from app.models.keyword_trace import KeywordTrace
from app.models.demand import DemandConnection, DemandSignal
from app.models.user_preferences import UserPreferences
from app.models.billing_wallet import Payment, PaymentWebhookEvent, Wallet, WalletLedgerEntry, WalletReservation
from app.models.research_planning import EvidenceCompletionTask, ResearchQuerySet
from app.models.research_dependency import ResearchIteration, SourceDependency
from app.models.research_federation import ResearchHit, ResearchProviderRun, ResearchQuery, ResearchQuestion
from app.models.agent_network import AgentDefinition, AgentSession, AgentTask, AgentMessage, AgentHandoff, AgentMemoryBinding
from app.models.background_policy import BackgroundTaskPolicy, MemoryProfile
from app.models.visibility_project import (
    VisibilityCompetitor,
    VisibilityEvent,
    VisibilityProject,
    VisibilityRun,
    VisibilitySnapshot,
)
from app.models.visibility_budget import VisibilityBudget
from app.models.wordpress_mapping import WordPressMapping

__all__ = [
    "Organization",
    "User",
    "Site",
    "AuditLog",
    "AuthSession",
    "KnowledgeObject",
    "Entity",
    "Claim",
    "Relationship",
    "KnowledgeVersion",
    "KnowledgeGap",
    "Source",
    "Document",
    "DocumentChunk",
    "Evidence",
    "ClaimEvidence",
    "ResearchProject",
    "ResearchTask",
    "ResearchTaskReference",
    "Query",
    "QueryProvenance",
    "Intent",
    "QueryGroup",
    "QueryGroupMembership",
    "QueryCluster",
    "QueryClusterMembership",
    "Product",
    "Offer",
    "ProductEvidence",
    "ProductRelation",
    "TrustRecord",
    "CustomerContext",
    "Recommendation",
    "Installation",
    "InstallationCredential",
    "WordPressMapping",
    "CommerceMapping",
    "SyncJob",
    "VisibilityTest",
    "AIExecution",
    "VisibilityBudget",
    "VisibilityProject",
    "VisibilityRun",
    "VisibilitySnapshot",
    "VisibilityCompetitor",
    "VisibilityEvent",
    "SearchObservation",
    "DocumentConversion",
    "DocumentTable",
    "DocumentElement",
    "SynthesisRun",
    "SynthesisUnit",
    "WorkspaceCommand",
    "WorkspaceCommandVersion",
    "ChatSettings",
    "Conversation",
    "ConversationMessage",
    "ConversationCitation",
    "ConversationFeedback",
    "ConversationResearchRequest",
    "DocumentAsset",
    # --- Phase 13
    "AiAgent",
    "AccessPolicy",
    "PageView",
    "ContentViewDaily",
    "SearchDemandEvent",
]
