You are a Principal Software Architect, Staff Backend Engineer, Data Architect, AI Systems Engineer, and DevOps Engineer.

Your task is to BUILD the software described below.

Do NOT give me a conceptual overview unless absolutely necessary.
Do NOT repeatedly explain the architecture.
Do NOT ask unnecessary clarification questions.
Do NOT simplify the system into a generic SEO plugin.
Do NOT replace the architecture with your preferred architecture without a strong technical reason.

I want REAL, EXECUTABLE, PRODUCTION-QUALITY CODE.

When a decision is already specified below, follow it.
When something is not specified, make the most technically sound decision, document it briefly, and continue.

The goal is to produce the actual software incrementally, with every stage runnable and testable.

==================================================
1. PRODUCT VISION
==================================================

We are building a "Knowledge-to-Discovery-to-Commerce Operating Layer".

This is NOT merely an SEO plugin.

The system should allow a business website and its products to become:

- machine-readable
- semantically structured
- evidence-backed
- trustworthy
- discoverable by search engines
- understandable by AI systems and agents
- commercially discoverable
- connected to products and offers
- capable of routing users to the original merchant website
- capable of learning from legitimate customer/commerce interactions

The long-term flow is:

USER
 ↓
QUERY
 ↓
INTENT
 ↓
ENTITY
 ↓
KNOWLEDGE
 ↓
EVIDENCE
 ↓
TRUST
 ↓
PRODUCT
 ↓
OFFER
 ↓
MERCHANT WEBSITE
 ↓
CART
 ↓
CHECKOUT
 ↓
PURCHASE
 ↓
FEEDBACK
 ↓
KNOWLEDGE / COMMERCE IMPROVEMENT

The product must not attempt to replace ChatGPT, Gemini, Perplexity, Google, etc.

Instead, it should become the knowledge, trust, discovery, and commerce infrastructure that external search engines, AI systems, agents, and users can interact with.

==================================================
2. CORE ARCHITECTURE
==================================================

The architecture is:

                    Google / AI / Agents
                           |
                      REST / MCP
                           |
             +-------------v-------------+
             |       CLOUD CORE          |
             |                           |
             | Knowledge Engine          |
             | Evidence Engine           |
             | Research Engine           |
             | Graph Engine              |
             | Query / Intent Engine     |
             | Commerce Engine           |
             | Recommendation Engine     |
             | Customer Context Engine   |
             | Discovery Engine          |
             | Rights Engine             |
             +-------------+-------------+
                           |
                    PostgreSQL
                    + pgvector
                           |
                       Redis
                           |
                     Worker Queue
                           |
             +-------------v-------------+
             | WordPress / WooCommerce   |
             | Plugin / Adapter           |
             +---------------------------+

IMPORTANT:

The Cloud Core is the source of truth.

WordPress is an adapter/projection/integration layer.

The WordPress plugin must NOT become the main brain of the system.

==================================================
3. INITIAL TECHNOLOGY STACK
==================================================

Use:

Backend:
- Python
- FastAPI

Database:
- PostgreSQL

Vector:
- pgvector

ORM:
- SQLAlchemy 2.x

Migration:
- Alembic

Validation:
- Pydantic 2.x

Queue:
- Redis
- Celery

HTTP:
- httpx

Containerization:
- Docker
- Docker Compose

API:
- REST
- JSON
- versioned under /api/v1

Future:
- MCP interface
- additional platform adapters

Frontend/admin dashboard can be selected later, but architecture must support it cleanly.

WordPress plugin:
- PHP
- WordPress APIs/hooks
- WooCommerce integration

==================================================
4. IMPORTANT ARCHITECTURAL PRINCIPLE
==================================================

Do NOT create a huge microservice architecture in MVP.

Use a modular monolith initially.

The backend should be one deployable application with clear logical modules:

app/
    api/
    core/
    db/
    models/
    schemas/
    services/
    workers/
    integrations/
    security/

Later modules can be extracted into services if scale requires it.

==================================================
5. REPOSITORY STRUCTURE
==================================================

Create:

