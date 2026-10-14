# Existing Backlog After Closure (final existing-owner closure pass)

## Required for original project completion (existing owners)
| Item | Owner | Blocker |
|---|---|---|
| Real AI provider run (success, failure, retry, fallback) | 12 / 17 | external: `ANTHROPIC_API_KEY` (+ `AI_MODEL_PRICING_JSON`) |
| Code-login email delivery to real mailboxes | 1 / 13 | external: an SMTP provider (implementation done and verified against a local SMTP server) |
| Google sign-in | 1 / 13 | external: Google OAuth client credentials |
| Remaining dashboard screens (Analytics, Access, Research, Traffic, Operations, Inbox, admin screens) still sample-only | 14 | implementation (priority screens are done) |
| Pilot at MASTER §55 size | 15 | owner input: real knowledge domain, products and evidence |

## Optional backlog
Real research provider (P5); keyset pagination; explicit Claude visibility platform value; request_id
propagation into workers; plugin admin screens browser check; D-01, D-02, D-09, D-10.

## Future product expansion / not established
Billing, wallet, trial (ADRs only PROPOSED); support tickets; platform super-admin (MASTER §58);
signed cart intent (MASTER §36).
