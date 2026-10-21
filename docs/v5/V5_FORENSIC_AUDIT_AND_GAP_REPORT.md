# Master Execution Prompt (v5) — Phase A forensic audit, Phase B gap report, Phase C order

Audited 2026-10-20 against this working tree: commit `d192804` plus the **uncommitted** v4 work
(migrations `0037`–`0041`, chat, CDR, synthesis, workspace, auth sessions). The v4 audit
(`docs/v4/V4_GAP_ANALYSIS.md`) is still valid and is not repeated. This document covers only what the
v5 prompt adds or tightens.

Basis key (§3): **FACT** = read in code or executed in this session · **SIGNAL** = documented, not
executed here · **INFERENCE** · **UNKNOWN**.

## 1. Where the system actually is (FACT)

| Item | Finding |
|---|---|
| Repository | `graphify-src/02-core-tool-full-repo` (own git; the home-directory git is unrelated) |
| Stack | FastAPI, SQLAlchemy 2, Alembic, PostgreSQL 16 + pgvector, Celery + Redis, single-file dashboard (`visual-harness/index.html`, 52 screens), static website, WordPress adapter (PHP) |
| Size | 71 model modules, 73 services, 44 API modules, migrations `0001`–`0041`, 104 test files |
| System of record | PostgreSQL. Celery ignores results; the rows are the record (`workers/celery_app.py`). Walrus is an optional mirror (`integrations/memory/walrus.py`). Matches §4 and §58. |
| Providers | `ai_providers` / `ai_provider_accounts` / `ai_models` per tenant (BYOK), Anthropic + OpenAI adapters, encrypted credentials. **No live call ever made** (no keys) → every provider path is `IMPLEMENTED_BUT_LIVE_PROVIDER_NOT_VERIFIED`. |
| Test baseline | see `.devdb/baseline_2026-10-20.txt` (recorded in §6 below) |

## 2. Trace of the long-running AI path (UI → API → Service → DB → Worker → Provider → Persistence)

`POST /ai-center/jobs` → `ai_job_service.create_job` (rows in `ai_jobs`, `ai_job_items`, `job_state` memory)
→ Celery `ai_center.run_job` → `ai_job_service.run_job` → `ai_routing_service.decide` (persists
`ai_routing_decisions`) → `ai.invocation.invoke_once` (one `ai_executions` row per call, wallet
reserve/settle) → adapter → result stored as `intermediate_finding` memory; on a switch stop a
`processing_checkpoint` + `ai_handoff` are written first.

## 3. Gap matrix for the v5 additions