ai-operating-layer/
│
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   └── v1/
│   │   ├── core/
│   │   ├── db/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   ├── workers/
│   │   ├── integrations/
│   │   ├── security/
│   │   └── main.py
│   │
│   ├── migrations/
│   │   └── versions/
│   │
│   ├── tests/
│   │
│   ├── Dockerfile
│   ├── requirements.txt
│   └── alembic.ini
│
├── plugin/
│   └── ai-operating-layer/
│
├── docker-compose.yml
├── .env.example
├── .gitignore
├── README.md
└── docs/

==================================================
6. DOCKER
==================================================

Initial Docker services:

1. API
2. PostgreSQL with pgvector
3. Redis

Example architecture:

api
postgres
redis

The API must be reachable on port 8000 in development.

PostgreSQL must persist through a Docker volume.

Redis must persist only if technically necessary.

==================================================
7. ENVIRONMENT CONFIGURATION
==================================================

Use environment variables.

Example:

APP_ENV=development
APP_NAME=AI Operating Layer

DATABASE_URL=postgresql+psycopg://...
REDIS_URL=redis://...

SECRET_KEY=...

API_V1_PREFIX=/api/v1

Never hard-code production secrets.

Provide:

.env.example

Do not commit:

.env

==================================================
8. DATABASE PRINCIPLES
==================================================

Use UUID primary keys.

Use TIMESTAMPTZ for timestamps.

Use SQLAlchemy 2.x typed models.

Use Alembic migrations.

Use foreign keys properly.

Use indexes where appropriate.

Use soft-delete/archive semantics for important business/knowledge data rather than destructive deletion.

All tenant-owned data must have:

organization_id

Tenant isolation is mandatory.

Do not allow one organization to access another organization's data.

==================================================
9. CORE DATA MODEL
==================================================

The core entities are:

organizations
users
sites

knowledge_objects
entities
relationships
knowledge_versions
knowledge_gaps

sources
documents
document_chunks

claims
evidence
claim_evidence

research_projects
research_tasks

queries
intents
query_groups
query_group_members

products
offers
product_evidence
product_relations

trust_records

visibility_tests

customer_context
recommendations

rights_policies

wordpress_mappings
commerce_mappings

sync_jobs
audit_logs

==================================================
10. ORGANIZATIONS
==================================================

organizations:

id
name
slug
status
created_at
updated_at

users:

id
organization_id
email
name
role
password_hash
created_at
updated_at

Roles:

owner
admin
researcher
editor
analyst
viewer

sites:

id
organization_id
name
domain
platform
wordpress_url
woo_enabled
status
created_at
updated_at

A single organization may have multiple sites.

==================================================
11. KNOWLEDGE OBJECT
==================================================

knowledge_objects are the central knowledge abstraction.

Fields:

id
organization_id
canonical_name
slug
object_type
description
status
language
confidence
public_visibility
ai_visibility
version
created_at
updated_at

Possible object types:

plant
food
compound
disease
condition
concept
person
organization
product
brand
place
study
method
topic

This list must be extensible.

A Knowledge Object is NOT merely a WordPress article.

It is the canonical semantic object from which multiple outputs can be generated:

- article
- FAQ
- comparison
- buying guide
- structured data
- AI API response
- product explanation
- evidence section

==================================================
12. ENTITIES
==================================================

entities:

id
organization_id
knowledge_object_id
entity_type
canonical_name
aliases
external_ids
language
created_at
updated_at

Use JSONB for aliases/external IDs where appropriate.

The system must eventually support entity resolution.

Example:

Taranjabin
may have:
- Persian name
- English name
- alternate names
- scientific identifiers
- external IDs

==================================================
13. SOURCES
==================================================

sources:

id
organization_id
source_type
title
author
url
doi
pmid
isbn
publisher
publication_date
access_status
rights_status
reliability_score
metadata
created_at
updated_at

Source types include:

scientific_paper
book
pdf
website
government
dataset
supplier_document
lab_report
user_upload
first_party
review
news

IMPORTANT:

The system must distinguish:

- source existence
- source accessibility
- source reliability
- evidence strength

Do not assume an inaccessible source does not exist.

Do not claim full-text review if only metadata or abstract was available.

