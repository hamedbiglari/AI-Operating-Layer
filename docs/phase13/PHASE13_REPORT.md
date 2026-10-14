# PHASE 13 — REPORT

**Project:** AI Operating Layer / Knowledge-to-Commerce
**Phase 13 scope as executed:** Analytics, Demand Intelligence and AI
Access Control, plus the dashboard that surfaces them
**Date:** 2026-09-17

---

# FINAL PHASE 13 STATUS: `BLOCKED`

Phase 13 is **not** PASS, and this report does not argue that it should
be. Two independent reasons, either of which alone is sufficient:

1. **The Phase 12 gate is not PASS.** The MASTER PRE-PHASE-13 context
   records Phase 12 as `CONDITIONAL` (§51, §147, §178), and §146 states
   plainly that a non-PASS phase locks the next one. The Phase 13 protocol
   §1.1 says the same thing from the other direction.
2. **No verification was executed.** The container in which this work was
   authored has no FastAPI, no SQLAlchemy, no Alembic, no pytest, no
   PostgreSQL, no PHP binary and no network egress. Nothing in this phase
   has been run — not one test, not one migration, not one render.

Per §109 and §46, neither of those converts to PASS by wording.

**Phase 14 gate: `LOCKED`.**

---

# 1. What was done, and under what label

This work was carried out on the project owner's explicit instruction to
implement Phase 13. That instruction is recorded, and so is the fact that
it runs ahead of the owner's own protocol:

* MASTER §175/§176/§180 state that the next action is the Product/UX
  Architecture Checkpoint, then **STOP and wait for approval** — and that
  checkpoint has been completed, with status `ENVIRONMENT BLOCKED`, not
  approved-and-green.
* MASTER §146 locks Phase 13 while Phase 12 is `CONDITIONAL`.

So the correct label for everything below is:

```
IMPLEMENTED — NOT VERIFIED — NOT ACCEPTED
```

It is a reviewable implementation proposal against a locked gate, not a
delivered phase. Recording that is the difference between this being
useful and this being a false completion.

---

# 2. Owner requirements and where each one landed

| Owner asked for | Where it lives | Verified? |
|---|---|---|
| Geographic location per visit | `page_views.geo_*`, `AIOL_Geo` (edge headers only) | No |
| IP address per visit | `page_views.ip_address` + `/24` truncation + 30-day horizon | No |
| Time on page, for humans and bots | `page_views.dwell_ms` (NULL when unmeasured), `aiol-dwell.js` | No |
| Human vs bot view counts | six-way split on `content_view_daily` | No |
| Sort content by views, both directions, with numbers | `GET /telemetry/content-stats?sort_by=total_views&sort_dir=asc\|desc` | No |
| Record what users search for | `SearchDemandEvent` → canonical Phase 6 `Query` | No |
| Record what bots search for | same table, `actor_type` discriminator | No |
| Free / paid / forbidden access levels | `AccessPolicy`, HTTP 200 / 402 / 403 | No |
| Block training crawlers, allow Q&A | `AccessPurpose` axis + precedence | No |
| **No restriction on which AIs are listed** | `resolve_or_discover` has no rejection path | No |
| Cloudflare-style AI control as the pattern | purpose-based rules, robots.txt + `/.well-known/ai-policy` | No |
| Green connection indicator | `GET /telemetry/health`, dashboard status strip | No |
| Logs captured + clear-history button | `AIOL_Logger` reused; clear clears adapter state only | No |
| Version displayed | plugin `0.13.0`, core `0.13.0`, telemetry API `13.0` | No |

Every row in the right-hand column says No for the same reason: nothing
ran. It is not that these are half-built.

---

# 3. Changes made

## 3.1 Cloud Core

* **8 new enums** (`ActorType`, `ActorConfidence`, `AccessPurpose`,
  `AccessTier`, `AccessDecision`, `AgentRegistrationOrigin`,
  `SearchDemandSource`, `GeoResolutionMethod`) + 2 additive
  `AdapterScope` values.
* **5 new models:** `AiAgent`, `AccessPolicy`, `PageView`,
  `ContentViewDaily`, `SearchDemandEvent`.
* **5 new services:** `actor_signatures`, `ai_agent_service`,
  `access_policy_service`, `telemetry_service`, `search_demand_service`.
