# AI Operating Layer — WordPress adapter

Thin WordPress adapter for the AI Operating Layer Cloud Core
(master spec §38). **Cloud Core is the source of truth.** This plugin
publishes references to Core objects and renders what Core asserts; it
holds no business truth of its own.

## What it does

| §38 responsibility | Implementation |
|---|---|
| Authentication | Installation token (`aiol_…`) → Core derives the tenant. `includes/class-aiol-credentials.php` |
| Connection to Cloud Core | `includes/class-aiol-client.php` — one place, eight stable error categories |
| Content sync | `save_post` / `transition_post_status` → `POST /adapter/mappings` |
| Product sync | `woocommerce_update_product` → identity projection only (ADR-041) |
| Schema rendering | JSON-LD from `GET /adapter/catalog/{id}`. `includes/class-aiol-schema.php` |
| WordPress hooks | `includes/class-aiol-hooks.php` |
| WooCommerce hooks | One hook, identity only — Phase 10 owns commerce (ADR-041) |
| Status reporting | Per-dependency, never one green light. `includes/class-aiol-status.php` |
| Cache | Asymmetric TTL: identity 1h, price/stock 60s. `includes/class-aiol-cache.php` |

## What it deliberately cannot do

No credential scope grants it, and Core refuses regardless:

- mark evidence or trust **verified**
- **publish** a product (Core owns `ProductStatus`)
- invent a price or stock value
- decide what to recommend
- read another tenant — the tenant is derived from the credential, and
  no request carries an `organization_id`

## Setup

1. In Cloud Core: **Installations → create** (bind it to a site) **→ issue
   credential** with `catalog:read`, `mappings:read`, `mappings:write`.
2. In WordPress: **AI Operating Layer**, paste the Core URL and token.
   The credential is verified immediately — a token that cannot
   authenticate does not produce a success message.
3. On any post/page/product, use the **AI Operating Layer** sidebar panel to
   paste the Core object ID.

The token is stored in `wp_options` with `autoload=false`, never logged
(`AIOL_Logger::redact`), never echoed, and masked in the UI.
**WordPress has no secret store** — a compromised install can read it.
Containment is Core-side: four narrow scopes, revocable and rotatable.

## Schema rendering safety

`class-aiol-schema.php` renders **only what Core asserts**:

- `postmeta` is never a source of product facts
- a missing price is **omitted**, never rendered as `0` (0 means free)
- untracked stock is never rendered as out-of-stock
- unverified or rejected claims never appear
- if Core is unreachable, **nothing is rendered** — absent markup is
  uninformative; wrong markup is a false public claim

## Tests

```bash
bash tests/run.sh        # 68 assertions + php -l across all files
```

Covers the pure logic: JSON-LD mapping, status aggregation, credential
validation, secret redaction, error categorisation and retry-safety.

**Not covered** (`ENVIRONMENT BLOCKED`): anything needing a live WordPress —
hooks, nonces, capabilities, admin rendering — and anything needing a
browser. See `tests/visual/README.md` for the reproducible visual procedure
and the exact list of unverified properties.
