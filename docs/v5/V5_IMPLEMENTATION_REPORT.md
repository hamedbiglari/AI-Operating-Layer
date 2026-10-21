# Master Execution Prompt (v5) — implementation report (prompt §94)

Covers the work done against `V5_FORENSIC_AUDIT_AND_GAP_REPORT.md` on 2026-10-20 and 2026-10-21. Nothing here is
committed yet: the working tree is commit `d192804` plus the uncommitted v4 and v5 work. Migration head: **`0046`**.

Status vocabulary (§38/§82): **COMPLETE_AND_VERIFIED**, **IMPLEMENTED_BUT_UNVERIFIED**, **BACKEND_ONLY**,
**IMPLEMENTED_BUT_LIVE_PROVIDER_NOT_VERIFIED**, **BLOCKED_WITH_REASON**.

## A. Already implemented before v5 (FACT, read in code)
PostgreSQL as the system of record; Celery as dispatcher only. Per-tenant providers, accounts and models, with
encrypted credentials and Anthropic + OpenAI adapters. Six routing modes with persisted explanations. Wallet
reserve/settle. Checkpoint + handoff before every account switch. Source access states, `claim_evidence`
many-to-many, `evidence_conflicts`, compound-route-is-indirect DB CHECK. Coverage audit, master topic matrix,
Vancouver citations. From v4: CDR, context assembly with output reserve, coverage-preserving synthesis, command
workspace, knowledge chat with eight answer states and approval-gated research, auth sessions, prompt-injection
defence.

## B. Extended in v5
| ADR | What | Status |
|---|---|---|
| 131 | AI-job worker lease, stale-lease recovery sweep, capacity deferral (`resume_after`), bounded auto-resume | IMPLEMENTED; sweep needs `celery beat` deployed |
| 132 | Provider `Retry-After` sets how long an account rests | IMPLEMENTED_BUT_LIVE_PROVIDER_NOT_VERIFIED |
| 133 | Working-memory lifecycle as a DB CHECK, supersede rule, model output starts `created`, access-level CHECK | COMPLETE (backend); dashboard shows status |

## C. Newly implemented in v5
| ADR | What | Status |
|---|---|---|
| 134 | Knowledge Transfer Package v1 + deterministic validator (quotes checked against stored text, §35 directness) + reconciler (duplicate → evidence link, variant kept, contradictions → `evidence_conflicts`); `ai_jobs.output_contract='ktp_v1'` | Backend tested. Dashboard list + per-claim verdicts added 2026-10-21: IMPLEMENTED_BUT_UNVERIFIED in a browser |
| 135 | Task DAG: `ai_job_items.depends_on`, acyclicity checked at creation, dependency-aware scheduling, `DEPENDENCY_FAILED` propagation, `waiting_on` in the handoff | COMPLETE (backend, API). No dashboard editor: jobs are created through the API or by services |
| 136 | Model capability limits (max in/out, RPM/TPM, structured-output/tool flags, `capability_source`); oversized items fail `CONTEXT_OVERFLOW` before any call; admin PATCH, audit-logged | Backend tested. Dashboard "Models and their limits" card added: IMPLEMENTED_BUT_UNVERIFIED in a browser |
| — | Residual risk register (`RESIDUAL_RISK_REGISTER.md`) | Done; updated 2026-10-21 |
| — | Dashboard: provider form now offers the `openai` adapter (ADR-121 had added it to the backend only) | IMPLEMENTED_BUT_UNVERIFIED in a browser |

## D. Still incomplete
* **§38 control-by-control dashboard audit.** Not done. It needs a browser, and none can be launched in this
  environment (see E).
* **Oversized items are not split or re-routed automatically** in plain AI jobs (ADR-136). They fail visibly.
  Synthesis runs do split.
* **RPM/TPM are recorded, not enforced.**
* **DAG branches run one at a time** per job, and a dependency orders work without passing outputs (by design, §22).
* **Free-text AI jobs still exist.** Only `ktp_v1` jobs reach the knowledge layer.
* **No scheduled living-knowledge rerun (§68).**
* **No distributed-vs-strong-model benchmark (§78).**

## E. Could not be verified here
* **Any live provider call.** No API key exists, so every provider path is IMPLEMENTED_BUT_LIVE_PROVIDER_NOT_VERIFIED.
* **Browser rendering of the dashboard changes.** The installed Chrome exits at launch (code 21), Edge is not
  installed, and Playwright's own Chromium is not downloaded. What was verified instead: `visual-harness/check.js`
  33/33 rules, every inline script parses, and the API routes the UI calls are covered by tests.
* **WordPress plugin PHP tests.** PHP is absent.

## F/G. Tests
All runs against real PostgreSQL 16 + pgvector (`.devdb`), Windows 11, Python 3.13.