* **1 new router:** `/api/v1/telemetry`, 15 endpoints.
* **Migration `0016`**, with an explicit, documented, destructive
  downgrade (including the `adapter_scope` enum rebuild).
* `SORTABLE_FIELDS` extended for the 4 new listable models.
* `redis_available()` added to `rate_limit.py`; `CORE_VERSION` added to
  settings.

## 3.2 WordPress plugin (0.9.0 → 0.13.0)

* `AIOL_Telemetry` — observe, buffer, cron-flush, dwell beacon endpoint.
* `AIOL_Access_Gate` — edge enforcement, `robots.txt`,
  `/.well-known/ai-policy`.
* `AIOL_Geo` — header pass-through only.
* `AIOL_Actors` — signature table **regenerated** from Core's canonical
  list; gained `purpose_for()`, `signature_for_label()`,
  `signature_keys()`.
* `admin/view-dashboard.php` — the merchant dashboard.
* `assets/js/aiol-dwell.js` — visibility-based dwell measurement.
* Design system and icon registry copied in by
  `scripts/sync-design-system.php`, closing checkpoint **UX-08**.

## 3.3 Frontend / harness

* 7 icons added to the canonical registry (67 → 74).
* 3 screens added to `visual-harness/build.js`:
  `#screen-analytics`, `#screen-access`, `#screen-operations`.
* `docs/ux/DASHBOARD_UX.md` written; `DECISIONS.md` gained ADR-076…081.

---

# 4. Decisions, and what was rejected

Full text in `docs/DECISIONS.md`. The rejections matter more than the
acceptances:

| Rejected | Why |
|---|---|
| "Strictest wins" policy resolution | makes *"block all AI crawlers except this one"* inexpressible |
| Default-allow reported as `ALLOWED` | reports a decision nobody made as a permission |
| Default-forbid | would remove merchants from answer surfaces the day this ships, unchosen |
| A price column on `paid` | nothing meters or bills; a number would look like a working price |
| `bot_views` / `human_views` only | collapses the one distinction that changes what the merchant does |
| Deriving geography from IP | no database, no lookup; a guessed country cannot be corrected by anyone who spots it |
| Plugin calling Core per request | puts Core's latency and uptime on every page load |
| Each runtime keeping its own signature list | drift is invisible: edge blocks one thing, report shows another |
| Auto-creating knowledge gaps from zero-result searches | a gap list full of typos is a gap list nobody reads |
| Storing dwell as an average | loses re-averaging; a mean over 3 and over 3,000 are not the same claim |
| `ip_address` in the sortable allow-list | sorting by IP is a lookup dressed as an ordering |

---

# 5. The supersession that must not be missed

**ADR-079 supersedes the privacy narrowing in ADR-046.** ADR-046 remains
on file, unedited.

ADR-046 deliberately stored no IP and no query string. The pre-Phase-13
checkpoint §P.5 found the original design conversation had asked for
geography and dwell time, and **declined to close the gap by default**,
recording it as an owner decision. The owner has now decided the other
way, in writing, in the Phase 13 instruction.

That is a legitimate supersession, not drift — but it has a cost, and the
implementation carries the cost visibly rather than waving it away: `/24`
truncation on write, a 30-day horizon on the full address, OWNER/ADMIN-only
access to it, no cross-session visitor id anywhere, and checkpoint
§76/§77's prohibition on profiling left completely untouched.

The AI Visibility harness screen said *"no location and no time-on-site
are collected."* That sentence has been corrected in place, with a pointer
to ADR-079 — leaving it standing would have made the prototype contradict
the product.

---

# 6. Verification — the part that decides the verdict

## 6.1 Environment

```
python3 -c "import fastapi"     -> ModuleNotFoundError
python3 -c "import sqlalchemy"  -> ModuleNotFoundError
python3 -c "import pytest"      -> ModuleNotFoundError
python3 -c "import alembic"     -> ModuleNotFoundError
which php                       -> (nothing)
which psql                      -> (nothing)
network egress                  -> blocked (HTTP 403 from the proxy)
node visual-harness/measure.js  -> exit 2, "puppeteer is not installed"
```

## 6.2 Results table

