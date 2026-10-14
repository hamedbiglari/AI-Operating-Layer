# Existing Requirement Closure Matrix

Class: A user-approved · B architectural · C phase · D backlog · E optional · F AI suggestion.
Verification columns: ✓ verified this project, – not applicable, ✗ not done.

| ID | Requirement | Exact source | User approved? | Owning phase | Current status | Code | DB | API | Worker | Frontend | Runtime | E2E | Security | Evidence | Action |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| E-01 | Knowledge objects: create/read/list/update/version | MASTER §54, P2 | A | 2 | COMPLETE | ✓ | ✓ | ✓ | – | fixture UI | ✓ | ✓ (E2E-K2C) | ✓ tenant | P15/P16 runs, E2E | none |
| E-02 | Sources, documents, normalization (MarkItDown), chunks | MASTER P3, ADR-065/066 | A | 3 | PARTIAL | ✓ | ✓ | ✓ | ✓ | fixture UI | ✓ (job, retry) | URL fetch blocked by sandbox egress | SSRF guard reached | P14/P15 | none possible here |
| E-03 | Claims, evidence, claim↔evidence; no silent promotion | MASTER P4, §63 | A | 4 | COMPLETE | ✓ | ✓ | ✓ | – | – | ✓ | ✓ (trust refused until evidence verified) | ✓ | E2E stage 4–5 | none |
| E-04 | Direct ≠ indirect; traditional ≠ scientific ≠ clinical | MASTER §63 | B | 4 | COMPLETE (schema + tests) | ✓ | ✓ | ✓ | – | – | ✗ | ✗ | – | enums EvidenceDirectness; tests | none |
| E-05 | Research engine; knowledge ≠ research | MASTER P5 | A | 5 | PARTIAL | ✓ | ✓ | ✓ | ✓ | – | – | – | – | NotConfigured provider (honest) | real provider = D |
| E-06 | Query / intent | MASTER P6 | A | 6 | COMPLETE | ✓ | ✓ | ✓ | – | – | ✓ | ✓ | ✓ | E2E 1–2 | none |
| E-07 | Product ≠ offer; product evidence; trust | MASTER P7, §26–29 | A | 7 | COMPLETE | ✓ | ✓ | ✓ | – | fixture UI | ✓ | ✓ | ✓ | E2E 5–6, 10 | none |
| E-08 | Evidence-aware recommendation with abstention, modes | MASTER P8, §34 | A | 8 | COMPLETE | ✓ | ✓ | ✓ | – | – | ✓ | ✓ | ✓ | E2E 11 | none |
| E-09 | WordPress thin adapter (auth, mapping, schema, status) | MASTER P9, §38 | A | 9 | COMPLETE (runtime) | ✓ | – | ✓ | – | WP admin not browser-tested | ✓ real WP | ✓ | plugin security 33/33 | E2E 7, 9, 13 | admin screens browser check = D |
| E-10 | WooCommerce adapter / offer sync | MASTER P10, §40 | A | 10 | COMPLETE (runtime) | ✓ | ✓ | ✓ | – | – | ✓ real Woo | ✓ | ✓ | E2E 8, 10, 14–15 | none |
| E-11 | AI/REST interfaces incl. routing to merchant website | MASTER P11, §1, §35 | A | 11 | COMPLETE (after C-P11-01) | ✓ | – | ✓ | – | – | ✓ | ✓ | ✓ tenant | E2E 12 | none |
| E-12 | AI visibility (mention≠citation≠…≠purchase) | MASTER P12, §31 | A | 12 | PARTIAL | ✓ | ✓ | ✓ | ✓ | – | no-credential path ✓ | ✗ | ✓ | P17 | BLOCKED_EXTERNAL_DEPENDENCY (credential) |
| E-13 | Rights layer / access policy | MASTER P13, §37 | A | 13 | PARTIAL | ✓ | ✓ | ✓ | – | – | – | – | 1 failing test (D-05) | tests | fix D-05 (Phase 13) |
| E-14 | Analytics, demand, telemetry, IP per ADR-079 | P13 REQ, ADR-079 | A | 13 | PARTIAL | ✓ | ✓ | ✓ | – | fixture UI | – | – | D-03/04/06/07 | tests | fix D-03..07 (Phase 13) |
| E-15 | Email 6-digit code login (5-min resend; 3 fails → 1 h lock; 3 more → 24 h) + Google | owner's explicit instructions recorded in P13 addendum 9 | A | 13 (dashboard) / 1 (auth) | UI_ONLY | ✗ | ✗ | ✗ (password login only) | – | harness state machine | ✗ | ✗ | – | route scan | implement in owning phase; email delivery + Google OAuth need external credentials |
| E-16 | Billing: plans, subscriptions, trial, wallet, ledger, entitlements; payment NOT_CONNECTED | owner's prompt (§61, §71, §82, §102, §113, §117, §184, §214, §223) via P13 billing follow-up | A | 13 (billing follow-up) | DESIGNED_ONLY | draft classes, not wired | ✗ | ✗ | ✗ | fixture UI | ✗ | ✗ | – | docs/billing/* | implement in owning phase (payment gateway itself not required: MASTER §58) |
| E-17 | Dashboard wired to backend (operational control plane) | MASTER P14; P14 §12–13, §65 | A | 14 | PARTIAL | ✓ AI-executions screen | – | ✓ | – | 1 live screen, rest fixture | ✓ (1 screen) | ✓ (1 screen) | ✓ | P17 browser run | wire remaining screens (Phase 14) |
| E-18 | Admin dashboard | P13 addendum 9 ("Admin console added"), P14 §42–43; MASTER §58 + api.md: no cross-tenant super-admin in MVP | A (UI) | 13/14 | UI_ONLY for platform admin; tenant admin (users) COMPLETE | tenant ✓ | ✓ | users API | – | fixture UI | – | – | ✓ | api.md line 39 | platform admin: SUPERSEDED for MVP by MASTER §58 |
| E-19 | Support / tickets | harness UI only; P14 §41 conditional ("if in scope") | no explicit approval found | – | NOT_ESTABLISHED_AS_REQUIREMENT | ✗ | ✗ | ✗ | – | fixture UI | – | – | – | route scan, docs grep | none unless owner confirms |
| E-20 | Customer context privacy | MASTER P8/§33 | A | 8 | COMPLETE (tests) | ✓ | ✓ | ✓ | – | – | – | – | tenant ✓ | tests | none |
| E-21 | Resource/cost: adapters thin, heavy work in Core, budget before spend, unknown ≠ 0 | MASTER §63; P14 §23–24; P17 | A/B | 12/17 | COMPLETE | ✓ | ✓ | ✓ | ✓ | – | ✓ | ✓ (no model call in loop) | ✓ | P17 | none |
| E-22 | AIExecution canonical record | P16 lock, P17 | B | 17 | COMPLETE except real provider | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | P17 docs | BLOCKED_EXTERNAL_DEPENDENCY |
| E-23 | Controlled pilot at MASTER §55 volumes (10–20 KOs, 5–10 products, 50–100 evidence) | MASTER §55, P15 | A | 15 | NOT_VERIFIED | – | – | – | – | – | smoke only | 1-product E2E | – | this doc | run the pilot (Phase 15) with owner data |
| E-24 | Signed cart intent | MASTER §36 ("Future commerce integration may…") | D | — | NOT_ESTABLISHED_AS_REQUIREMENT (future) | – | – | – | – | – | – | – | – | MASTER §36 wording | none |
| E-25 | Scale | MASTER P16 | A (deferred) | 16 (renumbered) | SUPERSEDED / not yet due (§55) | – | – | – | – | – | – | – | – | MASTER §55 | none now |

