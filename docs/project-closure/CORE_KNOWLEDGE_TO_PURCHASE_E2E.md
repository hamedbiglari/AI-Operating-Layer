# Core Knowledge → Product → Purchase — End-to-End Evidence

**Test ID:** E2E-K2C-001 · **Date:** 2026-09-24 · **Tenant:** "Toranjebin Merchant" (`85f86782-a013-48c6-82c3-947e36e76727`)

## Environment (all real processes, no fixtures)
Cloud Core (uvicorn + Celery worker) on PostgreSQL 16 DB `aiol_e2e` migrated 0001→0018; Redis 7;
**WordPress 6.6.2 + WooCommerce 9.3.3 + the AIOL plugin 0.13.0** on MariaDB, served by `wp server`
(WordPress and WooCommerce obtained from their GitHub releases; PHP 8.3 from the Ubuntu archive).
No AI model is called anywhere in this loop (recommendation is policy-based by design), so
the missing AI-provider credential does not affect it.

## Stages
| # | Stage | What happened (real API / real DB) | IDs | Status |
|---|---|---|---|---|
| 1 | Query | `POST /queries/import` "where to buy authentic toranjebin online" | query `d662bfc1-…` | VERIFIED |
| 2 | Intent | `POST /queries/{id}/intents` transactional, linked to entity | — | VERIFIED |
| 3 | Knowledge | KO "Toranjebin (Persian manna)", entity "Toranjebin" | KO `9054d6fb-…`, entity `06d675e5-…` | VERIFIED |
| 4 | Evidence | source (lab certificate) → evidence (direct, moderate) → review pending→**verified**; claim "contains mannitol" → pending→**approved**; claim↔evidence "supports" | evidence `b977119b-…`, claim `d67ce48c-…` | VERIFIED |
| 5 | Trust | trust record (testing) → verify **refused** while evidence was draft ("Verify the Evidence first") → verified after evidence verification | trust `3ba0706c-…` | VERIFIED (no silent promotion) |
| 6 | Product | product "Toranjebin Grade A — 100 g" linked to KO; product-evidence verified; status draft→in_review→**published** | product `c164612f-…` | VERIFIED |
| 7 | Adapter auth | plugin `AIOL_Credentials::save` + `GET /adapter/identity` → tenant derived from token, 6 scopes | installation `bc25fcea-…` | VERIFIED |
| 8 | Merchant product | real WooCommerce product #11 (SKU TRJ-A-100, 12.50 USD, stock 40) | Woo #11 | VERIFIED |
| 9 | Content mapping | `save_post` hook → plugin → `POST /adapter/mappings` with permalink | mapping state `synced` | VERIFIED |
| 10 | Offer (commerce sync) | commerce mapping via plugin client; price change to 12.90 → `woocommerce_update_product` → plugin → `POST /adapter/commerce/mappings/{id}/offer` → Core offer 12.90 USD in_stock, stock 40, `external_id woo:11` | offer `0dce8379-…` | VERIFIED |
| 11 | Recommendation | `POST /recommendations` (recommend mode, query + KO) → **recommended**, score 0.762, 0 rejected | 1 recommendation row | VERIFIED |
| 12 | AI-facing answer | separate AI-agent installation (`ai:query`) → `POST /ai/ask` purchase_intent=ready → answerable, rank 1, evidence/trust "partial", **merchant_url** = permalink | — | VERIFIED (after correction C-P11-01) |
| 13 | Merchant URL → page | `GET http://127.0.0.1:8081/?product=toranjebin-grade-a-100-g` → 200, title and price 12.90 present; JSON-LD Offer 12.90 USD InStock | — | VERIFIED (that the Offer block is the plugin's rather than WooCommerce's: SIGNAL — no sku/@id, matching the plugin's Core-only rendering) |
| 14 | Cart | Store API `cart/add-item` ×2 → 201, cart total 25.80 USD | — | VERIFIED |
| 15 | Purchase intent | Store API `checkout` (payment method *cheque* — no money moves) → **order #13, status on-hold, total 25.80 USD** | Woo order #13 | VERIFIED (order placed; payment NOT executed — by design) |
| 16 | Purchase (paid) | real payment gateway | — | NOT_APPLICABLE (master §58: no payment processor in MVP; payment happens on the merchant site) |
| 17 | Tenant isolation | tenant B user and B machine credential → A's product, offers, KO, evidence, trust, query, catalog, AI knowledge, AI trust: all **404**; B lists empty; B `/ai/ask` leaks nothing | — | VERIFIED |

DB rows after the run: recommendations 1, offers 1, wordpress_mappings 1, commerce_mappings 1,
ai_executions 0 (no model invoked — correct).

## Defect found by this E2E and corrected
**C-P11-01 (owner: Phase 11 AI interface; requirement: MASTER §1 "routing users to the original
merchant website", §35 commerce flow).** `/ai/ask` returned products without any purchase
destination, so an AI agent could not send a buyer to the merchant. Added `merchant_url`, taken
only from merchant-asserted data (offer URL, else the adapter-published permalink), tenant-scoped,
http(s) only, NULL when absent. 4 tests added (offer URL, permalink fallback, never guessed,
never cross-tenant).

## Limitations
Single product, single tenant pair, localhost; no real payment; one sample query. Not a pilot
at master §55 volumes and not production.

## Regression run — final existing-owner closure pass (2026-09-24)
Fresh Cloud Core DB, same real WordPress 6.6.2 + WooCommerce 9.3.3. New WooCommerce product #14.
All stages re-passed; additionally **stock change 40 → 7 synced** (Core offer `stock_quantity 7`,
`external_id woo:14`). Recommendation `recommended` (0.762); `/ai/ask` `merchant_url`
`…/?product=toranjebin-grade-a-100-g-2`; product page 200 with JSON-LD Offer 12.90 USD; cart 2 × =
25.80 USD; **order #15 on-hold** (cheque, unpaid). Tenant isolation: 9/9 direct attempts 404, lists
empty, no AI-answer leak. A defect found in the regression was in the test script (mapping id is
nested under `mapping`), fixed in `e2e/e2e_wp.sh`; no product defect.
