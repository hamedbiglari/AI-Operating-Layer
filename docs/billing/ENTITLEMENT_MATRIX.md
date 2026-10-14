# Entitlement matrix — proposal

**Status: PROPOSAL, not a decision.** Which capabilities are Basic vs.
Pro is a business/pricing decision the owner has to make — this table is
a starting draft, not something engineering should treat as settled. It
exists so `EntitlementService` has something concrete to read while the
real values get decided; the whole point of `ENTITLEMENT_MATRIX` being
data (a table, versioned, admin-editable) rather than code is that this
file changing never requires touching a service or an API route.

| Capability | Basic | Pro Trial | Pro Monthly | Pro Annual | Admin |
|---|---|---|---|---|---|
| VIEW_KNOWLEDGE | ✓ | ✓ | ✓ | ✓ | ✓ |
| VIEW_HISTORY | ✓ | ✓ | ✓ | ✓ | ✓ |
| VIEW_AI_VISIBILITY | ✓ | ✓ | ✓ | ✓ | ✓ |
| VIEW_ANALYTICS_BASIC | ✓ | ✓ | ✓ | ✓ | ✓ |
| CREATE_KNOWLEDGE_OBJECT | ✗ | ✓ | ✓ | ✓ | ✓ |
| ADD_SOURCE | ✗ | ✓ | ✓ | ✓ | ✓ |
| REMOVE_SOURCE | ✗ | ✓ | ✓ | ✓ | ✓ |
| RUN_PROCESSING | ✗ | ✓ | ✓ | ✓ | ✓ |
| RUN_RESEARCH | ✗ | ✓ | ✓ | ✓ | ✓ |
| ADVANCED_VISIBILITY_REPORT | ✗ | ✓ | ✓ | ✓ | ✓ |
| AI_EXECUTION | ✗ | ✓ (from trial wallet grant) | ✓ | ✓ | ✓ |
| AI_BUDGET_CONTROL (allocation/limits) | ✗ | ✓ | ✓ | ✓ | ✓ |
| EXPORT | ✗ | ✓ | ✓ | ✓ | ✓ |
| PUBLICATION | ✗ | ✓ | ✓ | ✓ | ✓ |
| ANALYTICS_ADVANCED | ✗ | ✓ | ✓ | ✓ | ✓ |
| ADMIN_OPERATIONS | ✗ | ✗ | ✗ | ✗ | ✓ |

Read access to previously-generated Knowledge Objects (owner's prompt
§59/§93) is intentionally on the VIEW_* rows, not gated to Pro — this is
the "expiry changes access to operations, not ownership of what already
exists" principle from the owner's prompt §275, expressed as actual
matrix rows rather than a special-cased exception in code.

## Resolution order (`EntitlementService.check`)

```
1. Is the organization ADMIN-flagged?           -> Admin column
2. Does an ACTIVE TrialClaim exist and cover
   this capability?                             -> Pro Trial column
3. What is Subscription.status + Plan.tier?
     ACTIVE / TRIALING (paid) + PRO             -> Pro Monthly/Annual column
     anything else (BASIC, PAST_DUE past grace,
     EXPIRED, CANCELED, REVOKED)                -> Basic column
```

This mirrors `access_policy_service.py`'s documented first-match
semantics (owner's prompt §45: "Existing first-match semantics must
remain intact... do not silently introduce strictest-wins or combined
scoring") applied to commercial entitlement instead of AI access policy —
one deliberate, intentional reuse of a pattern already accepted in this
codebase, not a coincidence.

## What still needs an owner decision before this is implementable

* Grace-period length and whether PAST_DUE keeps Pro capabilities during
  it (owner's prompt §212 requires this be explicit; it isn't yet).
* Whether Pro Trial's AI wallet grant has its own cap, separate from a
  paid Pro wallet purchase.
* Whether ADMIN_OPERATIONS needs finer-grained sub-capabilities (viewer
  vs. support vs. super-admin) — owner's prompt §184 lists six admin
  role levels this single matrix does not yet distinguish.
