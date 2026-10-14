# AI Access Toolkit — capability map and absorption record

**FACT.** The legacy plugin was inspected in full: 25 files, 2,069 lines of
PHP, 13 classes. Nothing below is inferred from its README; every row was
read from source.

Legacy structure:

```
ai-access-toolkit.php
includes/Admin/          class-aat-admin.php, views/dashboard.php, views/settings.php
includes/Core/           class-aat-helpers.php
includes/Frontend/       class-aat-endpoints.php
includes/Modules/Gateway/      class-aat-gateway.php            (274 lines)
includes/Modules/Monitoring/   class-aat-bot-monitor.php        (204 lines)
includes/Modules/Optimization/ class-aat-llms-txt.php, class-aat-markdown.php,
                               class-aat-structured-data.php
includes/Modules/Readiness/    class-aat-score-calculator.php + 7 checks
languages/               .pot, fa_IR.po, fa_IR.mo
uninstall.php
```

## Classification

| # | Legacy capability | Class | Where it now lives | Reasoning |
|---|---|---|---|---|
| 1 | AI readiness diagnostics | **REFACTOR** | `includes/class-aiol-diagnostics.php` | Genuinely useful, cheap, deterministic, local. Rebuilt with PASS/WARNING/FAIL/**UNKNOWN** — the legacy version had no UNKNOWN and silently scored an unreachable check as failure. |
| 2 | HTTPS check | **REFACTOR** | `AIOL_Diagnostics::check_https()` | Same check, now also used to enforce the credential HTTPS policy (ADR-045). |
| 3 | robots.txt check | **REFACTOR** | `AIOL_Diagnostics::check_robots()` | Unreachable robots.txt now returns UNKNOWN, not FAIL. |
| 4 | XML sitemap check | **REFACTOR** | `AIOL_Diagnostics::check_sitemap()` | Detects core sitemaps and common plugins. |
| 5 | llms.txt generation | **REFACTOR** | `includes/class-aiol-representations.php` | Kept as a *representation*. Never Business Truth; carries an explicit header saying so. Invalidation widened (see #22). |
| 6 | Markdown representation | **REFACTOR** | `AIOL_Representations::markdown()` | Published-only enforced at generation, not just at routing — the legacy version relied on the route. |
| 7 | Schema.org / JSON-LD | **REPLACE** | `includes/class-aiol-schema.php` (Phase 9) | **The legacy implementation is the reason this is REPLACE not REFACTOR.** It assembled product schema from WordPress data. Core is now the only source for commercial facts; a negative test asserts no `AAT_Structured_Data` survives. |
| 8 | canonical URL check | **REFACTOR** | `AIOL_Diagnostics::check_canonical()` | |
| 9 | meta description check | **REFACTOR** | `AIOL_Diagnostics::check_meta_description()` | |
| 10 | AI Gateway (REST API) | **REPLACE** | Cloud Core `/api/v1/**` | §9 of the binding rules: WordPress must not be a second canonical API. The legacy gateway had its own auth, its own rate limit and its own content contract — three canonical-API responsibilities. Its *transport* role survives as the read-only representation endpoints (#5, #6), which serve WordPress's own content and claim no authority. |
| 11 | API key generation | **DEPRECATE** | — | `wp_generate_password(40)` stored in `wp_options`, verified by string compare, with no installation identity, no tenant, no scope, no rotation, no revocation. Superseded by machine identity (ADR-036). Negative test asserts no key-generation path remains. |
| 12 | API authentication | **REPLACE** | `AIOL_Credentials` + Core | `credential → installation → organization`. Tenant is never accepted from a request. |
| 13 | Rate limiting | **REPLACE** | Cloud Core (ADR-039) | Legacy limited per-IP in WP transients — ineffective behind shared hosting and unenforceable across sites. Core limits per *installation*. |
| 14 | AI bot monitoring | **REFACTOR** | `includes/class-aiol-actors.php` | Rebuilt on a real actor model (ADR-046). The legacy 18-entry User-Agent map is retained as *signal*, not identity. |
| 15 | Bot visit logging | **REFACTOR** | `AIOL_Actors::log()` | **Privacy narrowed:** no IP address, no full URL, no query string, UA truncated to 120 chars. Legacy stored IP + full request URI. Cap lowered 300 → 200. |
| 16 | Admin dashboard | **REFACTOR** | `admin/view-diagnostics.php` | Folded into the existing Phase 9 admin page rather than a second dashboard. |
| 17 | Settings | **REFACTOR** | existing settings screen + `aiol_settings` | Legacy per-feature toggles retained for representations/actor logging. |
| 18 | i18n | **REUSE (strategy) / REPLACE (catalogue)** | `languages/ai-operating-layer.pot`, `fa_IR.po` | Same gettext approach; strings are new, so the catalogue is regenerated rather than copied. |
| 19 | Uninstall behaviour | **REUSE (pattern)** | `uninstall.php` | Extended to the new option/transient set. Legacy `aat_*` options are also removed, so upgrading from the old plugin leaves nothing behind. |
| 20 | Frontend endpoints | **REFACTOR** | `AIOL_Representations` rewrite rules | `/llms.txt` and `?aiol_format=md` retained. |
| 21 | Caching | **REFACTOR** | `AIOL_Cache` (asymmetric TTL, Phase 9) | Legacy used one flat TTL for everything. |
| 22 | Content-change invalidation | **REFACTOR** | `AIOL_Representations::register()` | **Widened.** Legacy hooked `save_post`, `deleted_post`, `trashed_post` only. Now also `untrashed_post`, `transition_post_status` and `aiol_mapping_changed`, so unpublishing or remapping invalidates too. |
| 23 | AI Readiness **score** | **REPLACE** | `AIOL_Diagnostics::dimensions()` | See ADR-047. The single 0–100 number is gone; decomposed dimensions, explicitly labelled INTERNAL DIAGNOSTIC. |

## Summary

| Class | Count |
|---|---|
| REUSE | 2 |
| REFACTOR | 13 |
| REPLACE | 6 |
| DEPRECATE | 1 |
| DEFER | 1 (Agent Actionability / AI Visibility dimensions → Phase 12) |

**Nothing was blind-copied.** No `AAT_*` class survives; a negative test
(`test-absorption.php`) asserts that, so a future reviewer does not have to
take this document's word for it.
