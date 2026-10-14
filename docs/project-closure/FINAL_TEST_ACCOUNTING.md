# FINAL TEST ACCOUNTING (2026-09-28)

| Suite | Total | Passed | Failed | Skipped | XFAIL | Deselected / not run | Command / notes |
|---|---|---|---|---|---|---|---|
| Backend (pytest), fresh DB | 1217 | **1217** | 0 | 0 | 0 | 0 | eight chunks: 123 + 155 + 190 + 248 + 144 + 163 + 100 + 94 (2026-10-06, migrations 0001→0036) |
| Migration upgrade → downgrade → upgrade | 1 cycle (0001 → 0032 → base → 0032) | pass | — | — | — | — | scripts/verify_migration_cycle.sh on a fresh database |
| Plugin (PHP) | 221 assertions | **221** | 0 | 0 | — | 0 | wordpress-plugin/tests/run.sh; PHP lint clean |
| Dashboard rules | 33 | **33** | 0 | — | — | — | visual-harness/check.js |
| Responsive | 45 screens × 6 widths × 2 directions | clean | 0 | — | — | — | 0 overflow, 0 escapes, 0 targets < 24 px |
| English locale | 44 screens | clean | 0 | — | — | — | 0 Persian UI strings / attributes |
| Live API — E2E-K2C-001 | 1 flow | pass | — | — | — | — | real WordPress 6.6.2 + WooCommerce 9.3.3 at Cloud Core 0032: order #30 |
| Live API — tenant isolation | 9 direct + 4 lists + AI answer | pass | — | — | — | — | all 404 / empty / no leak |
| Live API — AI job via Celery worker | 1 job, 4 items | pass | — | — | — | — | 4 AIExecutions (test_provider), SSE shows completion |
| Browser — wallet, SSE, export, chips | 1 run | pass | — | — | — | — | no provider → BLOCKED + disabled; sandbox top-up credited only after webhook |
| Live scholarly providers | — | — | — | — | — | **NOT RUN** | hosts blocked by the sandbox (BLOCKED_EXTERNAL_DEPENDENCY) |
| Live commercial AI provider | — | — | — | — | — | **NOT RUN** | no credential |

## Section 13 coverage (test names in cloud-core/tests)
provider isolation — test_ai_center · credential encryption — test_ai_center · model routing — test_ai_center (six modes) ·
task routing — test_background_worker_enforcement, test_background_enforcement · job progress — test_ai_center ·
SSE progress — test_sse_streams_progress_until_terminal, test_sse_reports_cancellation, test_sse_is_authenticated_and_tenant_scoped ·
pause/resume/cancel — test_ai_center, test_sse_reports_cancellation · memory export — test_memory_export_is_complete_and_audited ·
memory export tenant isolation — test_memory_export_is_tenant_isolated_and_admin_only · billing isolation — test_billing_is_tenant_isolated ·
wallet reservation — test_reservation_and_settlement, test_reservation_idempotency · wallet settlement — test_reservation_and_settlement ·
insufficient balance — test_insufficient_balance · payment idempotency — test_payment_idempotency ·
webhook replay — test_webhook_credits_once_and_rejects_replays, test_webhook_amount_mismatch_never_credits ·
source deduplication — test_federated_search_dedups_by_doi_pmid_and_title · abstract-only source — test_discovery_never_claims_full_text_and_creates_no_evidence ·
full-text acquisition — test_full_text_is_claimed_only_after_a_real_document, test_a_landing_page_is_not_full_text, test_acquisition_only_from_recorded_open_access_locations, test_acquisition_passes_through_the_ssrf_guard, test_acquisition_is_tenant_scoped ·
compound indirectness — test_compound_evidence_stays_indirect, test_only_a_study_of_the_subject_is_direct · knowledge gap Find More — test_knowledge_gap_find_more ·
tenant isolation / SSRF / authentication / authorization — across the suite (incl. test_url_ingestion_security, test_money_moving_endpoints_need_an_admin).
Conditional skip markers exist in four files (fixtures missing, PostgreSQL unreachable, plugin checkout absent); none triggered.

