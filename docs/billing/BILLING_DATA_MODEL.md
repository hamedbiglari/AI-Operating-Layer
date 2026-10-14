# Billing data model — schema reference

**Status: DESIGNED.** `Plan`, `Subscription`, `TrialClaim`, `Wallet` and
`LedgerEntry` exist as syntax-checked draft SQLAlchemy classes in
`cloud-core/app/models/_draft_billing_not_wired/billing.py`. The tables
below — `PlanVersion`, `Payment`, `PaymentEvent`, `Invoice`,
`WalletReservation`, `UsageRecord`, `AICostRecord`,
`ProviderPricingVersion`, `SubscriptionEvent` — are documented at column
level only, so a real implementation session can draft the classes
against reviewed columns rather than starting from nothing. None of this
has been migrated.

Every table follows the project's standing conventions: `UUIDPrimaryKeyMixin`
(`id UUID PK`), `TimestampMixin` (`created_at`, `updated_at`), and a
composite `(organization_id, id)` foreign key from any child row into its
tenant-scoped parent — never a bare `organization_id` copied without a
constraint tying it to the parent's own `organization_id`.

## PlanVersion

Effective-dated pricing/entitlement snapshot, so a historical invoice
stays explainable (owner's prompt §102).

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| plan_id | UUID FK -> billing_plans.id | |
| price_cents | INTEGER | minor units |
| currency | CHAR(3) | |
| billing_interval | ENUM(month, year) | |
| entitlements | JSONB | capability list this version grants |
| ai_budget_included_cents | INTEGER | 0 if none |
| effective_from | TIMESTAMPTZ | |
| effective_to | TIMESTAMPTZ NULL | NULL = still current |
| created_at | TIMESTAMPTZ | |

## SubscriptionEvent

Append-only history for `Subscription` (renewals, upgrades, cancellations
— owner's prompt §214, "This history must remain immutable").

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| organization_id | UUID FK | composite FK to subscriptions(org_id, id) |
| subscription_id | UUID | |
| event_type | ENUM(created, renewed, upgraded, downgraded, canceled, expired, reactivated) | |
| from_plan_version_id | UUID NULL | |
| to_plan_version_id | UUID NULL | |
| occurred_at | TIMESTAMPTZ | |
| actor | ENUM(user, admin, system, webhook) | who/what caused it |
| actor_id | UUID NULL | |

## Payment / PaymentEvent

`Payment` is the current-state row per attempted charge; `PaymentEvent`
is the append-only webhook/event trail feeding it (owner's prompt §71:
webhooks must be idempotent, replay-safe, auditable).

**Payment**

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| organization_id | UUID FK | |
| provider | ENUM | e.g. stripe |
| provider_payment_id | STRING | unique per provider |
| amount_cents | INTEGER | |
| currency | CHAR(3) | |
| status | ENUM(pending, succeeded, failed, refunded, partially_refunded) | |
| plan_version_id | UUID NULL | if this payment is a subscription charge |
| wallet_purchase_cents | INTEGER NULL | if this payment is a wallet top-up |
| created_at / updated_at | TIMESTAMPTZ | |

**PaymentEvent**

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| payment_id | UUID FK | |
| provider_event_id | STRING | **unique** — the actual idempotency key from the provider webhook |
| event_type | STRING | raw provider event type, kept for audit |
| received_at | TIMESTAMPTZ | |
| raw_payload_redacted | JSONB | secrets stripped before storage |

`UNIQUE(provider_event_id)` is the entire duplicate-webhook defense
(owner's prompt §71, §217) — a redelivered webhook fails the insert and
is a no-op, not a second `Payment` update.

## Invoice

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| organization_id | UUID FK | |
| payment_id | UUID FK NULL | |
| invoice_number | STRING | human-facing, sequential per org or global (business decision) |
| plan_version_id | UUID NULL | pins the pricing version this invoice used |
| gross_cents | INTEGER | |
| tax_cents | INTEGER NULL | NULL = not computed, never 0-by-default |
| platform_fee_cents | INTEGER NULL | |
| ai_budget_cents | INTEGER NULL | |
| currency | CHAR(3) | |
| status | ENUM(open, paid, void, uncollectible) | |
| issued_at | TIMESTAMPTZ | |
| pdf_path | STRING NULL | only populated once PDF generation is actually implemented |

## WalletReservation

The "hold" half of the reserve/settle/release cycle (`BILLING_ARCHITECTURE.md`
§4). A `LedgerEntry` records the *money movement*; `WalletReservation`
records the *hold's own lifecycle* so a stuck/expired reservation is
queryable directly instead of reconstructed from ledger rows.

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| organization_id | UUID FK | |
| wallet_id | UUID FK (composite w/ org) | |
| job_id | UUID NULL | the AI job this reservation backs |
| estimated_cents | INTEGER | |
| settled_cents | INTEGER NULL | filled at settlement |
| status | ENUM(held, settled, released, expired) | |
| event_key | STRING | idempotency key, unique per org |
| created_at | TIMESTAMPTZ | |
| settled_at | TIMESTAMPTZ NULL | |

## UsageRecord

Metered usage that is not itself an AI cost (storage, source-ingestion
counts — owner's prompt §223/§224: route future metered usage through
this one domain, don't invent a parallel billing mechanism per feature).

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| organization_id | UUID FK | |
| metric | ENUM(sources_ingested, storage_bytes, ...) | extend, don't branch |
| quantity | NUMERIC | |
| period_start / period_end | TIMESTAMPTZ | |
| recorded_at | TIMESTAMPTZ | |

## AICostRecord

One row per AI execution's cost accounting — the customer-facing half.
(The provider-side wholesale cost, where different from what the
customer is charged, is admin-only — see `ProviderPricingVersion`.)

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| organization_id | UUID FK | |
| job_id | UUID | |
| knowledge_object_id | UUID NULL | |
| provider | STRING | |
| model | STRING | |
| input_tokens / output_tokens | INTEGER | |
| estimated_cents | INTEGER | |
| actual_cents | INTEGER NULL | NULL until the provider/reconciliation reports it — never defaulted to the estimate |
| customer_charged_cents | INTEGER | may legitimately differ from actual_cents |
| wallet_reservation_id | UUID NULL | |
| created_at | TIMESTAMPTZ | |

## ProviderPricingVersion

Admin-only catalog (owner's prompt §87: "Never hardcode current AI
provider prices in business logic").

| Column | Type | Notes |
|---|---|---|
| id | UUID PK | |
| provider | STRING | |
| model | STRING | |
| input_price_per_1k_cents | NUMERIC | |
| output_price_per_1k_cents | NUMERIC | |
| currency | CHAR(3) | |
| effective_from | TIMESTAMPTZ | |
| effective_to | TIMESTAMPTZ NULL | |
| source | STRING | e.g. "provider published pricing page, checked 2026-09-18" |
| confidence | ENUM(verified, estimated) | |

If a provider's price for a given period is not known, no row exists for
that period — resolution code returns `UNKNOWN`, never `0`.