Never bypass paywalls.

==================================================
14. DOCUMENTS
==================================================

documents:

id
organization_id
source_id
title
content
language
content_hash
version
mime_type
file_size
storage_path
extraction_status
created_at
updated_at

Documents may originate from:

- URL
- PDF
- WordPress
- uploaded document
- user-provided source

==================================================
15. DOCUMENT CHUNKS
==================================================

document_chunks:

id
document_id
chunk_index
content
token_count
embedding
metadata
created_at

Use pgvector.

The embedding dimension must be configurable based on the selected embedding model.

Do not hard-code assumptions that prevent changing embedding models later.

==================================================
16. CLAIMS
==================================================

claims:

id
organization_id
knowledge_object_id
subject_entity_id
predicate
object_value
object_entity_id
claim_type
evidence_strength
confidence
status
source_generated
human_reviewed
created_at
updated_at

A claim is an assertion.

Examples:

Taranjabin -> contains -> Mannitol

or:

Entity X -> has_property -> Y

IMPORTANT:

Extraction confidence is NOT evidence strength.

AI extraction can be highly confident while scientific evidence remains weak.

==================================================
17. EVIDENCE
==================================================

evidence:

id
organization_id
source_id
document_id
evidence_type
study_type
population_type
accessibility
directness
evidence_strength
excerpt
location_reference
interpretation
confidence
created_at
updated_at

Evidence types:

scientific
first_party
observational
documentary
laboratory
etc.

Study types can include:

HUMAN
ANIMAL
IN_VITRO
OBSERVATIONAL
RCT
SYSTEMATIC_REVIEW
META_ANALYSIS

Directness:

DIRECT
INDIRECT
MECHANISTIC
ANALOGICAL
COMPOSITIONAL

The system MUST preserve evidence scope.

Example:

Taranjabin
contains
Mannitol

does NOT automatically mean:

Taranjabin
has
every clinically observed effect of mannitol.

==================================================
18. CLAIM ↔ EVIDENCE
==================================================

claim_evidence:

claim_id
evidence_id
relation_type

relation types:

supports
contradicts
qualifies
limits
contextualizes

Multiple evidence records may support or contradict one claim.

==================================================
19. GRAPH
==================================================

relationships:

id
organization_id
subject_id
predicate
object_id
confidence
source_id
status
created_at

The initial graph implementation should use PostgreSQL relational tables.

Do NOT introduce Neo4j in MVP.

The architecture must make future Graph DB migration possible.

==================================================
20. KNOWLEDGE GAPS
==================================================

knowledge_gaps:

id
organization_id
knowledge_object_id
gap_type
description
priority
status
recommended_action
created_at
updated_at

Gap types:

CONTENT_GAP
ENTITY_GAP
CLAIM_GAP
EVIDENCE_GAP
SOURCE_GAP
ACCESS_GAP
RELATION_GAP
FRESHNESS_GAP
CONFLICT_GAP
RESEARCH_GAP

Recommended actions may include:

SEARCH_MORE
EXPAND_SEARCH
SEARCH_RELATED_ENTITY
SEARCH_COMPOUND
SEARCH_MECHANISM
SEARCH_RELATED_PLANT
SEARCH_CLINICAL_DATABASE
SEARCH_PRIMARY_STUDIES
SEARCH_SECONDARY_STUDIES
REQUEST_FULL_TEXT
REQUEST_USER_SOURCE
REQUEST_PDF
REQUEST_DATASET
REQUEST_EXPERT_REVIEW
RUN_ANALYSIS
COMPARE_EVIDENCE
RESOLVE_CONFLICT
WAIT_FOR_NEW_EVIDENCE
KEEP_GAP_OPEN

==================================================
21. KNOWLEDGE VERSIONING
==================================================

knowledge_versions:

id
knowledge_object_id
version
snapshot
change_summary
created_by
created_at

Knowledge must be versioned.

Need support for:

- diff
- audit
- rollback
- review
- publishing status

Do not fake article dates simply to make content look fresh.

==================================================
22. RESEARCH ENGINE
==================================================

research_projects:

id
organization_id
name
objective
status
created_at
updated_at

