# AI Center — Forensic Audit (before implementation, 2026-09-25)

## Existing state (FACT, from source)
- AIExecution (0017/0018): canonical, immutable, one row per real invocation; `provider` + `model` are free strings; no account concept; arc parent = `visibility_run` only.
- One provider adapter (`app/integrations/llm/anthropic.py`), credential from a single environment variable (`ANTHROPIC_API_KEY`); no per-tenant or per-account credentials.
- Retry / provider fallback / model fallback already produce new executions (`invoke_with_policy`), but targets come from settings, not a registry.
- No provider/account/model registry, no routing policy, no working memory, no checkpoint/handoff, no keyword workspace, no demand connectors (GSC/GA4), no Walrus client.
- Research tasks exist with an honest NotConfigured provider (no search API).
- Telemetry/search-demand (Phase 13) exists: first-party page views, internal search demand.
- Every table must carry `organization_id` (enforced by `test_forensic_integrity`).
- Canonical project memory lives in `docs/ai-context/` (+ `docs/DECISIONS.md` for ADRs, last ADR-086).

## External facts not available in this environment
- No AI provider credentials of any kind; no Google Search Console / GA4 OAuth client; no Walrus endpoint/credentials.

## Bounded plan for this session (and what is explicitly NOT done)
Implemented (backend + tests; see AI_CENTER_FINAL_VERIFICATION.md for runtime/browser status): REQ-AIC-001, 002, 003, 004, 005, 007, 008, 011, 012, REQ-AIC-006 (boundary only), REQ-KW-001, 002, 003, REQ-MEM-001.
Registered but NOT implemented now (open gaps, owners recorded): REQ-DI-001/002/003 (connectors need external credentials; first-party telemetry exists), REQ-AIC-009 provider web verification of the discovery list, REQ-AIC-010 provider usage/balance sync, REQ-KO-001 Knowledge Object page expansion, REQ-SET-001 backend persistence of every Settings preference, REQ-UX-001 full English-locale cleanup, REQ-KW-004 keyword→published-content traceability beyond research tasks.
Not established: platform AI credits / billing (ADR-082..084 remain PROPOSED; the prompt itself conditions it on authoritative approval).