| Run | Scope | Result |
|---|---|---|
| Baseline 2026-10-21 (code and DB at `0044`, before ADR-135/136; `-x`, so it stops at the first failure) | full suite | **599 passed, 1 failed, then stopped** (60 min). Log: `.devdb/baseline_2026-10-21.txt` |
| Targeted, after changes (DB `0046`) | `test_v5_task_dag` (9), `test_v5_model_limits` (8), `test_v5_job_durability`, `test_v5_memory_lifecycle`, `test_v5_knowledge_reconstruction`, `test_ai_center` | **all passed** (54 + 8 + 25) |
| Migration cycle | `0044 → 0045 → 0044 → 0045`, `0045 → 0046 → 0045 → 0046` | exit 0 |
| Dashboard static rules | `visual-harness/check.js` | 33 / 33; every inline script parses |
| **Full suite at head `0046`** (no `-x`, 2026-10-21) | 1566 tests | **1561 passed, 2 failed, 3 skipped** (2 h 35 min). Log: `.devdb/full_head0046_2026-10-21.txt` |

**No regression from v5.** Both failures are environment-dependent and explained below. The file-mode one also
failed in the pre-change baseline. The baseline stopped there (`-x`), so it never reached the time-zone one;
that test passes with `PGTZ=UTC` and touches no code changed in v5. The 2026-10-20 run also showed a failure at
the same position (SIGNAL, its log is truncated). The 3 skips are `test_security_audit_2026_10.py:110`: Redis is not running here, and
the rate limiter allows requests when Redis is down, by design. They are not verified in this environment.

**Known failure, environment (not a regression):** `test_original_retention.py::test_stored_file_is_not_world_readable`
asserts POSIX mode `0600`. `app/ingestion/storage.py:95` does call `os.chmod(…, 0o600)`, but NTFS cannot represent
that, so Python reports `0o666`. Neither file was changed in v5. Expected to pass on the Linux/Docker target;
BLOCKED_WITH_REASON here. On a Windows host the original-file store needs an ACL-based restriction, which is not
implemented.

**Known failure, environment-dependent (pre-existing, not a regression):**
`test_phase12_visibility.py::test_tested_at_is_preserved_not_overwritten`. The stored instant is correct
(`19:13:48+03:30` = `15:43:48Z`), but the API renders timestamps in the DB session's time zone, and this dev
Postgres runs in local time (+03:30) while the test compares UTC text prefixes. With `PGTZ=UTC` it passes.
**Finding:** the application does not pin its DB sessions to UTC, so the offset in API output depends on the
server environment. **Fixed 2026-10-21:** `app/db/session.py` now opens every session with `-c timezone=UTC`
(`CONNECT_ARGS`), and the test engine in `tests/conftest.py` uses the same value. The server default here stays
`Asia/Tehran`; app sessions report `UTC`, and the test passes without `PGTZ` (`test_phase12_visibility.py` +
`test_v5_job_durability.py`: 41 passed). The full-suite figures above predate this fix.

## H. Known limitations
Quote matching is exact after normalisation, so paraphrased evidence is rejected (deliberate). Execution is
at-least-once: an in-flight item may run twice after a worker dies. Unknown model limits block nothing.

## I. Security findings (this pass)
All new routes are tenant-scoped through the credential: the model PATCH returns 404 cross-tenant (tested), and
package reads filter on the caller's organization (tested). Writes need the admin or editor role. The new
dashboard code renders server values with `textContent` only. No secret is logged; the audit row for limit
changes holds only numbers and the source label.

## J. Resource/cost findings
Before ADR-136 an item larger than the model window was sent and paid for or rejected by the provider. It is now
refused before the call when the limit is registered. The cost gate is unchanged.

## K. Database migrations (all additive and reversible; up → down → up run for 0045 and 0046)
`0042` lease and deferral · `0043` memory lifecycle · `0044` knowledge transfer packages + `ai_jobs.output_contract`
· `0045` `ai_job_items.depends_on` · `0046` `ai_models` capability limits.

## L. Provider requirements
An official API key per provider account (Anthropic and/or OpenAI), with model limits entered from the provider's
documentation, plus `celery beat` running for recovery and auto-resume.

## M. Remaining risks
See `RESIDUAL_RISK_REGISTER.md`. The highest is R-17: no live provider has ever been called.

## N. Recommended next stage
1. Configure one real provider key and run the pilot runbook: the first live verification of ADR-131/132/134/136.
2. Run the §38 dashboard audit in a working browser, starting with the two cards added here.
3. Automatic split or re-route of oversized items in plain AI jobs.
4. Scheduled living-knowledge refresh (§68).
5. Benchmark corpus for §78 once a provider is live.