research_tasks:

id
research_project_id
task_type
query
status
result
created_at
completed_at

Research modes:

GAP_DRIVEN
USER_DRIVEN
EXPLORATORY
CONTINUOUS

Research should produce traceable results.

The system should preserve the research trail.

==================================================
23. QUERY INTELLIGENCE
==================================================

queries:

id
organization_id
query
language
country
source
search_volume
commercial_value
priority
status
discovered_at

Possible sources:

search_console
excel
csv
site_search
keyword_tool
customer
research
serp
ai_test
manual

The system must accept manually uploaded Excel/CSV query lists.

It must also eventually integrate Google Search Console.

==================================================
24. INTENT
==================================================

intents:

id
query_id
intent_type
confidence
entity_id
product_id
created_at

Intent types:

INFORMATION
EDUCATION
PROBLEM
COMPARISON
PRICE
QUALITY
AUTHENTICITY
TRUST
ORIGIN
SUPPLIER
WHOLESALE
LOCAL
AVAILABILITY
COMMERCIAL
TRANSACTIONAL
RECOMMENDATION

Do NOT create one page for every query.

Use:

Queries
 ↓
Intent
 ↓
Clustering
 ↓
Knowledge Needs
 ↓
Pages / Sections

==================================================
25. QUERY GROUPS
==================================================

query_groups:

id
organization_id
name
primary_intent
target_entity_id
priority
created_at

query_group_members:

query_group_id
query_id

The system should cluster semantically related queries.

==================================================
26. COMMERCE
==================================================

products:

id
organization_id
site_id
external_id
sku
name
slug
description
brand
category
origin
ingredients
specifications
certifications
images
shipping
returns_policy
status
created_at
updated_at

The product object is not merely a WooCommerce mirror.

It is a normalized Product Knowledge Object.

==================================================
27. OFFERS
==================================================

offers:

id
product_id
external_id
price
currency
availability
stock_quantity
condition
url
valid_from
valid_until
created_at
updated_at

Keep Product and Offer separate.

This is important for:

- price
- availability
- variants
- sellers
- promotions
- future marketplaces

==================================================
28. PRODUCT EVIDENCE
==================================================

product_evidence:

id
product_id
evidence_id
claim
verification_status
verified_at
created_at

Examples:

Product A
Claim: Origin = X
Evidence: origin document

Product A
Claim: Grade = A
Evidence: lab report

Do not allow unsupported marketing claims to be presented as verified evidence.

==================================================
29. PRODUCT RELATIONS
==================================================

product_relations:

product_id
related_product_id
relation_type
confidence

Relation types:

alternative
complementary
similar
frequently_bought_together
replacement

==================================================
30. TRUST ENGINE
==================================================

trust_records:

id
organization_id
subject_type
subject_id
trust_type
claim
evidence_id
verification_status
verified_at
created_at

Trust must be evidence-backed.

Possible trust chain:

Website
 ↓
Business Identity
 ↓
Supplier
 ↓
Origin
 ↓
Product
 ↓
Quality Evidence
 ↓
Testing
 ↓
Reviews
 ↓
Policies
 ↓
Customer Experience

Do not create a fake "trust score" that has no explainable evidence.

==================================================
31. AI VISIBILITY
==================================================

visibility_tests:

id
organization_id
query_id
platform
test_type
prompt
response
mentioned
cited
recommended
product_present
url_present
result_metadata
tested_at

Platforms may include:

google
bing
chatgpt
gemini
perplexity
copilot

The system must distinguish:

Mention
Citation
Recommendation
Product Display
URL
Click
Purchase

These are NOT the same metric.

==================================================
32. CUSTOMER CONTEXT
==================================================

customer_context:

id
organization_id
customer_id
session_id
context_type
intent
topic
purchase_intent
evidence_need
trust_need
price_sensitivity
product_interest
preferences
consent_status
source
created_at
updated_at

IMPORTANT:

Do not store raw external AI conversations by default.

Prefer minimal context:

topic
intent
purchase intent
preferences where legitimately provided
evidence need
trust need

Context must be consent-aware and privacy-safe.

