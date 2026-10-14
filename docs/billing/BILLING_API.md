# Billing / entitlement API — contracts (draft)

**Status: DESIGNED.** No route below exists in `app/api/v1/`. Shapes
follow the conventions already visible in `app/api/v1/telemetry.py`
(paginated list envelope, `Not available` rather than `null`-as-zero) —
they are not copy-pasted from that file, but they are meant to feel like
the same API, not a bolted-on second style.

## GET /api/v1/me/entitlements

```json
{
  "organization_id": "…",
  "plan_tier": "basic",
  "capabilities": {
    "CREATE_KNOWLEDGE_OBJECT": { "allowed": false, "reason": "Requires Pro" },
    "AI_EXECUTION": { "allowed": false, "reason": "Requires Pro" },
    "VIEW_KNOWLEDGE": { "allowed": true, "reason": null }
  },
  "trial": { "status": "eligible" }
}
```

`reason` is always present when `allowed` is `false` — this is
`EntitlementService.explainRestriction()` from the owner's prompt §61,
surfaced directly rather than the frontend inferring a reason from a
plan name.

## GET /api/v1/me/subscription

```json
{
  "plan": { "slug": "pro-monthly", "display_name": "Pro Monthly" },
  "status": "active",
  "current_period_start": "2026-09-01T00:00:00Z",
  "current_period_end": "2026-10-01T00:00:00Z",
  "cancel_at_period_end": false
}
```

If no subscription row exists yet (a brand-new organization), this
returns the implicit Basic state — a `200` with `"plan": {"slug": "basic", ...}`,
not a `404`. Basic is a real plan row, not "the absence of a plan".

## GET /api/v1/me/wallet

```json
{
  "currency": "USD",
  "available_cents": 4270,
  "reserved_cents": 350,
  "consumed_cents": 1730,
  "balance_recomputed_at": "2026-09-18T07:40:00Z"
}
```

## POST /api/v1/billing/trial/claim

Request: `{}` (organization/user resolved from auth context — never
accepted from the request body, per §111 "the client must never be
trusted to declare... entitlement").

Success `200`:

```json
{ "trial": { "status": "active", "start_at": "…", "end_at": "…" } }
```

Error `409 ALREADY_CLAIMED`:

```json
{ "error": "ALREADY_CLAIMED", "message": "This organization already used its trial." }
```

Backed entirely by `uq_billing_trial_claims_organization` — the 409 is
what a unique-constraint violation surfaces as, not a separate
"has-claimed-before" check that could drift from the constraint.

## POST /api/v1/knowledge/{id}/sources (existing route, entitlement-gated)

Unchanged request/response shape. New failure mode when the caller lacks
`ADD_SOURCE`:

`402 ENTITLEMENT_REQUIRED` (owner's prompt §117 asks for a typed
response, not a 500 or a fake-success queued state):

```json
{
  "error": "ENTITLEMENT_REQUIRED",
  "capability": "ADD_SOURCE",
  "message": "Adding sources requires Pro.",
  "upgrade_url": "/billing/plans"
}
```

## POST /api/v1/ai/jobs (illustrative — the actual route/shape belongs to
whatever job-creation endpoint already exists for processing)

Before this returns `202 Accepted`, the handler must have already:

1. resolved `EntitlementService.require(org, AI_EXECUTION)`,
2. called `wallet_service.reserve(...)`,
3. persisted the job row.

Insufficient-budget failure, `402 INSUFFICIENT_AI_BUDGET`:

```json
{
  "error": "INSUFFICIENT_AI_BUDGET",
  "estimated_cents": 1200,
  "available_cents": 350,
  "message": "Insufficient AI budget for this operation."
}
```

## Error code registry (extends the project's existing set)

| Code | HTTP | Meaning |
|---|---|---|
| ENTITLEMENT_REQUIRED | 402 | Capability not covered by current plan/trial |
| INSUFFICIENT_AI_BUDGET | 402 | Wallet cannot cover the estimated cost |
| ALREADY_CLAIMED | 409 | Trial already used for this organization |
| SUBSCRIPTION_NOT_FOUND | — | never returned; Basic is always a real row (see above) |

Every one of these carries a human-readable `message` alongside the
machine `error` code, per owner's prompt §242 — "This action requires a
Pro plan," not the bare enum value, in the surface a merchant reads.