| Dimension | Status | Evidence |
|---|---|---|
| Static analysis (Python) | **PASS** | every file under `cloud-core/app/` parses (`ast.parse`, all files) |
| Static analysis (JS) | **PASS** | `node --check assets/js/aiol-dwell.js`; `node build.js` regenerated the harness |
| Static analysis (PHP) | **BLOCKED** | no `php` binary; `php -l` not run on any file |
| UX static conformance | **PASS** | `node visual-harness/check.js` → 33 passed, 0 failed, after every addition |
| Unit tests | **BLOCKED** | ~50 tests written across 2 files; **0 executed** |
| Integration | **BLOCKED** | no database |
| Negative paths | **BLOCKED** | written (422/403/404/duplicate/boundary); 0 executed |
| Contract | **PARTIAL** | schemas written and inspected; never exercised |
| Security / tenant isolation | **BLOCKED** | 5 isolation tests written; 0 executed; composite FKs never applied to a real database |
| Concurrency / idempotency | **BLOCKED** | `event_key` uniqueness never exercised |
| Migration | **BLOCKED** | `0016` parses; `base→head→base→head` **not run** |
| E2E | **BLOCKED** | none attempted |
| Regression (Phase 0–12) | **BLOCKED** | the 772-test suite was **not run** against this tree |
| Mutation | **BLOCKED** | 11 planned in `MUTATION_PLAN.md`; **0 executed** |
| Runtime | **BLOCKED** | nothing started |
| Visual | **BLOCKED** | `measure.js` exit 2 |
| Accessibility | **PARTIAL** | static criteria hold; contrast/keyboard/SR **UNKNOWN** |
| RTL / LTR | **PARTIAL** | logical properties, `<bdi>`, `lang`-driven fonts present; **bidi as painted UNKNOWN** |
| Responsive | **BLOCKED** | `data-label` coverage static-checked; reflow never rendered |
| Performance | **PARTIAL** | server-side sort/filter/page + 14 new indexes; **no measurement** |
| Duplicate / dead-code audit | **NOT RE-RUN** | `test_forensic_integrity.py` (13 structural tests) not executed against the new modules |
| Documentation | **PASS** | ADR-076…081, `DASHBOARD_UX.md`, requirement matrix, this report |
| Memory | **PASS** | `MEMORY-CHANGE-P13-001.md` |

## 6.3 The honest summary

Two rows say PASS on execution (`check.js`, Python parse). Everything that
would constitute evidence of correctness says BLOCKED. **This
implementation has never been executed by anything.**

---

# 7. Forensic audit — what could still be wrong

Asked in the spirit of §121: actively looking for reasons not to pass.

1. **`test_forensic_integrity.py` has not seen the new modules.** Its 13
   structural invariants — duplicate Celery task names, orphan models,
   unregistered routers, dead enums, single query normalizer — are exactly
   the checks most likely to catch a defect in 5 new models and a new
   router, and none of them has run.
2. **`AccessPolicy.evaluate` is implemented twice** (Python and PHP). The
   signature lists are parity-tested; the *behaviour* is not. A
   behavioural edge/Core parity test is a named gap (P13-REQ-027).
3. **`ContentViewDaily` is a second place a view count exists.** ADR-080
   argues it is derived data with a stated derivation and a rebuild path,
   not a second source of truth. That argument is reasonable and is
   **unverified** — nothing has demonstrated that a rebuild reproduces the
   same numbers.
4. **`UNIQUE NULLS NOT DISTINCT` requires PostgreSQL 15+.** The migration
   uses it in two places. The project's minimum Postgres version is not
   stated anywhere I could find, so this is an **unverified assumption**,
   not a checked constraint.
5. **`INET` type + `ip_address=None` writes** were never round-tripped
   against a real database.
6. **The dwell beacon is unverified in any browser.** `sendBeacon`
   behaviour during `pagehide` varies; the measurement could silently
   never arrive, in which case every dwell is NULL — which is at least the
   honest failure mode, but it is still a failure mode nobody has looked at.
7. **`robots_txt` emits `Disallow` only for agent-specific FORBIDDEN
   rules.** An actor-type rule ("all AI crawlers") produces nothing in
   robots.txt, because there is no User-agent token for a class. That is
   deliberate and documented, and it means the two surfaces disagree in a
   way a merchant could misread.