## Update — final existing-owner closure pass (append-only; rows above are the previous pass)
| ID | Requirement | New status | Evidence |
|---|---|---|---|
| E-13 | Rights layer / access policy | COMPLETE (tests) | D-05 fixed; precedence + fail-open tests pass |
| E-14 | Analytics / telemetry | COMPLETE (tests) | D-03, D-04, D-06 fixed |
| E-15 | Email 6-digit code login | COMPLETE_RUNTIME (delivery to real mailboxes BLOCKED_EXTERNAL_DEPENDENCY: no email provider; Google login BLOCKED_EXTERNAL_DEPENDENCY: no OAuth credentials) | 9 tests; real SMTP run |
| E-16 | Billing | NOT_ESTABLISHED (corrects the previous pass): ADR-082/083/084 are PROPOSED; MASTER §54/§58; Phase 14 §31–32 conditional | FINAL_EXISTING_OWNER_AUDIT.md |
| E-17 | Dashboard wired to backend | PARTIAL → priority screens COMPLETE (Overview, Knowledge + detail, Sources, Processing, AI executions, AI visibility, Products + offers, Settings/organization); other screens still sample (labelled) | Chrome check |
| E-09/E-10 | WordPress / WooCommerce | COMPLETE_RUNTIME (regression incl. stock sync) | E2E regression |
| E-23 | §55 pilot | NOT_VERIFIED — needs the owner's real domain content and products | — |
