# Phase 13 — Requirement matrix

**Generated IDs.** The project defines no stable Phase 13 requirement IDs,
so `P13-REQ-nnn` was created for traceability in this phase. These IDs
**did not come from the original specification** and are labelled as
generated wherever they appear, per the Phase 13 protocol §21.

**Origin column.** `OWNER` means the project owner stated it directly in
the Phase 13 instruction. `CHECKPOINT` means it comes from
`PRODUCT_UX_ARCHITECTURE_CHECKPOINT_REPORT.md`. `MASTER` means the
MASTER PRE-PHASE-13 context. Nothing here is inferred.

**Status vocabulary** is the protocol's: PASS / PARTIAL / FAIL / BLOCKED /
UNKNOWN / NOT APPLICABLE. **No requirement below is PASS**, because no
test in this phase has been executed — see §Verification in
`PHASE13_REPORT.md`. `IMPLEMENTED` is recorded in the Implementation
column and is deliberately *not* a status.

---

## Legend for evidence columns

| Value | Meaning |
|---|---|
| `IMPLEMENTED` | code exists and is inspectable at the named path |
| `WRITTEN` | test exists at the named path, **never executed** |
| `BLOCKED` | cannot be produced in this environment |
| `N/A` | genuinely does not apply, with the reason stated |

---

## A. Analytics and telemetry

| ID | Requirement | Origin | Implementation | Test | Runtime | Visual | Status |
|---|---|---|---|---|---|---|---|
| P13-REQ-001 | Record per-visit geographic location | OWNER | `models/page_view.py` `geo_*`, `class-aiol-geo.php` | `test_phase13_telemetry.py::test_supplied_geo_is_stored_with_its_method_and_coarse_coordinates` WRITTEN | BLOCKED | BLOCKED | **BLOCKED** |
| P13-REQ-002 | Record visitor IP, bounded by a retention horizon | OWNER + ADR-079 | `page_view.ip_address` / `ip_truncated` / `ip_retained_until`; `telemetry_service.enforce_retention` | `test_retention_nulls_the_address_and_keeps_the_prefix`, `test_truncate_ip` (5 cases) WRITTEN | BLOCKED | N/A | **BLOCKED** |
| P13-REQ-003 | Record time on page (dwell), NULL when unmeasured | OWNER | `page_view.dwell_ms`, `aiol-dwell.js`, `AIOL_Telemetry::receive_dwell` | `test_unreported_dwell_stays_null_end_to_end`, `test_mean_dwell_is_null_not_zero_when_no_samples`, `test_reported_dwell_is_preserved_and_averaged_over_real_samples` WRITTEN | BLOCKED | BLOCKED | **BLOCKED** |
| P13-REQ-004 | Separate human and machine view counts | OWNER | `content_view_daily` six-way split | `test_total_views_equals_the_sum_of_its_parts`, `test_ai_answer_views_are_not_merged_into_crawler_views` WRITTEN | BLOCKED | BLOCKED | **BLOCKED** |
| P13-REQ-005 | Sort content by view count, ascending **and** descending, with the numbers | OWNER | `SORTABLE_FIELDS["ContentViewDaily"]`, `GET /telemetry/content-stats` | `test_content_stats_sort_ascending_surfaces_least_seen_first`, `test_unknown_sort_field_is_422_naming_the_allowed_values` WRITTEN | BLOCKED | BLOCKED | **BLOCKED** |
| P13-REQ-006 | Ingestion is idempotent under adapter retry | MASTER §53 | `event_key` + `uq_page_views_organization_event_key` | `test_redelivered_batch_does_not_double_count`, `test_partially_new_batch_accepts_only_the_new_events` WRITTEN | BLOCKED | N/A | **BLOCKED** |
| P13-REQ-007 | Server-side pagination, filtering, sorting for large collections | MASTER §100 | `telemetry_service.list_*`, `apply_sort` (ADR-056 reused, not reimplemented) | covered by P13-REQ-005 tests WRITTEN | BLOCKED | N/A | **BLOCKED** |
| P13-REQ-008 | Query string never stored | ADR-046 carried forward | `PageViewIngest.strip_query_string`, `AIOL_Actors::safe_path` | `test_query_string_is_stripped_from_the_stored_path` WRITTEN | BLOCKED | N/A | **BLOCKED** |

## B. Demand intelligence

| ID | Requirement | Origin | Implementation | Test | Status |
|---|---|---|---|---|---|
| P13-REQ-010 | Record what humans searched for | OWNER | `search_demand_service.record_search` | WRITTEN (`test_phase13_telemetry.py` ingest path) | **BLOCKED** |
| P13-REQ-011 | Record what machines searched for | OWNER | same, `actor_type` discriminator | WRITTEN | **BLOCKED** |
| P13-REQ-012 | A searched term resolves to the canonical Phase 6 `Query` — no second query vocabulary | MASTER §62, ADR-081 | `SearchDemandEvent.query_id`, no text column | structural test needed — **NOT WRITTEN** | **PARTIAL** |
| P13-REQ-013 | Zero-result searches distinguishable from unmeasured | ADR-081 | `result_count` nullable; `zero_results_only` filter uses `== 0` | **NOT WRITTEN** | **PARTIAL** |

## C. AI access control

