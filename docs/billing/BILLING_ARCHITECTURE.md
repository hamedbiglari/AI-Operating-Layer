# Billing / Entitlement / AI-Wallet — Architecture

**Status: DESIGNED, NOT IMPLEMENTED.** Nothing in this document has been
run against a database, a payment provider, or a browser. It is written
so a real implementation session — with an actual Postgres instance,
Alembic, a payment provider sandbox, and the rest of this project's real
dependency set — has a concrete, reviewed starting point instead of a
blank page. Written in response to the owner's "FINAL MASTER EXECUTION
PROMPT" (Phase 13 dashboard/billing follow-up), scoped down to what a
design document can responsibly claim: no code in this document has been
executed, and none of it should be read as verified.

This document assumes the reader has `docs/DECISIONS.md`,
`docs/MASTER_SPEC.md` and `cloud-core/app/models/page_view.py` open — it
follows their conventions rather than restating them.

## 1. Where this sits in the existing architecture

The owner's prompt asks for a layered pipeline:

```
Provider Adapters -> Domain Services -> Application Services ->
Dashboard Query Layer -> API / BFF -> Web Dashboard
```

This project already has half of that pipeline for analytics
(`app/services/telemetry_service.py`, `app/services/access_policy_service.py`
consumed by `app/api/v1/telemetry.py`). Billing adds three new domain
services and one new cross-cutting service, following the exact same
shape — a service module per aggregate, an API router that calls the
service and never touches the ORM directly, no vendor SDK object crossing
the service boundary:

```
app/services/
    plan_service.py            # catalog read, plan/version resolution
    subscription_service.py    # subscription lifecycle, trial claim
    wallet_service.py          # reserve / settle / release, ledger writes
    entitlement_service.py     # THE gate — see §3

app/services/integrations/
    payment/
        port.py                # PaymentProvider interface
        stripe_adapter.py       # (or whichever provider is chosen)
```

`PaymentProvider` is a port in the same sense `AnalyticsProvider` would
be for GA4 — the domain services never see a Stripe (or any vendor)
response object; the adapter normalizes it into the project's own
`PaymentEvent`/`Invoice` shapes first. This is not a new pattern for the
project — it's the same normalization discipline ADR-075/ADR-081 already
apply to search data (`normalize_query`) applied to money instead.

## 2. Three separate aggregates, not one "billing record"

See ADR-082. `Subscription`, `Wallet` and `Entitlement` are modelled and
queried independently:

| Aggregate | Answers | Persisted? |
|---|---|---|
| `Subscription` | What plan, what status, until when? | Yes — current-state row |
| `Wallet` + `LedgerEntry` | How much AI budget is available? | Yes — cache + append-only ledger |
| `Entitlement` | Can this org do *this* right now? | **No** — resolved per-request |

`Entitlement` is deliberately not a table of booleans. A resolved
entitlement is `EntitlementService.check(org, capability)` reading:

1. the org's current `Subscription.status` + `Plan.tier`,
2. any `TrialClaim` with `status = ACTIVE` and `end_at > now()`,
3. the `ENTITLEMENT_MATRIX.md` capability table (versioned, admin-edited
   data — never an `if plan == "pro"` scattered across call sites).

## 3. Entitlement enforcement — server-side only, one call site pattern

Every Pro-gated mutation endpoint follows the same shape (owner's prompt
§60, §116):

```
authenticate
  -> authorize (tenant, role)
  -> EntitlementService.require(org, CAPABILITY)   # raises 402/403-style
     domain error if denied — never a bare 500, never a silent no-op
  -> resolve quota
  -> resolve/reserve AI budget if the operation spends one
  -> validate request body
  -> execute
  -> audit
```

`EntitlementService.require(...)` is the ONLY thing that may deny a
mutation for plan reasons. Frontend-disabled buttons are a UX courtesy,
not the control — the same "frontend hiding is not authorization"
principle `access_policy_service.py`'s docstring already states for AI
access policy, applied here to commercial plan gates.

## 4. Wallet: reserve -> settle -> release (ADR-086)

Before any AI-provider call that spends wallet budget:

```
1. estimate_cost(operation)                     -> estimated_cents
2. wallet_service.reserve(wallet_id, estimated_cents, event_key)
   -- atomic: UPDATE ... WHERE available_cents >= :amount
   -- (a conditional UPDATE, not read-then-write, closes the race
   --  the owner's prompt names at §83/§235)
   -- writes a LedgerEntry(type=RESERVATION, amount=-estimated_cents)
3. run the AI job
4. wallet_service.settle(reservation_id, actual_cents)
   -- writes LedgerEntry(type=AI_USAGE_CHARGE, amount=-actual_cents)
   -- writes LedgerEntry(type=RELEASE, amount=+(estimated - actual))
      when actual < estimated
5. if the job fails before any provider usage: release the full
   reservation (LedgerEntry(type=RELEASE, amount=+estimated_cents))
```

If step 1's estimate exceeds `wallet.available_cents`, the provider is
never called (owner's prompt §82: "If insufficient budget: do not call
provider"). The user sees "Insufficient AI budget", not a failed
provider call.

## 5. What is genuinely out of scope for a design document

This document does not — and a design document should not — settle:

* which payment provider (Stripe vs. a regional processor the owner may
  need for Iran-market payment rails is a real, non-trivial decision that
  needs the owner's input, not an assumption);
* actual tax/VAT logic (owner's prompt §113 explicitly requires
  jurisdiction-specific legal review before this is implemented, not
  invented here);
* the actual entitlement matrix values (drafted in
  `ENTITLEMENT_MATRIX.md` as a starting proposal, but "what Basic
  includes" is a business decision, not an engineering one).

## 6. Files this follow-up produced

```
docs/billing/BILLING_ARCHITECTURE.md      (this file)
docs/billing/BILLING_DATA_MODEL.md        schema-level column tables
docs/billing/ENTITLEMENT_MATRIX.md        capability x plan proposal
docs/billing/BILLING_API.md               endpoint contracts
docs/DECISIONS.md                          ADR-082 .. ADR-086 appended
cloud-core/app/models/_draft_billing_not_wired/billing.py
    draft SQLAlchemy models: Plan, Subscription, TrialClaim, Wallet,
    LedgerEntry (syntax-checked, not migrated, not wired)
```
