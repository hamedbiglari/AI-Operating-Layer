# AI Resource Discovery Registry (ADR-093, REQ-AIC-008/011)

## Core rule: a discovered name is not an integration

## Status machine
```
DISCOVERED → IDENTIFIED → OFFICIAL_SOURCE_VERIFIED → API_CAPABILITY_CHECKED
→ CREDENTIAL_METHOD_VERIFIED → CAPABILITY_VERIFIED → HEALTH_CHECKED → APPROVED → ACTIVE
```
Exception statuses: APPLICATION_ONLY, MODEL_ONLY, SPECIALIZED_RESEARCH_TOOL,
NO_VERIFIED_API, NOT_VERIFIED, DEPRECATED, BLOCKED_EXTERNAL_DEPENDENCY, DISABLED.

Nothing becomes ACTIVE automatically.
API, pricing, quota remain NULL until verified from an official source.

## Initial discovery corpus
The owner's list (~80+ names from the prompt) is imported via
`POST /ai-center/discovery/import-seed` — idempotent, never re-inserts existing entries.
Entries arrive as DISCOVERED with `proposed_types` derived by inference (labelled as such:
`classification_basis = "model_inference"`). The status machine must be advanced manually
after human verification.

## Type classification
Every entry must be one or more of:
PROVIDER, MODEL, APPLICATION, RESEARCH_TOOL, DOCUMENT_TOOL, SEARCH_TOOL, ACADEMIC_TOOL,
PARSING_TOOL, WRITING_TOOL, EDUCATION_TOOL, VISION_TOOL, AUDIO_TOOL, MULTIMODAL_TOOL.

ChatGPT (APPLICATION) ≠ OpenAI API (PROVIDER).
Claude.ai (APPLICATION) ≠ Anthropic API (PROVIDER).
Consensus/Elicit/Scite = RESEARCH_TOOL, NOT generic PROVIDER.

## Research tool category
Specialized tools (Consensus, Elicit, Scite, Semantic Scholar, Scholarcy, ResearchRabbit,
Connected Papers, Litmaps, Inciteful, Explainpaper, Humata, MinerU, Cohere Parse) are
classified as SPECIALIZED_RESEARCH_TOOL and do not follow the provider/account/model
architecture. A future Research Tool Registry may integrate them as separate connectors.

## API surface
GET /ai-center/discovery?status=&limit=&offset= — paginated, filterable
PATCH /ai-center/discovery/{id} — advance status, record official URL, verification notes
POST /ai-center/discovery/import-seed — idempotent seed import