The system must not pretend that ChatGPT/Gemini/etc permanently remember a user unless there is an actual integration supporting such context.

==================================================
33. RECOMMENDATION ENGINE
==================================================

recommendations:

id
organization_id
customer_context_id
product_id
query_id
knowledge_object_id
relevance_score
evidence_score
trust_score
availability_score
final_score
reason
status
created_at

The recommendation engine should follow:

USER QUESTION
 ↓
USER INTENT
 ↓
KNOWLEDGE
 ↓
CLAIM
 ↓
EVIDENCE
 ↓
RELEVANCE
 ↓
PRODUCT
 ↓
PRODUCT EVIDENCE
 ↓
RECOMMENDATION
 ↓
PURCHASE

The internal recommendation score is NOT:

- Google ranking
- ChatGPT ranking
- AI ranking

It is only an internal decision signal.

==================================================
34. RESPONSE MODES
==================================================

Initial response modes:

EDUCATE
COMPARE
REASSURE
RECOMMEND
TRANSACT

Examples:

"ترنجبین چیست؟"
→ EDUCATE

"ترنجبین A یا B؟"
→ COMPARE

"چطور بفهمم اصل است؟"
→ REASSURE

"بهترین ترنجبین برای خرید؟"
→ RECOMMEND

"میخواهم همین را بخرم."
→ TRANSACT

Do not push products when the user's intent does not justify it.

==================================================
35. COMMERCE FLOW
==================================================

The merchant website remains the trusted transaction destination.

Preferred flow:

AI
 ↓
Product Card
 ↓
"خرید از فروشگاه اصلی"
 ↓
Merchant Website
 ↓
Cart
 ↓
Checkout
 ↓
Payment Gateway

Payment information must never be placed into AI prompts, context payloads, or signed cart tokens.

==================================================
36. SIGNED CART INTENT
==================================================

Future commerce integration may create:

/cart/?token=SIGNED_TOKEN

Token can encode:

product
offer
quantity
site
expiration

and must be cryptographically signed.

Never put payment credentials into the token.

==================================================
37. RIGHTS ENGINE
==================================================

rights_policies:

id
organization_id
resource_type
resource_id
discovery_access
retrieval_access
training_access
bulk_access
commercial_access
rate_limit
metadata
created_at
updated_at

Initial policy model:

Discovery        OPEN
Search           OPEN
Snippet          OPEN
Full Text        CONTROLLED
Bulk Extraction  CONTROLLED
Dataset          CONTROLLED
Training         POLICY
Private Data     CLOSED

Do not promise that the system can make content "AI-proof".

Do not block search crawlers blindly.

Discovery and commercial visibility are strategically important.

==================================================
38. WORDPRESS INTEGRATION
==================================================

Create a WordPress plugin:

ai-operating-layer

The plugin should handle:

- authentication
- connection to Cloud Core
- content sync
- product sync
- schema rendering
- WordPress hooks
- WooCommerce hooks
- status reporting
- cache where appropriate

The plugin must remain thin.

Cloud Core remains the source of truth.

==================================================
39. WORDPRESS MAPPINGS
==================================================

wordpress_mappings:

id
site_id
object_type
object_id
wordpress_post_id
wordpress_post_type
wordpress_url
sync_status
last_synced_at
remote_updated_at
created_at

==================================================
40. WOOCOMMERCE MAPPINGS
==================================================

commerce_mappings:

id
site_id
product_id
woo_product_id
woo_variation_id
sku
last_synced_at
sync_status

==================================================
41. SYNC JOBS
==================================================

sync_jobs:

id
organization_id
site_id
job_type
status
payload
attempts
error_message
created_at
started_at
completed_at

Use async workers.

Do not perform heavy ingestion/extraction/embedding tasks directly inside normal HTTP requests.

==================================================
42. AUDIT LOG
==================================================

audit_logs:

id
organization_id
user_id
action
resource_type
resource_id
old_value
new_value
created_at

Important operations must be auditable.

==================================================
43. WORKER JOBS
==================================================

Initial worker job types:

ingest_document
extract_text
chunk_document
generate_embeddings

extract_entities
resolve_entities