passwordless sign-up — tests/test_passwordless_signup.py (12): happy path, code never stored/returned in clear, wrong-code lockout,
expiry, one-time use, verify without request, resend cooldown + hourly cap, no enumeration, email taken in between, delivery
unavailable, validation, two sign-ups are separate tenants.

user-supplied full text (ADR-107) — 5 tests: attach with provenance and audit, unparsed/tiny upload claims nothing,
foreign document or tenant refused, access states recorded but never full text, DB refuses a full-text claim without an origin.

multi-compound and routes (ADR-108) — 8 tests: one search per route, compounds taken from the knowledge object, no indirect
route can be direct (parametrised over 7 routes, API and DB), candidates say what they are about, the graph never turns a
compound path into subject evidence, unsearchable route refused, graph tenant-scoped.

dependency and saturation (ADR-109) — 9 tests: reviews of one trial count once, a citation stays independent, transitive
chains, validation/idempotency/isolation/self-dependency, the real stopping reason, duplicates-only, routes still to run,
all providers down is not saturation, declare and reopen.

Memory Center, confidence and conflicts (ADR-110) — 10 tests: search/filter/sort, versions and compare, all four export
formats, scope + audit, tenant isolation and admin-only export, confidence separate from strength, machine extraction cannot
claim certainty, conflict with comparison, a resolution needs a reason, conflicts tenant-isolated.

research planning (ADR-111) — 10 tests: query set saved/edited/re-run and comparable, validation and isolation, completion
task lifecycle, wrong-kind evidence refused, dead end needs a reason, isolation, four new gap types.
§43 acceptance (ADR-112) — 1 test walking all twenty steps end to end on the production code path.

planning, modes, gaps and acceptance (ADR-111) — 17 tests, including `test_taranjabin_end_to_end`, which runs all twenty
§43 acceptance steps through the production code path and asserts only what the system recorded.

**§43 acceptance** — `tests/test_acceptance_taranjabin.py`: one test, twenty steps, production code path.

category schema and Master Topic Matrix (ADR-114) — 12 tests: starter schema per category, object_type untouched and an
uncategorised topic still works, apply-schema is idempotent, the matrix is live data with honest empty cells, status derived
from claims and evidence, a closed cell needs a written reason (API and DB), a person's decision survives recalculation,
a discovered section is proposed not copied, deciding a proposal, sections outside the schema stay visible, tenant isolation,
validation.

coverage audit (ADR-115) — 12 tests: six dimensions and no single number, dimensions moving independently, unknown never
reported as zero, closed sections excluded from the denominator, a new version per run with history, a failed audit leaving
the last good one standing (API and DB), never_run said plainly, cross-topic category analysis, stale flag cleared, pending
evaluations surfaced, tenant isolation, editor-only runs.

Vancouver citation (ADR-116) — 22 tests, one per case the prompt names: first source is 1, second new source is 2,
a repeated source reuses its number, ten consecutive compress to (1–10), non-consecutive stay (1,3,5,8,11), order is first
appearance not alphabetical, the reference list follows citation order, no number is shared and no source numbered twice
(API and DB), every number resolves, an unsupported sentence is marked not invented, a non-supporting source is refused,
indirect stays indirect, an abstract-only source is marked, a duplicate ingestion takes one number, resolving twice is
deterministic, reordering renumbers deterministically, an earlier version keeps its numbering, a sentence and a paragraph
may cite more than ten, references built only from stored metadata, the audit separates presence/validity/support,
the DB refuses a resolved factual sentence without a citation, tenant isolation.

dashboard knowledge screens (ADR-117) — browser-verified against a live backend; dashboard rules 33/33; responsive
48 screens × 6 widths × LTR/RTL, 0 overflow, 0 small targets; English locale 0 Persian strings. Plus one resolver test:
sources first cited together follow evidence-attachment order.

Website management (ADR-118) — 9 tests. During this pass two existing tests (test_sorting) correctly caught that the new
list endpoints did not support sorting; the endpoints were fixed (not the test's exclusion list) and a sorting test added.
The PHP plugin suite was not re-run in this pass: the plugin was not changed, and PHP is not installed in the rebuilt environment.
