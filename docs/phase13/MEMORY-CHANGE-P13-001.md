# MEMORY-CHANGE-P13-001

| Field | Value |
|---|---|
| Change ID | MEMORY-CHANGE-P13-001 |
| Date | 2026-09-17 |
| Phase | 13 (Analytics, Demand Intelligence, AI Access Control) |
| Trigger | Owner instruction: build the dashboard, apply the MASTER PRE-PHASE-13 context, write Phase 13 |
| Previous memory version | Phase 12 post-forensic (772 tests, CONDITIONAL) |
| New memory version | Phase 13 IMPLEMENTED / NOT VERIFIED / NOT ACCEPTED |

## What was discussed

The owner supplied the MASTER PRE-PHASE-13 context, the UX checkpoint
report, the checkpoint deliverables and the Phase 13 protocol, and asked
for (a) a redesigned dashboard, (b) the pre-Phase-13 work applied, and
(c) Phase 13 written and tested.

## What was proposed and ACCEPTED

ADR-076 (actor vocabulary to Core, generated plugin mirror) · ADR-077
(access policy, four precedence levels, default not-configured) · ADR-078
(append-only idempotent telemetry, NULL-preserving) · ADR-079 (IP, geo and
dwell collected, bounded, never inferred — **supersedes the ADR-046
privacy narrowing**) · ADR-080 (daily rollup, full recompute) · ADR-081
(a searched term IS a `Query`).

## What was REJECTED, and stays rejected

Strictest-wins precedence · default-forbid · default-allow labelled
`ALLOWED` · a price column on `paid` · bot/human-only counts · deriving
geography from IP · per-request Core calls from the plugin · independent
signature lists per runtime · auto-creating knowledge gaps from search
misses · storing dwell as an average · `ip_address` as a sortable field ·
any cross-session visitor identifier · any psychological or
purchase-readiness inference (checkpoint §76/§77, unchanged by ADR-079).

## What was IMPLEMENTED

Cloud Core: 8 enums, 2 scopes, 5 models, 5 services, 1 router with 15
endpoints, migration `0016`, `SORTABLE_FIELDS` extension,
`redis_available()`, `CORE_VERSION`.
Plugin 0.9.0 → 0.13.0: `AIOL_Telemetry`, `AIOL_Access_Gate`, `AIOL_Geo`,
regenerated `AIOL_Actors`, `view-dashboard.php`, `aiol-dwell.js`, design
system synced in (closes checkpoint UX-08).
Frontend: 7 icons added to the canonical registry (67 → 74); 3 harness
screens; `docs/ux/DASHBOARD_UX.md`.

## What was TESTED

`node visual-harness/check.js` → 33 passed / 0 failed.
Python static parse of every `cloud-core/app` file → clean.
`node --check` on the beacon → clean.
Signature parity Python↔PHP → verified by script at authoring time.

## What FAILED or was BLOCKED

Everything else. No FastAPI, SQLAlchemy, pytest, Alembic, PostgreSQL, PHP
binary, browser or network egress. ~50 Python tests and 2 PHP test files
were **written and never executed**. 11 mutations planned, 0 run. The
Phase 0–12 regression suite was not run against this tree.
`measure.js` exits 2 — visual gate UNKNOWN.

## What remains BLOCKED (carried forward, unchanged)

Live AI platforms · Google Search Console · SERP provider · real
WordPress · real WooCommerce · browser rendering · RTL as painted.

## Changed files

See `MANIFEST.json` in the handoff package.

## Verification state

```
PHASE 13 = BLOCKED
PHASE 14 = LOCKED
```

Phase 12 remains `CONDITIONAL`; MASTER §146 locks Phase 13 on that alone,
independently of the environment blockers above.

## Provenance

Authored in a sandbox with no network and no application runtime. Every
claim in the Phase 13 report about what does and does not exist was
checked against a file in the repository, not against a previous report.