extract_claims
find_evidence
evaluate_source

detect_conflicts

generate_queries
cluster_queries

sync_wordpress
sync_woocommerce

generate_schema

visibility_test

calculate_metrics

send_notification

==================================================
44. INGESTION PIPELINE
==================================================

Input sources:

URL
PDF
Text
WordPress
CSV
Excel

Pipeline:

INPUT
 ↓
PARSER
 ↓
CLEANER
 ↓
STRUCTURE DETECTION
 ↓
SEMANTIC CHUNKING
 ↓
ENTITY EXTRACTION
 ↓
CLAIM EXTRACTION
 ↓
EVIDENCE MAPPING
 ↓
EMBEDDING
 ↓
ENTITY RESOLUTION
 ↓
CONFLICT DETECTION
 ↓
KNOWLEDGE OBJECT
 ↓
HUMAN REVIEW
 ↓
PUBLISH

Do not automatically publish uncertain scientific or commercial claims without appropriate review.

==================================================
45. 1000 ARTICLE STRATEGY
==================================================

The system may receive approximately 1000 articles around a topic such as Taranjabin.

Do NOT assume:

1000 articles = 1000 knowledge objects.

Instead:

1000 articles
 ↓
duplicate detection
 ↓
classification
 ↓
entity extraction
 ↓
claim extraction
 ↓
evidence mapping
 ↓
clustering
 ↓
Knowledge Objects

Potentially:

1000 articles
→ hundreds of entities
→ dozens of knowledge objects
→ dozens of topic clusters
→ query clusters

The exact numbers must be data-driven.

==================================================
46. KNOWLEDGE VS CONTENT
==================================================

Content is a presentation layer.

Knowledge is the semantic source of truth.

One Knowledge Object may generate:

- article
- FAQ
- comparison
- buying guide
- structured data
- AI response
- product explanation

Do not duplicate knowledge manually across multiple systems.

==================================================
47. ORIGINAL KNOWLEDGE
==================================================

The system should distinguish:

PUBLIC KNOWLEDGE
OPEN RESEARCH
DIFFICULT-TO-ACCESS KNOWLEDGE
USER-PROVIDED KNOWLEDGE
FIRST-PARTY KNOWLEDGE
ORIGINAL ANALYSIS
ORIGINAL DATA
LIVE COMMERCE DATA

This later supports:

Knowledge Moat
Knowledge Replacement Risk
Knowledge Composition

Do not falsely claim exclusivity over public facts.

==================================================
48. FIRST-PARTY EVIDENCE
==================================================

The system should eventually support:

supplier invoice
certificate
lab report
batch record
origin document
product photo
warehouse record
quality inspection
purchase record
expert review
original dataset
original analysis

Example:

Product A
 ↓
Claim: Grade A
 ↓
Evidence: Lab Report #123
 ↓
Date
 ↓
Verification Status

==================================================
49. SCIENTIFIC SAFETY
==================================================

For health/scientific content, preserve distinctions between:

Traditional Use
Scientific Evidence
Clinical Evidence
Clinical Recommendation

Never convert:

"compound X has evidence"

into:

"plant/product Y definitely has the same clinical effect"

unless direct evidence supports it.

Do not make unsupported medical claims.

==================================================
50. API
==================================================

Use:

/api/v1/

Initial API groups:

/knowledge
/sources
/evidence
/research
/queries
/products
/recommendations
/context
/commerce
/sites

Knowledge:

GET    /knowledge/search
GET    /knowledge/{id}
POST   /knowledge
PATCH  /knowledge/{id}
GET    /knowledge/{id}/evidence
GET    /knowledge/{id}/relations

Research:

POST   /research/projects
POST   /research/tasks
GET    /research/projects/{id}
GET    /research/tasks/{id}

Evidence:

GET    /evidence/search
GET    /evidence/{id}
POST   /evidence
POST   /claims/{id}/evidence

Queries:

POST   /queries/import
GET    /queries
POST   /queries/cluster
GET    /query-groups

Products:

GET    /products
GET    /products/{id}
GET    /products/{id}/offers
GET    /products/{id}/evidence
GET    /products/{id}/related