8. **Nothing verifies the plugin against a real WordPress.** `is_rtl()`,
   `wp_localize_script`, `template_redirect` priority ordering,
   `admin-ajax` nonce flow — all unexercised, as they have been since
   Phase 9.
9. **Phase 12's own blockers are untouched** and were not to be touched:
   live AI platforms, Search Console, SERP, WordPress, WooCommerce,
   browser.

---

# 8. What must happen before Phase 13 can be re-evaluated

In order, and none of it is optional:

1. Resolve the **Phase 12 gate** (§51's four blocked external providers),
   or obtain an explicit, recorded owner decision to proceed with Phase 12
   at `CONDITIONAL`, naming what that accepts.
2. Run the suite in a real environment:
   ```
   pip install -r cloud-core/requirements.txt
   docker compose up -d postgres redis
   cd cloud-core && alembic upgrade head
   python -m pytest -q                        # expect 772 + ~50 new
   bash scripts/verify_migration_cycle.sh     # base->head->base->head, 0016 included
   php wordpress-plugin/tests/run.sh
   php scripts/sync-design-system.php         # must report "already in sync"
   php scripts/sync-signatures.php            # diff against the committed block
   ```
3. Execute all 11 mutations in `MUTATION_PLAN.md`.
4. Install a browser and run `node visual-harness/measure.js`, then
   inspect by eye per §142: desktop/tablet/mobile × LTR/RTL ×
   English/Persian/mixed × light/dark, plus focus, empty, error, long
   Persian titles and long paths.
5. Re-run `test_forensic_integrity.py` and the cross-tenant route sweep
   **including the new routes**.
6. Close the named traceability gaps in `REQUIREMENT_MATRIX.md` §Gaps.

---

# 9. Final table

| Category | Status | Evidence |
|---|---|---|
| Phase 12 prerequisite | **CONDITIONAL — not PASS** | MASTER §51, §147, §178 |
| Phase 13 requirements | **PARTIAL / BLOCKED** | `REQUIREMENT_MATRIX.md` — 0 rows PASS |
| Implementation | **IMPLEMENTED** | 5 models, 5 services, 15 endpoints, migration 0016, 4 plugin classes, 3 harness screens |
| API/UI contract | **PARTIAL** | schemas written; never exercised |
| Regression | **BLOCKED** | 772-test suite not run |
| Mutation | **BLOCKED** | 0 of 11 |
| E2E | **BLOCKED** | none attempted |
| Runtime | **BLOCKED** | nothing started |
| Visual | **BLOCKED** | `measure.js` exit 2 |
| Accessibility | **PARTIAL** | static only |
| RTL/LTR | **PARTIAL** | static only |
| Responsive | **BLOCKED** | never rendered |
| Performance | **PARTIAL** | indexes + server-side ops; unmeasured |
| Security | **BLOCKED** | isolation tests written, 0 executed |
| Duplicate/dead-code audit | **NOT RE-RUN** | forensic suite not executed |
| Documentation | **PASS** | ADR-076…081, DASHBOARD_UX, matrix, this report |
| Memory | **PASS** | `MEMORY-CHANGE-P13-001.md` |
| Final forensic audit | **PARTIAL** | §7 above; 9 open concerns |
| **Phase 14 gate** | **LOCKED** | Phase 13 is not PASS |

```
FINAL PHASE 13 STATUS: BLOCKED
```

Blockers, in full:

1. Phase 12 is `CONDITIONAL`; §146 locks Phase 13 on that alone.
2. No Python runtime for the application stack — no unit, integration,
   negative, security, concurrency or E2E evidence.
3. No PostgreSQL — no migration cycle, no constraint verification.
4. No PHP binary — no lint, no plugin test execution.
5. No browser — visual, accessibility-as-rendered, RTL-as-painted and
   responsive all UNKNOWN.
6. No mutation execution — 0 of 11.
7. Phase 0–12 regression not run against this tree.
8. `test_forensic_integrity.py` not run against the new modules.
9. The Product/UX Architecture Checkpoint itself stands at `ENVIRONMENT
   BLOCKED`, not approved, and MASTER §176 requires explicit owner
   approval before Phase 13 begins at all.