| § | Requirement | Status | Evidence / finding |
|---|---|---|---|
| 10, 86 | Worker lease recovery for long jobs | **BROKEN** | `run_job` sets `running` and holds no lease. If the worker dies, the job stays `running` forever: `run_ai_job` skips any job not in `queued/paused/blocked`, and no sweeper touches `ai_jobs`. The `ai_executions` reclaimer only marks the in-flight call `abandoned`. Workflow B cannot complete. |
| 9, 74, Workflow D | Wait for quota reset / defer and resume | **MISSING** | When every account is rate-limited or out of quota the job becomes `blocked` and nothing ever resumes it, although `ai_provider_accounts.unavailable_until` is known. Nothing distinguishes "wait" from "needs the user". |
| 9 | Honour provider `Retry-After` | **MISSING** | Neither adapter reads the header; `record_health(retry_after=…)` is never passed a value from an execution. A fixed avoid window (60 s / 3600 s) is used instead. |
| 74 | Bounded retries | **EXISTS** (per run) | Accounts are excluded once they stop; the loop ends when the pool is empty. Across runs there is no bound yet (it is added together with the deferral, see §5). |
| 10, 50 | Task DAG with dependencies | **MISSING** | `ai_job_items` and `research_tasks` are flat lists; there is no dependency edge. |
| 11–14, 55, 87 | Typed memory with ACL, lifecycle and scope | **PARTIAL** | `ai_working_memory` is versioned, tenant-scoped, idempotent by content hash, carries provenance (FACT). Missing: lifecycle CHECK (`status` is free text and never changes), supersede rule, per-agent READ/WRITE/ADMIN, retention policy. |
| 21, 51–53 | Knowledge Transfer Package, Validator, Reconciler | **MISSING** | Worker output is stored as free text in memory (`result`). Nothing validates it against a schema or reconciles it into `claims`/`claim_evidence`. `current_synthesis` is explicitly "a mechanical merge". Workflow A therefore cannot run. |
| 23 | One canonical claim + N evidence links | **EXISTS** in schema | `claim_evidence` many-to-many with `evidence` (ADR-101/108). Not fed by workers (see above). |
| 25 | Contradictions preserved | **EXISTS** | `evidence_conflicts` (ADR-110); the system never picks a side. |
| 7 | Provider capability metadata (max in/out, RPM/TPM, pricing, source, verified-at) | **PARTIAL** | `ai_models` has `context_window`, capabilities, modalities, `last_verified_at`. Missing: max input/output, RPM/TPM, structured-output/tool flags, `capability_source`. Pricing lives in config (`ai/pricing.py`). |
| 15–17 | Context assembly, budget, output reserve | **EXISTS (v4)** | `ai/context_assembly.py`, used by chat and synthesis. Not used by plain AI jobs. |
| 17 | Truncation detection, partial output persistence | **PARTIAL** | `stop_reason` recorded on executions; no "resume missing output". |
| 20 | Source access states | **EXISTS** | ADR-107. |
| 32–33 | Master Topic Matrix, coverage audit | **EXISTS** | ADR-114/115 (v4 fixed the processing-dimension bug). |
| 34 | Vancouver citations | **EXISTS** | ADR-116. |
| 40–47 | Knowledge Chat, research approval, states | **EXISTS (v4, uncommitted)** | All eight answer states, approval-gated research, persistence, tenant isolation tests. |
| 56 | Persistent command workspace | **EXISTS (v4, uncommitted)** | |
| 72 | Residual risk register | **MISSING** as a register | Risks are scattered across `KNOWN_ISSUES.md`, `DEBT_REGISTER.md` and exception registers. |
| 38 | Control-by-control dashboard audit | **NOT DONE IN THIS PASS** | 52 screens. Earlier passes verified 33 dashboard rules and responsive layouts (SIGNAL). A per-control classification needs a browser run and is still open. |
| 78 | Distributed vs strong-model benchmark | **BLOCKED** | Needs live provider credentials. |

Duplications (§69): two job tables (`sync_jobs` for ingestion and `ai_jobs` for AI work), kept on purpose by
earlier ADRs. Nothing in this pass adds a third.

## 4. Implementation order (Phase C)

Ordered by the prompt's priority list (correctness → persistence → security → orchestration → integrity → resources):

1. **Durable AI-job execution**: worker lease, stale-lease recovery, deferral until the quota resets, and a
   bound on automatic resumes. Closes Workflows B and D at the job level. *(done: ADR-131)*
2. Read `Retry-After` from the provider adapters and feed it into `unavailable_until`. *(done: ADR-132)*
3. Memory lifecycle (`CREATED→VALIDATED→ACTIVE→SUPERSEDED→ARCHIVED`) as a DB CHECK, plus the supersede rule. *(done: ADR-133)*
4. Knowledge Transfer Package schema + Validator + Reconciler into `claims`/`claim_evidence`/`evidence_conflicts`
   (Workflow A). *(done: ADR-134; dashboard view still missing)*
5. Item dependencies (task DAG) on `ai_job_items`. *(done: ADR-135)*
6. Provider capability metadata columns on `ai_models`. *(done: ADR-136; max input/output enforced, RPM/TPM recorded only)*
7. Residual risk register (`docs/v5/RESIDUAL_RISK_REGISTER.md`). *(done)*
8. Dashboard control audit in a browser (§38).

## 5. Implemented in this pass

See `docs/v5/V5_IMPLEMENTATION_REPORT.md`.