| ID | Requirement | Origin | Implementation | Test | Status |
|---|---|---|---|---|---|
| P13-REQ-020 | Set access per agent to free / paid / forbidden | OWNER | `AccessPolicy`, `PUT /telemetry/access-policies` | `test_actor_type_rule_blocks_all_ai_crawlers`, `test_paid_tier_returns_402_with_terms_link` WRITTEN | **BLOCKED** |
| P13-REQ-021 | Block training crawlers while leaving question-answering open | OWNER | `AccessPurpose` axis | `test_purpose_rule_blocks_training_while_answering_stays_open` WRITTEN; PHP `test-access-gate.php` WRITTEN | **BLOCKED** |
| P13-REQ-022 | **Every** AI is listed — no allow-list, unknown agents included | OWNER | `ai_agent_service.resolve_or_discover` (no rejection path) | `test_an_unknown_agent_is_registered_not_dropped`, `test_even_a_gibberish_client_gets_a_row`, `test_agents_endpoint_has_no_known_only_filter` WRITTEN | **BLOCKED** |
| P13-REQ-023 | Cloudflare-style purpose-based control as the pattern | OWNER | `AccessPurpose` (training / search_indexing / answering / agent_action / preview / unknown) | precedence tests WRITTEN | **BLOCKED** |
| P13-REQ-024 | Precedence is predictable: most specific first, first match wins | ADR-077 | `access_policy_service.evaluate`, `AIOL_Access_Gate::evaluate` | `test_specific_agent_rule_beats_a_stricter_general_rule` + PHP twin WRITTEN | **BLOCKED** |
| P13-REQ-025 | An undecided agent reports as "not configured", never "allowed" | ADR-077 | `AccessTier.UNSET` → `AccessDecision.NOT_CONFIGURED` | `test_no_policy_is_not_configured_not_allowed`, `test_unset_tier_behaves_exactly_like_no_rule` WRITTEN | **BLOCKED** |
| P13-REQ-026 | Policy is published machine-readably | MASTER §42 | `robots_txt` filter + `/.well-known/ai-policy` | **NOT WRITTEN** | **PARTIAL** |
| P13-REQ-027 | Edge and Core evaluate the same rule identically | ADR-076/077 | generated signature table + parity tests | `test_python_and_php_signature_lists_are_identical`, `test-signature-parity.php` WRITTEN; **behavioural edge/Core parity test NOT WRITTEN** | **PARTIAL** |

## D. Operations surface

| ID | Requirement | Origin | Implementation | Test | Status |
|---|---|---|---|---|---|
| P13-REQ-030 | Green connection indicator for Cloud Core and plugin | OWNER | `GET /telemetry/health`, `view-dashboard.php` connection strip | **NOT WRITTEN** | **PARTIAL** |
| P13-REQ-031 | Overall status is the worst of its parts, never rounded up | ADR-039 / `AIOL_Status` | `telemetry_health` aggregation | existing `test-status.php` covers the plugin half; Core half **NOT WRITTEN** | **PARTIAL** |
| P13-REQ-032 | Logs captured | MASTER §103 | `AIOL_Logger` (reused, not duplicated) | existing | **PARTIAL** |
| P13-REQ-033 | Button to clear log history, without destroying the analytics record | OWNER | `view-dashboard.php` form + `AIOL_Telemetry::clear_buffer` | **NOT WRITTEN** | **PARTIAL** |
| P13-REQ-034 | Tool version displayed | OWNER | `AIOL_VERSION` 0.13.0, `CORE_VERSION`, `TELEMETRY_API_VERSION` — all three shown | **NOT WRITTEN** | **PARTIAL** |

## E. Inherited contract (checkpoint M.1)

| ID | Requirement | Origin | Implementation | Status |
|---|---|---|---|---|
| P13-REQ-040 | One design system; no second token set | CHECKPOINT UX-08 | plugin copy generated by `scripts/sync-design-system.php`; `test-design-system-parity.php` asserts byte-identity | **BLOCKED** (test not run) |
| P13-REQ-041 | One icon registry; no inline SVG, no emoji, no dashicons in new UI | CHECKPOINT M.1 §8, MASTER §90 | 7 icons added to `icon-paths.json` (67 → 74); dashboard uses `AIOL_Icon` only | **PARTIAL** — `check.js` 33/33 PASS (static); rendering BLOCKED |
| P13-REQ-042 | Status never carried by colour alone | MASTER §139 | every badge = icon + word + colour | **PARTIAL** — static only |
| P13-REQ-043 | "Not available" ≠ 0 throughout | CHECKPOINT §10 | `.not-available` / `.aiol-na` used for every nullable | **PARTIAL** — static only |
| P13-REQ-044 | Tenant isolation across all new routes | MASTER §113 | composite FKs on 4 new tables; `get_tenant_scoped_or_404` | 5 isolation tests WRITTEN | **BLOCKED** |
| P13-REQ-045 | No second source manager / job system / query normalizer | MASTER §149 | `SyncJob` untouched; `normalize_query` reused; no new file store | forensic audit **NOT RE-RUN** | **PARTIAL** |

---

## Traceability gaps, stated

Per §111, a missing link is a **TRACEABILITY GAP**, not an omission to be
quietly tolerated. The open ones:

1. **No requirement in this matrix has runtime evidence.** Every status is
   BLOCKED or PARTIAL for that reason, not for a design reason.
2. **P13-REQ-012, 013, 026, 030–034 have no test at all.** They are
   implemented and unverified, which is a weaker position than the ones
   marked BLOCKED, and the matrix says so rather than levelling them up.
3. **Mutation testing: 0 mutations run.** `MUTATION_PLAN.md` lists 11
   planned mutations; none has been executed.
4. **No E2E flow has been executed**, fixture or otherwise.
5. **Phase 0–12 regression has not been run** against this tree.
