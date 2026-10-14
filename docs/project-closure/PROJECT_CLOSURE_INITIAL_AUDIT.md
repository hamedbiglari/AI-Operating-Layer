# Project Closure — Initial Forensic Audit (read-only, before any change)

## Repository state (FACT)
- No git repository (`git status`: not a git repository). History cannot be taken from commits.
- Tree: `cloud-core/` (FastAPI backend, 18 migrations 0001–0018), `wordpress-plugin/` (38 PHP files, 12 standalone test files), `visual-harness/` (single-file dashboard prototype), `frontend/` (design-system CSS + icons only), `docs/`, `docker-compose.yml`.
- API surface: 145 `/api/v1` paths (adapter, ai, ai-executions, auth, claims, claim-evidence, commerce-mappings, context, credentials, documents, entities, evidence, health, installations, knowledge, knowledge-gaps, mappings, offers, organizations, product-evidence, products, queries, query-clusters, query-groups, recommendations, relationships, research, sites, sources, sync-jobs, telemetry, trust-records, users, visibility).
- Not present in the API (FACT, route scan): OTP/verification-code auth, support tickets, billing/wallet/subscription/trial, admin endpoints, cart/click/purchase tracking, signed cart intent.

## Authoritative documents
- `docs/master-spec/MASTER_SPEC.md` (66 sections; §62 phase order 0–16; §54 MVP scope; §55 MVP pilot; §56 MVP success loop; §63 architectural rules; §66 final goal).
- `docs/DECISIONS.md` (ADRs incl. ADR-079 IP/geo), `docs/ai-context/*` (project memory), `docs/phase13..17/*`, `docs/billing/BILLING_DATA_MODEL.md` (Status: DESIGNED).
- Phase 14–17 governing prompts: supplied by the owner in the working conversation; their requirements are reflected in the phase documents.

## Historical evidence availability
- Phases 0–12: `HISTORICAL_EVIDENCE_UNAVAILABLE` for the original conversations. Available: repository docs (CURRENT_STATE phase list, DECISIONS, development.md, audits) and the executable test suite.
- Phases 13–17: phase documents present in `docs/`.

## Phase inventory (FACT, from phase documents)
| Phase (as executed) | Master §62 name | Recorded verdict |
|---|---|---|
| 0–11 | Foundation … AI/REST interfaces | recorded complete in CURRENT_STATE |
| 12 | AI Visibility | CONDITIONAL (live provider ENVIRONMENT BLOCKED) |
| 13 | Rights layer (+ analytics, demand, access) | BLOCKED (never executed at the time) |
| 14 | Dashboard (executed as integration/runtime) | BLOCKED |
| 15 | Pilot | CONDITIONAL PASS (+ manual-retry correction) |
| 16 | Scale (redefined by the owner as AIExecution architecture lock) | ARCHITECTURE_LOCKED |
| 17 | (owner-defined) AIExecution + first provider | BLOCKED (external credential) |

## Conflicts found
- C-1: Master §62 Phase 16 = "Scale"; the owner redefined Phase 16 as the AIExecution architecture lock and added Phase 17. Later explicit owner decision prevails; "Scale" is not lost — master §55 says scale only after the MVP loop works (it does not yet).
- C-2: DECISIONS.md (plugin absorption, line ~673) "no IP address is stored anywhere" vs ADR-079 + P13-REQ-002 (IP collected, truncated, 30-day horizon). ADR-079 is later and owner-backed; the plugin test encoding the older rule is stale.
- C-3: `docs/ai-context/CURRENT_STATE.md` still says "Current Phase: Phase 13 … PHASE 14 = LOCKED" and "Next Phase: Phase 10" — project memory not synchronized with Phases 14–17.

## External dependencies
AI provider credential (absent); WordPress + WooCommerce runtime (not downloadable: wordpress.org is outside the network allow-list); Docker (absent). PHP: absent at the start of the project, installable via the Ubuntu archive in this environment (installed during this audit).

## Correction (later pass)
"WordPress/WooCommerce not obtainable" was wrong. wordpress.org is outside the allow-list, but
WordPress, WooCommerce and WP-CLI are published on GitHub (allowed). A real WordPress 6.6.2 +
WooCommerce 9.3.3 runtime was built and used for E2E-K2C-001.
