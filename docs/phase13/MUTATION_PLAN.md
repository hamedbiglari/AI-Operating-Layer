# Phase 13 — Mutation plan

**STATUS: 0 of 11 mutations executed.** No mutation result may be cited
from this document. It exists so that the mutations are decided *before*
the tests are run, rather than chosen afterwards to match whatever the
suite happens to catch.

Rules carried from Phase 12 (§26): do not weaken a test to hide a mutant,
do not exclude critical logic without written justification, and a
surviving critical mutation prevents PASS.

| # | File | Mutation | Test that MUST fail | Why this one |
|---|---|---|---|---|
| M1 | `telemetry_service.ingest_batch` | delete the `existing_keys` duplicate check | `test_redelivered_batch_does_not_double_count` | without it one retry silently inflates every dashboard number, undetectably |
| M2 | `telemetry_service.truncate_ip` | return `raw` instead of `None` on parse failure | `test_truncate_ip[not-an-ip]` | a fallback that returns the input turns a parse failure into an untruncated address |
| M3 | `telemetry_service.enforce_retention` | change `<=` to `<` on the horizon | `test_retention_nulls_the_address_and_keeps_the_prefix` | an off-by-one on a deletion horizon is the difference between a 30-day window and permanent retention |
| M4 | `telemetry_service.enforce_retention` | also null `ip_truncated` | same test | destroys the analytics the truncated form exists to preserve |
| M5 | `telemetry_service.rollup_day` | count `dwell_ms IS NULL` rows as 0ms samples | `test_reported_dwell_is_preserved_and_averaged_over_real_samples` | drags every average toward zero and is invisible in the output |
| M6 | `telemetry_service.rollup_day` | compute `total_views` independently of its components | `test_total_views_equals_the_sum_of_its_parts` | lets the denormalised sort column drift from the numbers beside it |
| M7 | `access_policy_service.evaluate` | reverse the candidate order (least specific first) | `test_specific_agent_rule_beats_a_stricter_general_rule` | "block all crawlers except this one" stops working |
| M8 | `access_policy_service.evaluate` | map `AccessTier.UNSET` to `ALLOWED` | `test_unset_tier_behaves_exactly_like_no_rule` | reports a decision nobody made as a permission |
| M9 | `access_policy_service.evaluate` | drop the `ActorType.HUMAN` early return | `test_humans_are_never_subject_to_an_access_policy` | a misconfiguration could 403 a paying customer's browser |
| M10 | `ai_agent_service.resolve_or_discover` | return `None` when no signature matches | `test_an_unknown_agent_is_registered_not_dropped` | turns the registry into an allow-list — the exact thing the requirement forbids |
| M11 | `telemetry.py` route | remove the `organization_id` filter from `list_page_views` | `test_one_tenant_cannot_see_another_tenants_traffic` | cross-tenant leak of traffic data that now contains IP addresses |

## Not mutated, with reasons

* **`AIOL_Geo` header parsing** — PHP, and no PHP mutation harness exists
  in this project. Covered by unit assertions instead, and recorded here
  as a gap rather than silently skipped.
* **`aiol-dwell.js`** — browser-only; no JS test runner is configured.
  Listed as a gap.
