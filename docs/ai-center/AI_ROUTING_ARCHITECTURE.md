# AI Routing Architecture (ADR-088, REQ-AIC-003)

## Six modes

| Mode | Value | Behaviour |
|---|---|---|
| Manual single | `manual_single` | One fixed account+model; never falls back automatically. |
| Manual ordered chain | `manual_chain` | User-ordered steps; next step is used when the current one stops (quota, rate limit, auth failure, timeout, manual switch). |
| Stage-based manual | `stage_manual` | Each pipeline stage is mapped to a specific account+model. |
| Automatic pool | `auto_pool` | System chooses from enabled accounts ranked by health, failure count, estimated cost, then stable ID. |
| Automatic priority pool | `auto_priority` | Same as pool but the user's ordered steps set the priority. |
| Hybrid smart | `hybrid` | Stage rule wins if it matches, otherwise falls back to priority-pool logic. |

## Decision model
`AIRoutingDecision` stores every choice made (trigger, mode, chosen account, model, stop reason,
explanation). Each explanation entry records a `verdict` and a `reason` for every candidate,
so the decision is fully auditable:
- `chosen` — selected for use
- `disabled` — account disabled
- `no_credential` — no encrypted credential stored
- `unhealthy` — health status in (RATE_LIMITED, QUOTA_EXHAUSTED, AUTH_FAILED, UNAVAILABLE, TIMEOUT)
- `quota` — remaining_tokens ≤ 0 or remaining_requests ≤ 0
- `spend_limit` — estimated cost exceeds account spend limit
- `no_adapter` — no invocation adapter registered for this provider
- `capability` — required_capability not in account's model capabilities
- `stage` — step's stage does not match the requested stage

## Cost gate (REQ-AIC-012)
Before each item execution a worst-case token cost is estimated and compared against the job's
`max_cost_per_job`. The job stops with `cost_limit_reached` if the remaining budget is exceeded.

## Policies and steps
`ai_routing_policies` (name, mode, max_cost_per_job) with ordered `ai_routing_steps`
(position, account, model, optional stage, optional required_capability).

## Explainability endpoint
`GET /ai-center/routing-policies/{id}/preview` returns the current decision without executing
anything: which account was chosen, why every other was skipped, and the stop reason when
nothing is usable.
