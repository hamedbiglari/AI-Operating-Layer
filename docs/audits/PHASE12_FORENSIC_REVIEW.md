# Phase 12 — forensic reconciliation of Phases 10 and 11

Performed before any Phase 12 code was written.

## Findings

| # | Check | Result |
|---|---|---|
| F1 | Dead wiring (Celery task defined but never dispatched) | **CLEAN** — `research.execute_task` defined and dispatched |
| F1b | Enums declared but never referenced | **CLEAN** — none |
| F2 | Router modules defined but never registered | **CLEAN** — 20/20 registered, 150 `/api` routes |
| F3 | Query / Intent / QueryGroup available for reuse | **PRESENT** — Phase 12 must consume, not duplicate |
| F4 | `SyncJobType` reusable for visibility jobs | **COMMERCE-ONLY** — needs additive extension |
| F5 | Composite tenant-FK pattern | **ESTABLISHED** (ADR-037) — Phase 12 tables adopt at creation |
| F6 | Rate limiting | **PRESENT** (ADR-039), per-installation |
| F7 | **Cost / budget guard** | **ABSENT** — no `budget`, `estimated_cost` or `token_usage` anywhere |
| F8 | `AdapterScope` extensible | **YES** — Phase 12 extends, does not replace |

**F7 is the material finding.** Phase 12 is the first phase whose work has
a direct external monetary cost (platform queries). Nothing in the codebase
guards spend. A Phase 12 that queried platforms without a budget ceiling
would be the first component able to generate unbounded cost.

## Carried-forward blockers — none cleared by Phase 12

WordPress runtime · WooCommerce runtime · `WC_Product` behaviour · variation
handling · currency resolution · WordPress hooks · WP-Cron runtime ·
browser/visual verification · RTL verification.

Phase 12 is Core-only and clears none of them.

## MarkItDown

**E — NOT IMPLEMENTED** (`MARKITDOWN_AUDIT.md`). Phase 12 records this and
builds no parallel parser, per its own §32.