Recommendations:

POST   /recommendations
GET    /recommendations/{id}

Context:

POST   /context
POST   /context/query
GET    /context/{id}

Commerce:

GET    /commerce/products
GET    /commerce/offers
POST   /commerce/cart
POST   /commerce/purchase-intent
POST   /commerce/price-alert
POST   /commerce/restock-alert

==================================================
51. API DESIGN PRINCIPLES
==================================================

Use:

- typed request/response schemas
- validation
- authentication
- authorization
- tenant isolation
- pagination
- filtering
- sorting
- consistent errors
- structured logging
- request IDs
- API versioning

Do not expose internal database models directly as public API contracts.

Use Pydantic schemas.

==================================================
52. SECURITY
==================================================

Implement:

- authentication
- authorization
- tenant isolation
- API keys where appropriate
- secure password hashing
- secrets through environment
- input validation
- rate limiting architecture
- signed URLs/tokens where necessary
- audit logs

Never log:

- passwords
- API secrets
- payment credentials
- sensitive private conversation content

==================================================
53. DATABASE INDEXING
==================================================

Important indexes include:

knowledge object type
entity canonical name
claim subject
claim object
evidence source
relationship subject
relationship object
query text
query priority
product SKU
product external ID
offer product
visibility platform
visibility query

Use appropriate indexes based on actual query patterns.

Use HNSW or appropriate pgvector index for embeddings.

==================================================
54. MVP SCOPE
==================================================

Do NOT attempt to build everything at once.

MVP consists of:

KNOWLEDGE
- Knowledge Objects
- Entities
- Claims
- Evidence
- Sources
- Basic Graph
- Knowledge Gaps

COMMERCE
- Products
- Offers
- Trust
- WooCommerce synchronization

DISCOVERY
- Queries
- Intent
- Query Groups
- Basic AI Visibility tracking

INTEGRATION
- WordPress
- WooCommerce

INFRASTRUCTURE
- REST API
- PostgreSQL
- pgvector
- Redis
- Workers
- Authentication
- Audit

==================================================
55. MVP PILOT
==================================================

Before processing 1000 articles:

Use a controlled pilot:

10–20 Knowledge Objects
20–50 Query Clusters
5–10 Products
50–100 Evidence/Source records
10–20 Trust Records
50–100 Articles

Only after the complete loop works should we scale.

==================================================
56. MVP SUCCESS LOOP
==================================================

The MVP is successful if this loop works:

QUERY
 ↓
INTENT
 ↓
KNOWLEDGE
 ↓
EVIDENCE
 ↓
TRUST
 ↓
PRODUCT
 ↓
PRODUCT CLICK
 ↓
CART
 ↓
PURCHASE

And for AI visibility:

QUERY
 ↓
AI/Search Test
 ↓
Mention
 ↓
Citation
 ↓
Recommendation
 ↓
Product Presence
 ↓
Merchant URL

==================================================
57. METRICS
==================================================

Initial metrics:

Knowledge Coverage
Evidence Coverage
Product Data Completeness
Trust Coverage

AI Visibility
AI Citation
AI Recommendation

Product CTR
Add-to-Cart
Conversion
Repeat Purchase
Alert Conversion

Do not invent unsupported metrics.

==================================================
58. WHAT NOT TO BUILD YET
==================================================

Do NOT build in MVP:

- own LLM
- own ChatGPT clone
- Neo4j
- huge microservice system
- complex ML recommendation system
- full CRM
- full CDP
- payment processor
- AI training marketplace
- automated medical diagnosis
- giant 600-feature platform
- unnecessary enterprise abstractions

Keep architecture extensible without prematurely implementing all future functionality.

==================================================
59. DEVELOPMENT PRINCIPLE
==================================================

The software must be built incrementally.

Each stage must leave the repository in a runnable state.

Do not dump thousands of disconnected code lines.

For every implementation stage provide:

1. Files to create/change
2. Complete content of each file
3. Commands to run
4. Expected result
5. Tests
6. Known limitations

When modifying an existing file, provide the complete final file unless the change is extremely small and unambiguous.

Do not provide pseudocode when executable code is requested.

==================================================
60. TESTING
==================================================

Use pytest.

At minimum test:

- database connection
- health endpoint
- authentication
- tenant isolation
- Knowledge Object creation
- Knowledge Object retrieval
- Source creation
- Claim creation
- Evidence creation
- Claim/Evidence relationship
- Product creation
- Offer creation
- recommendation flow
- API validation

Add integration tests for PostgreSQL-backed functionality.

==================================================
61. DOCUMENTATION
==================================================

Maintain:

README.md
docs/architecture.md
docs/database.md
docs/api.md
docs/development.md

Documentation should explain implementation decisions briefly.

Do not turn documentation into marketing material.

==================================================
62. DEVELOPMENT ORDER
==================================================

Follow this order:

PHASE 0
Repository
Docker
Configuration
FastAPI
PostgreSQL
Redis
Alembic

PHASE 1
Organizations
Users
Sites
Authentication
Tenant isolation

PHASE 2
Knowledge Objects
Entities
Relationships
Knowledge Versions
Knowledge Gaps

PHASE 3
Sources
Documents
Chunks
pgvector

PHASE 4
Claims
Evidence
Claim/Evidence
Conflict foundations

PHASE 5
Research Engine

PHASE 6
Query Engine
Intent
Query Clustering

PHASE 7
Products
Offers
Product Evidence
Trust

PHASE 8
Recommendation Engine

PHASE 9
WordPress Adapter

PHASE 10
WooCommerce Adapter

PHASE 11
AI/REST interfaces

PHASE 12
AI Visibility

PHASE 13
Rights Layer

PHASE 14
Dashboard

PHASE 15
Pilot

PHASE 16
Scale

==================================================
63. CRITICAL ARCHITECTURAL RULE
==================================================

Do not silently change the following:

Cloud Core = source of truth
WordPress = adapter
PostgreSQL = primary database
pgvector = initial vector layer
Redis = queue/cache infrastructure
Modular monolith = MVP
REST API = primary interface
MCP = future/secondary agent interface
Knowledge Object = canonical knowledge abstraction
Evidence = separate from claims
Product = separate from Offer
Query = separate from Intent
Customer Context = separate from raw conversation
Trust = evidence-backed
Rights = separate from discovery
Commerce transaction = merchant website

==================================================
64. HOW TO START
==================================================

START WITH PHASE 0.

Do not jump directly to the complete final product.

Generate the actual repository files for Phase 0:

- docker-compose.yml
- .env.example
- .gitignore
- README.md
- backend/Dockerfile
- backend/requirements.txt
- backend/app/main.py
- backend/app/core/config.py
- backend/app/db/base.py
- backend/app/db/session.py
- alembic configuration
- initial migration structure
- basic tests

The first milestone must support:

docker compose up --build

and:

GET /health

and:

database connectivity

Then provide the exact commands required to run migrations and tests.

==================================================
65. IMPORTANT RESPONSE RULE
==================================================

Do not spend the response explaining what you could build.

BUILD IT.

If the response is too long for one message, split implementation into clearly numbered parts, but keep every part executable.

Never leave files as:

"TODO"
"implement later"
"pseudo code"

unless that functionality is explicitly outside the current phase.

At the end of each phase report:

STATUS:
- implemented
- tested
- remaining

Then continue to the next phase when requested.

==================================================
66. FINAL PRODUCT GOAL
==================================================

The final system should eventually enable:

Business
 ↓
Knowledge
 ↓
Evidence
 ↓
Trust
 ↓
Search / AI Discovery
 ↓
Product Discovery
 ↓
Merchant Website
 ↓
Purchase
 ↓
Customer Relationship
 ↓
Feedback
 ↓
Better Knowledge
 ↓
Better Discovery
 ↓
More Commerce

The ultimate objective is not merely "AI visibility".

The objective is:

INCREASE TRUSTED DISCOVERY
→ INCREASE RELEVANT PRODUCT DISCOVERY
→ INCREASE CONVERSION
→ BUILD A DEFENSIBLE KNOWLEDGE + COMMERCE MOAT.

Now start with PHASE 0 and write the actual code.