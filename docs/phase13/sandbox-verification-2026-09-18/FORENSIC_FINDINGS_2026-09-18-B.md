# Forensic findings — session B, 2026-09-18

**Different from `README.md` in this folder** (session A, same date): that
session ran read-only checks against the package exactly as uploaded and
changed nothing. This session did a **tracing pass** — followed each
Phase 13 component's actual call graph end to end, by hand, since no
runtime exists here to do it automatically — and found and fixed four
real defects. This file documents them. It does not change the final
verdict: **`FINAL PHASE 13 STATUS: BLOCKED`**, for the same reason as
before — nothing below has been executed by anything, only read and
reasoned about.

None of these were caught by the ~50 pytest cases or the 2 PHP test files
written earlier, because none of those have ever been executed either.
They were caught by manually tracing: bootstrap → constructor → method
call → does the callee exist → is the caller ever invoked.

---

## Finding 1 — `AIOL_Client::get()` / `->post()` did not exist

**Severity: would have been a Fatal Error on every real request.**

`AIOL_Telemetry::flush()` and `AIOL_Access_Gate::refresh()` (written in
an earlier session) called `$this->client->get(...)` and
`$this->client->post(...)`. `AIOL_Client` has no such methods — every one
of its methods is typed and named after the endpoint it calls
(`identity()`, `upsert_mapping()`, etc.), by explicit design stated in its
own file docblock. A generic verb-based method was never added.

**Fix:** seven new typed methods added to `AIOL_Client`, following its
existing pattern exactly: `ingest_page_views()`, `ingest_search()`,
`list_access_policies()`, `telemetry_health()`, `content_stats()`,
`list_agents()`, `search_demand_terms()`, `list_page_views()`. The two
broken call sites were updated to use them.

**Why this survived undetected:** nothing had ever called these methods,
because of Finding 2.

---

## Finding 2 — `AIOL_Telemetry` and `AIOL_Access_Gate` were never instantiated

**Severity: all Phase 13 plugin-side behaviour was dead code.**

Both classes were `require_once`'d in `ai-operating-layer.php` — so PHP
would parse them without error — but `aiol_bootstrap()` never did
`new AIOL_Telemetry(...)` or called `->register()` on either. Concretely,
on a real WordPress install this meant:

* no page view was ever observed (the `template_redirect` hook was never
  attached);
* the dwell beacon's AJAX endpoints were never registered — every request
  to them would 400 as an unknown action;
* the access gate never enforced anything — every request passed through
  regardless of policy;
* `robots_txt` and `/.well-known/ai-policy` were never registered.

**Fix:** both classes are now constructed and registered in
`aiol_bootstrap()`, and `AIOL_Admin`'s constructor gained two nullable
parameters so it can read from them without breaking any existing call
site.

---

## Finding 3 — the custom cron intervals were never registered

**Severity: telemetry buffer would never flush; policy cache would never refresh.**

`AIOL_Telemetry::register()` calls
`wp_schedule_event(..., 'aiol_five_minutes', ...)` and
`AIOL_Access_Gate::register()` calls
`wp_schedule_event(..., 'aiol_fifteen_minutes', ...)`. WordPress ships
only `hourly`/`twicedaily`/`daily` by default; an unrecognised interval
name makes `wp_schedule_event()` return `false` **silently** — no
warning, no log entry, the event is simply never scheduled.

**Fix:** a `cron_schedules` filter registering both intervals was added
to the plugin bootstrap, plus cleanup of both hooks on deactivation
(matching the existing pattern for `AIOL_WooCommerce::CRON_HOOK`).

---

## Finding 4 — the dashboard's access-decision lookup used a fragile reverse label lookup

**Severity: correct today, silently wrong after a merchant renames an agent.**

`AIOL_Access_Gate::evaluate()`'s `signature_for()` always derived the
policy-matching signature from `$actor['label']` via
`AIOL_Actors::signature_for_label()` — a reverse lookup against the
canonical signature table. That is the only option available at the edge
(`enforce()`, given a raw User-Agent, has a label and nothing else), but
the dashboard controller reads Core's `AiAgent` records directly and
already knows the canonical `signature` — going through the label was an
unnecessary indirection that breaks the moment a merchant renames an
agent (`display_name` diverges from the canonical label format the
reverse lookup expects), silently disabling every agent-level policy row
for that agent with no error anywhere.

**Fix:** `evaluate()` now accepts an optional direct `'signature'` key in
its `$actor` array and uses it without touching label at all; label-based
lookup remains the fallback used only by the edge path. Two regression
tests were added to `tests/test-access-gate.php` covering both paths
explicitly, so a future change cannot silently drop either one.

---

## Finding 5 (backend, not plugin) — `PageViewRead` exposed only `ai_agent_id`, a UUID

**Severity: the "recent requests" table the owner asked for would have shown raw UUIDs instead of "GPTBot".**

Found while building the per-request traffic table for the dashboard (a
completion, not a defect in already-shipped code, but it would have
shipped as a usability defect if not caught here). `PageView.ai_agent_id`
is a UUID foreign key; no field carried the human-readable signature.

**Fix:** `PageViewRead.agent_signature` added (nullable), resolved via a
new `telemetry_service.signatures_for()` — one batched `IN`-clause query
per response, not one query per row. Both `/telemetry/page-views` and
`/telemetry/page-views/with-ip` now attach it. Two functional tests plus
one query-count regression test (`test_signatures_for_is_one_query_not_one_per_row`)
were added.

---

## What this does and does not mean for the verdict

**Does mean:** the package handed to a real WordPress + Cloud Core
deployment today would have failed in at least three visible ways
(Findings 1–3) before a single dashboard number was ever seen. That is
now fixed at the source level.

**Does not mean:** any of it has been executed. `pip install fastapi` was
attempted again this session and failed exactly as before
(`No matching distribution found`, no network egress). No PHP binary
exists in this sandbox — the closest available check was a brace/paren
counter across every `.php` file, and it is reported honestly as
**unreliable** (it flagged 4 files for "paren imbalance" that turned out,
on inspection, to be parentheses inside comments and string literals —
not real errors; a tool this crude cannot be used as evidence of
correctness in either direction).

```
python3 -m py_compile <all 272 .py files>   -> 0 errors (re-run after every edit)
node visual-harness/build.js                 -> rebuilt, 74 icons
node visual-harness/check.js                 -> 33/33 passed (re-run after every edit)
node visual-harness/measure.js               -> ENVIRONMENT BLOCKED (no Chromium) — correctly, not a false pass
php -l <any file>                            -> BLOCKED (no php binary)
python -m pytest                             -> BLOCKED (no fastapi/sqlalchemy/pytest)
```

`FINAL PHASE 13 STATUS: BLOCKED` — unchanged, for the same reasons as
`PHASE13_REPORT.md` already states. What changed is that the code this
verdict applies to is now measurably more correct than it was, because
four real defects that would have surfaced on first real deployment were
found and fixed before that deployment happens, not after.

---

## Addendum — UX additions requested after this file was first written

The owner asked for two more things, both added to the visual harness only
(the only thing executable in this sandbox), and both real UI completions
rather than backend claims:

### "Visible to AI right now" is now a click-through

The dashboard stat card now links to a new screen,
`#screen-visibility-detail`, styled after the two references the owner
provided (Google Search Console's query/page/country tabs and time-range
switcher; Google Analytics' snapshot cards and location breakdown). It
adds:

* a time-range tab strip (Live / Today / 7 days / 28 days / 3 months /
  Year / All time) — static in this harness, not wired to a backend;
* a day-by-day bar chart of the two signals this product already keeps
  separate (platform observations vs. automated requests) — **not**
  relabeled as "clicks/impressions", because this product has no click
  event and inventing one to match a screenshot would be exactly the
  fabricated-metric problem ADR-064 forbids;
* a location breakdown — schematic marker-on-a-grid, explicitly labeled
  as schematic rather than a rendered map, reading the same
  `geo_country` field the Analytics screen's own "How we know" column
  already governs;
* a breakdown table with Queries/Pages/Countries/Actor types/Days tabs
  (query text only, matching the GSC reference image);
* Export CSV / Export PDF buttons, present as UI affordances only — no
  export capability exists in this harness or in the Cloud Core API
  built so far, and nothing here claims otherwise.

**A real static-checker failure was caught and fixed while building
this**, worth recording because it is exactly the kind of thing a
"looks right" pass would have shipped: the chart and the map were
initially built with raw `<svg>` markup, which `check.js` correctly
rejected — every `<svg>` in this harness must be a registry icon
(§56/§57), and a 700×160 chart is not an icon. Rather than tag the chart
with `class="icon"` to make the checker pass (which would be gaming the
rule the checker enforces, not satisfying it), both were rebuilt in pure
CSS (flexbox bars, absolutely-positioned circles). Re-run: 33/33.

A second real failure, same rebuild: the chart legend used Unicode `■`
characters as color swatches, which `check.js` also correctly rejects
("no Unicode box/arrow/tick glyphs as icons"). Replaced with small
`<span>` elements styled via `background-color`, using only existing
design tokens.

### Knowledge is now a list of independently-manageable objects

`#screen-knowledge` was, until this session, a single hard-coded detail
screen for one keyword (ترنجبین). The owner correctly pointed out that a
real deployment produces knowledge for many keywords (ترنجبین, زعفران,
سیر, آویشن were given as examples) and each one needs its own full
management window.

Fixed by refactoring the single screen into:

* `#screen-knowledge` — now a **list** of knowledge-object cards (one per
  keyword), each showing source/claim/evidence/gap counts at a glance;
* four detail screens, `#screen-knowledge-{taranjebin,saffron,garlic,thyme}`,
  built from one parameterised template function
  (`knowledgeDetailScreen(k)`) rather than four copy-pasted screens — so a
  future structural change (a new stat, a new evidence-kind row) is made
  once, not four times;
* every stale link that used to assume `#screen-knowledge` meant "the
  Taranjabin detail" was traced and corrected: the source-detail screen's
  "Knowledge objects: 3" stat, the provenance screen's "Review the
  conflict" link, and the knowledge-gap screen's breadcrumb now all point
  at `#screen-knowledge-taranjebin` specifically. One (the dashboard's
  "Coverage honesty" card) was left pointing at the list, because it
  discusses claims in general, not one specific object — that is a
  genuine improvement now that a list exists to point to.

All fixture data for saffron, garlic and thyme is invented for this
harness and is not a claim about real project content — the harness
banner ("Representative fixture data, not production content") governs
these exactly as it already governs every other number on every other
screen.

**Still not done, stated plainly:** none of this is backed by four real
knowledge objects in Cloud Core — no `Knowledge`/`KnowledgeObject` model
work was part of Phase 13's scope (that domain was built in earlier
phases; Phase 13 only added the AI-access and analytics layer). The
harness now correctly *represents* what a multi-object Knowledge section
should look like; wiring it to real per-object data is Phase 0–12
integration work, not something this session touched or claims to have
touched.

```
node visual-harness/build.js   -> rebuilt, 74 icons, 239 KB
node visual-harness/check.js   -> 33/33 (was 31/33 mid-edit; both real
                                   failures traced to root cause and fixed,
                                   not suppressed)
link integrity check           -> 84 internal links, 0 broken
python ast.parse (272 files)   -> 0 errors
node --check (beacon)          -> OK
```

`FINAL PHASE 13 STATUS: BLOCKED` — still unchanged. Nothing in this
addendum touches the reasons stated in `PHASE13_REPORT.md`: no Python
application runtime, no PostgreSQL, no PHP binary, no browser, in this
sandbox.

---

## Addendum 2 — an actual world map, replacing the 6-point schematic

The owner sent reference screenshots (Google Search Console's query/page
time-range UI; Google Analytics' snapshot cards and per-city location
table) and asked specifically for a **world map** for the location
breakdown, not the earlier 6-marker schematic-on-a-grid.

The earlier `schematicMap()` placed 6 hand-picked (x%, y%) points with no
real projection behind them — recognizable as "a chart with dots" but not
as a map. It's replaced with a **stylized dot map**: ~670 points sampled
from a coarse per-continent bounding-region approximation, projected with
a real equirectangular formula (`x=(lon+180)/360`, `y=(lat_top-lat)/(lat_top-lat_bot)`,
cropped to the inhabited band so it isn't mostly empty ocean/poles), so
the silhouette reads as a world map at a glance. The 6 country bubbles
now use the same projection from each country's approximate real
lon/lat centroid, so they land inside their own continent's dot cluster
instead of at an arbitrary hand-tuned position.

**What this is not, stated the same way the rest of this file states its
limits:** the continent regions are a handful of hand-drawn bounding
boxes, not a real coastline/vector dataset — there is no bundled
cartography source anywhere in this project (ADR-079 already declines to
invent geolocation; this extends the same discipline to not inventing
false map precision). The harness caption says so explicitly. It is
built as CSS-positioned `<div>` dots, not `<svg>`, for the same reason
`sparkChart()` isn't SVG: every `<svg>` in this harness must be a
registry icon (§56/§57 in `check.js`), and 670 dots is not an icon.

```
node visual-harness/build.js   -> rebuilt, 358 KB (was 239 KB)
node visual-harness/check.js   -> 33/33, unchanged
```

`FINAL PHASE 13 STATUS: BLOCKED` — unchanged, same reasons as above. This
is a UI/UX completion to the one thing in this sandbox that can be built
and checked; it does not touch, and does not claim to touch, any of the
backend/runtime/security/E2E/mutation/accessibility-as-rendered gates
that remain genuinely blocked without a real Python/PHP/Postgres/browser
environment.

---

## Addendum 3 — GA4 Realtime + Search Console date-range research, and per-keyword scoping

The owner asked for two more things, both checked against real product
documentation online rather than assumed from memory:

### What was researched, and the sources

* **Search Console's actual date-range set.** Verified via Search Engine
  Land's coverage of the Performance-report date picker and multiple
  independent write-ups of the "16 months" retention ceiling: the real
  picker offers 24 hours, 7 days, 28 days, 3 months, 6 months, 12 months,
  and 16 months (Search Console's actual data-retention limit — not a
  round number, and not "All time", which Search Console does not offer).
  `TIME_RANGES` was corrected to this exact set (it previously had
  invented entries — "Today", "Year", "All time" — that don't exist in
  the real product).
* **GA4's Realtime report.** Verified via Google's own Analytics Help
  Center article on the Realtime overview's cards, and the Realtime
  Reporting API guide: Realtime is a *distinct* report, on a 30-minute
  window, refreshed continuously, broken down by page/screen, country,
  and (for GA4) device — never merged into the historical daily/weekly
  report. This product does not have "device" as a concept for bot/agent
  traffic, so the equivalent breakdown uses actor type
  (crawler/user-agent/agent-tool/search-crawler) instead of inventing a
  device dimension that would not mean anything for this traffic.

### What was built from that research

* `liveActivityPanel()` — a "Right now" card at the top of the full
  visibility report: total requests in the last 30 minutes, a per-minute
  bar chart, and three "right now" breakdowns (pages, countries, actor
  types) — modelled on GA4's own card set, explicitly labeled as a static
  fixture ("refreshed continuously in production — this harness is a
  static fixture, not a live connection"), never claiming to be a live
  socket this harness cannot actually hold open.
* `TIME_RANGES` corrected to Search Console's real set, with `Live`
  added on top for the GA4-style panel (Search Console itself has no
  realtime view; GA4 does — the owner asked for GA4's realtime
  specifically, so it is additive, not a claim that Search Console has
  this).

### The other point: Knowledge must scale past a handful of keywords

The owner clarified that ترنجبین/زعفران/سیر/آویشن were **examples**, not
the ceiling — a real deployment could hold tens, hundreds or thousands of
knowledge objects, and **every one needs its own independent AI-visibility
report**, not a single shared dashboard.

Two changes:

1. **`#screen-knowledge` (the list)** gained a real search box, a sort
   control, and corrected copy: it no longer implies "a real deployment
   may have hundreds" as a soft aside — it now states the screen is built
   to hold thousands, searched/filtered/sorted/paginated server-side the
   same way `#screen-sources` already claims to be, with an explicit
   "Showing 4 of 4 in this fixture — representing an organization that
   may really hold thousands" note so the fixture's small size is never
   mistaken for a design ceiling.
2. **`keywordVisibilitySummary(k)`** — a new card embedded in *every*
   knowledge object's own detail screen: platform observations, automated
   requests, a 14-day chart and a 2-row country table, all **scoped to
   that keyword's own pages**. Numbers are deterministic per-keyword
   (derived from the object's `id` via a small hash), so the four
   existing objects each show genuinely different numbers instead of
   repeating one shared fixture — demonstrating "every keyword gets its
   own independent visibility report" without literally cloning the full
   670-dot world map four times (which would have quadrupled the file's
   weight for a static demo). It links back to the one shared full report
   (`#screen-visibility-detail`) for cross-keyword comparison, and its own
   caption states plainly that in production this is one filtered query
   against the same `page_views`/`search_demand_events` tables, not a
   second per-keyword pipeline — consistent with the project's "exactly
   one source manager" rule (`START_HERE.md` §4).

### A real bug caught while building this

`keywordVisibilitySummary()` referenced `GEO_POINTS`, which was declared
with `const` later in the same file (inside the map-building code added
in the previous session). Because `KNOWLEDGE_DETAIL_SCREENS` evaluates
eagerly at module-load time, this threw
`ReferenceError: Cannot access 'GEO_POINTS' before initialization` — a
real JavaScript temporal-dead-zone error caught by actually running
`node visual-harness/build.js`, not by inspection. Fixed by moving the
whole map block (`WORLD_DOTS`, `GEO_POINTS`, `schematicMap()`) above the
Knowledge section instead of leaving it in declaration order convenient
for whoever wrote it last.

```
node visual-harness/build.js   -> rebuilt, 389 KB (was 358 KB)
node visual-harness/check.js   -> 33/33 (one real regression appeared and
                                   was fixed mid-edit — see git-history-
                                   equivalent above: a literal "→" in new
                                   copy tripped the no-Unicode-glyph rule,
                                   replaced with plain words, not suppressed)
python -m py_compile (273 files) -> 0 errors
```

`FINAL PHASE 13 STATUS: BLOCKED` — unchanged, same reasons as
`PHASE13_REPORT.md`. This addendum is UI/UX completion work, checked the
only ways this sandbox can check anything (static analysis, and reading
real product documentation instead of guessing at it) — it does not
touch, and does not claim to touch, backend runtime, database, security,
or rendered-browser evidence.

---

## Addendum 4 — Billing/entitlement architecture (design only), and UI IA changes from the "FINAL MASTER EXECUTION PROMPT"

The owner supplied a 276-section execution prompt asking for a real,
production-connected, multi-tenant SaaS platform: subscriptions,
PCI-scope payment processing, an AI wallet with ledger accounting, a
separate admin console, real GA4/GSC/Cloudflare integration, OAuth, and
full test/mutation/E2E coverage against a live environment.

**This was not implemented**, and saying so plainly is the point of this
addendum, not a hedge: this sandbox has no network, no Postgres, no
payment provider, no real Cloud Core to connect to, and no way to run a
persistent backend. Writing code that *claimed* to be connected to any of
that would violate the prompt's own repeated instruction ("Do not create
fake backend connectivity... fake billing balances... fake subscription
status"). Given a choice between fabricating a working-looking billing
system and being honest that one cannot be built here, this addendum
chose honesty, per the owner's explicit direction after being asked to
pick a priority.

### What was actually produced (design only, clearly labeled)

* `docs/billing/BILLING_ARCHITECTURE.md` — the provider-adapter /
  domain-service / dashboard-query-layer pipeline the prompt asks for,
  mapped onto this project's *existing* pattern (the same shape
  `telemetry_service.py` already uses for analytics), not a generic
  architecture invented from scratch.
* `docs/billing/BILLING_DATA_MODEL.md` — column-level schema for every
  table the prompt's §215 lists (Plan, PlanVersion, Subscription,
  Entitlement, TrialClaim, Payment, PaymentEvent, Invoice, Wallet,
  LedgerEntry, WalletReservation, UsageRecord, AICostRecord,
  ProviderPricingVersion, SubscriptionEvent).
* `docs/billing/ENTITLEMENT_MATRIX.md` — a capability × plan table,
  explicitly marked PROPOSAL, not a decision — which capabilities are
  Basic vs. Pro is the owner's business call, not an engineering one.
* `docs/billing/BILLING_API.md` — request/response contracts for the
  entitlement/subscription/wallet/trial-claim endpoints, following this
  project's existing error-shape conventions.
* `docs/DECISIONS.md` — ADR-082 through ADR-086, each marked **PROPOSED**
  (not ACCEPTED, unlike every prior ADR in this file, because these were
  never reviewed against a running system).
* `cloud-core/app/models/_draft_billing_not_wired/billing.py` — draft
  SQLAlchemy models (`Plan`, `Subscription`, `TrialClaim`, `Wallet`,
  `LedgerEntry`) written against this project's actual conventions
  (`UUIDPrimaryKeyMixin`, `TimestampMixin`, composite tenant foreign keys
  copied from `PageView`'s own pattern) so a real implementation session
  has something concrete to start from. The package is deliberately named
  with a leading underscore and "not_wired" so nothing in the real
  `app/models/__init__.py` or an Alembic autogenerate target ever picks
  it up by accident. It was `python -m py_compile`'d (0 errors across all
  275 `.py` files in the package after adding it) — that is the *only*
  verification this file has had. It has never been imported against a
  real SQLAlchemy metadata registry, never migrated, never run.

### What was also done: the UI/UX portion of the same prompt

The prompt's Part F/G (dashboard IA, Knowledge Objects table, settings)
overlaps with the owner's earlier, separate UI request. That part *can*
be advanced honestly in the static harness, and was:

* A real product top bar was added (distinct from the harness's own dev
  toolbar): account menu (matching the reference screenshot — Settings,
  Language, Get help, Upgrade plan, Get apps and extensions, Learn more,
  Log out), a tickets/chat icon with an unread indicator, a theme toggle,
  and a language toggle — all wired with real click/keyboard JS in the
  harness (open/close, Escape to close, click-outside to close), not just
  static markup.
* The sidebar identity block now shows the account email and site name,
  each truncated to 12 characters with an ellipsis and the full value in
  a `title` attribute — exactly the "Hello Hamed…" truncation rule from
  the owner's prompt — plus a working sidebar collapse/hide toggle and a
  second logout entry in the sidebar itself.
* "Knowledge" was renamed to "Knowledge Objects" everywhere (nav label,
  page heading), and its description text was replaced with the owner's
  exact required copy.
* The Knowledge Objects list changed from a 2-column card grid to the
  requested **dense linear row table** — one row per entity, columns for
  sources, a processing-percentage bar, conflicts, evidence-review state,
  approval state (green when approved), and a plain-language "action
  needed" column — the shape §24 of the new prompt and the owner's
  earlier message both ask for, built to hold thousands of rows via the
  same server-side search/filter/sort/paginate note already used on the
  Sources screen.
* A first Settings screen exists now (previously the nav item pointed
  nowhere) covering appearance, account, a clearly-labeled illustrative
  plan/billing section pointing at the new billing docs, and a
  danger-zone with Reset all settings vs. the much heavier Factory reset
  kept visually and functionally distinct (matching the owner's
  requirement that a factory reset must never be "one click").
* Ten new icons (chat, language, theme, logout, help, upgrade, apps,
  avatar, wallet, font) were added to the canonical icon registry
  (`frontend/icons/icon-paths.json`) rather than using emoji or ad-hoc
  inline SVG, keeping the "one registry, every client" rule intact.

```
node visual-harness/build.js   -> rebuilt, 411 KB (was 389 KB)
node visual-harness/check.js   -> 33/33
python -m py_compile (275 files, incl. the new draft billing module) -> 0 errors
```

### What this addendum does not claim

It does not claim Phase 13, or this new billing scope, is IMPLEMENTED,
VERIFIED, or PASS in any sense. The billing/entitlement/admin-console
portion of the owner's 276-section prompt remains entirely un-started as
running code — this addendum's contribution there is design documents and
one syntax-checked draft model file, explicitly so a real engineering
session (with real infrastructure) has a reviewed starting point instead
of nothing. `FINAL PHASE 13 STATUS: BLOCKED` — unchanged, for the same
reasons stated throughout this file.

---

## Addendum 5 — sortable columns on every table in the harness

The owner asked for sorting everywhere, especially Analytics & Demand.
All 20 `<table class="table">` instances in the harness (every screen —
Sources, Processing, Knowledge Objects, all four Analytics & Demand
tables, the AI-access list, everything) gained real, working column
sorting:

* Every `<thead>` `<th>` became a focusable button with `aria-sort`
  (`none` / `ascending` / `descending`), toggled on click or Enter/Space.
* A pure-CSS triangle (`border-*` trick, not a Unicode glyph — the
  harness's own check forbids Unicode arrow/box characters as icons, and
  this respects that) indicates direction; it rotates on ascending rather
  than needing a second icon.
* Sorting auto-detects numeric vs. text columns (stripping `,` and `%`
  first) and falls back to `data-sort-value` on a cell when the visible
  text isn't what should be compared.
* The Content table's old copy claimed **"nothing is re-ordered in the
  browser"** — true before this change, false after. Left uncorrected,
  that would have been the exact kind of self-contradicting UI copy this
  project's own audits look for. It now says client-side reordering is
  what this one-page fixture does, and that a real deployment with
  thousands of rows would sort server-side instead — both statements
  true of their respective sides.

### A real regression this introduced, and how it was fixed

Marking every sortable table with an added `sortable` class
(`class="table sortable"`) broke `check.js`'s own "data tables have a
caption" rule, because that check's regex matched the *exact* string
`class="table"` and stopped matching once a second class was appended —
tables silently counted as zero, so caption coverage looked satisfied by
default rather than actually checked. Confirmed by running the check and
reading its failure message (`20 captions for 0 tables`), not by
inspection. Fixed by widening the regex to match "table" as a class
token among others (`class="[^"]*\btable\b[^"]*"`), which still requires
`tables > 0` and `captions >= tables` — the assertion itself was not
loosened, only its detection of what counts as a table.

```
node visual-harness/build.js   -> rebuilt, 415 KB (was 411 KB)
node visual-harness/check.js   -> 33/33 (one real regression appeared
                                   mid-edit and was fixed at its root
                                   cause, not worked around)
python -m py_compile (275 files) -> 0 errors
```

The owner's separate 172-section "MASTER ENGINEERING PROMPT" (forensic
gap matrix, separate admin console, real billing/entitlement backend,
AI execution log, full test pyramid against a live environment) was
acknowledged but not attempted here, for the same reasons recorded
earlier in this file and in `docs/billing/BILLING_ARCHITECTURE.md`: no
network, database, browser or real Cloud Core connection exists in this
sandbox, and fabricating any of it would be exactly the "fake
completion" that prompt itself prohibits at length. `FINAL PHASE 13
STATUS: BLOCKED` — unchanged.

---

## Addendum 6 — two real defects reported with screenshots, both real, both fixed

The owner reported two problems with screenshots, not descriptions —
both checked against the actual markup rather than assumed, and both
turned out to be real.

### 1. Settings cards had no gap between them

Confirmed by reading the source: `screenSettings`'s four `.card` blocks
(Appearance / Account / Plan & billing / Danger zone) were written
without the `style="margin-top:var(--space-4)"` every other multi-card
screen in this harness carries on its second-and-later cards (visible in
`screenVisibilityDetail`, `knowledgeDetailScreen`, etc.). `.card` itself
has no margin in `components.css` — spacing between stacked cards is an
explicit per-instance choice throughout this codebase, and this screen's
second, third and fourth cards simply omitted it. Fixed by adding the
same `margin-top:var(--space-4)` the other screens use — not a new
spacing convention, just the existing one applied where it had been
missed.

### 2. Sidebar collapse button

The old control was a full-width "Hide sidebar" button living inside
`<aside class="sidebar">` itself — which meant collapsing the sidebar
also hid the only button that could bring it back, exactly the
un-expandable dead-end the owner's screenshot of Claude's own interface
(a small, permanent edge-of-panel toggle) was pointing at as the correct
pattern instead.

Fixed by:
* moving the control out of the collapsible `<aside>` entirely, into the
  topbar's start side — it now lives in the always-visible header, so it
  survives its own collapsed state;
* replacing the full-width text button with a small icon-only button
  (a new `sidebar-toggle` registry icon — a panel-with-a-divider
  pictogram, the conventional "toggle sidebar" glyph, not a directional
  arrow, so one icon correctly represents both collapsing and expanding);
* wiring proper `aria-expanded` (on the button, describing the sidebar
  it controls via `aria-controls="app-sidebar"`) and a label that flips
  between "Hide sidebar" / "Show sidebar" — the previous version used
  `aria-pressed`, which describes a toggle's own state, not a remote
  region's visibility, and was the wrong ARIA pattern for what this
  control actually does;
* a small CSS rotation on the icon so the control also looks different
  in the two states, not just announces it to assistive tech.

```
node visual-harness/build.js   -> rebuilt, 416 KB, 85 icons (was 84)
node visual-harness/check.js   -> 33/33 (icon-only-button count rose
                                   from 11 to 12, correctly picking up
                                   the moved/relabelled control)
python -m py_compile (275 files) -> 0 errors
```

`FINAL PHASE 13 STATUS: BLOCKED` — unchanged; both fixes are UI-layer
corrections to the static harness, not new backend evidence.

---

## Addendum 7 — sidebar toggle repositioned + Claude-Code-style drag-to-peek

The owner sent a screenshot of Claude Code's own left rail: the collapse
toggle sits inline with the "Claude" wordmark in one persistent top
strip, and described a specific interaction — dragging the toggle peeks
the panel open only while the mouse is held down and moving, releasing
hides it again, while a plain click toggles the panel permanently until
clicked again.

### Layout: one real top bar, not two stacked ones

The previous fix (Addendum 6) put the toggle in the main-column's own
`<header class="topbar">`, which sat beside the sidebar's separate
`.brand` row rather than inline with it — visually two different rows at
similar height, not one. This addendum restructures the shell properly:

```
.app (flex column)
  .app-topbar   <- NEW, full width, always visible, never collapses
      start: [sidebar-toggle] [brand icon + "AI Operating Layer"]
      end:   [tickets] [theme] [language] [account menu]
  .shell (grid: sidebar | main-column)
      .sidebar  <- now just: account/site context, nav, log out
      .main-column > <main>
```

The old per-column `.topbar` inside `main-column` is gone; there is now
exactly one top bar for the whole app, matching the reference screenshot
structurally (one persistent strip holding both the collapse control and
the brand, with everything else — including account controls that used
to live in the column-scoped header — sharing that same strip). The
toggle button and the "AI Operating Layer" wordmark are now literally
adjacent DOM siblings in one flex row, not two separately-positioned
elements that happened to render near each other.

### Interaction: click vs. drag are genuinely different code paths

Implemented with Pointer Events, not plain `click`, because distinguishing
"held and dragged" from "pressed and released in place" requires tracking
movement between `pointerdown` and release:

* `pointerdown` records the start position and captures the pointer (so
  movement is tracked even if the cursor leaves the small button while
  dragging).
* `pointermove` (while the primary button is held) checks distance moved
  against a 4px threshold; crossing it sets `didDrag = true` and adds a
  `.sidebar-peeking` class that — via a CSS rule scoped to
  `.sidebar-collapsed.sidebar-peeking` — visually restores the sidebar's
  width and visibility WITHOUT touching the underlying
  `.sidebar-collapsed` class at all.
* `pointerup` / `pointercancel` just removes `.sidebar-peeking`. Nothing
  about the permanent state changed, so the sidebar reverts to whatever
  it already was.
* A single `click` handler does the permanent toggle — and is also what
  keyboard activation (Enter/Space) fires, with no pointer events at all,
  so keyboard users still get the ordinary toggle behaviour with no
  drag concept involved. The tricky part: the browser fires `click` after
  `pointerup` even for a drag, so the `click` handler checks the same
  `didDrag` flag first and, if it was a drag, resets the flag and returns
  without toggling — otherwise a drag would both peek AND permanently
  toggle on release.

```
node visual-harness/build.js   -> rebuilt, 419 KB, 85 icons (unchanged
                                   icon count — no new icon needed, this
                                   was layout + interaction only)
node visual-harness/check.js   -> 33/33
python -m py_compile (275 files) -> 0 errors
```

`FINAL PHASE 13 STATUS: BLOCKED` — unchanged.

---

## Addendum 8 — the active-tab bug was a real missing feature, not a typo

The owner reported "Sources & Documents" showing as the active/hovered
tab instead of "Dashboard" at load. Investigating found something bigger
than a wrong hardcoded index: **no hash-routing existed in the harness at
all.** `.nav a` links, breadcrumb links, and cross-links (e.g. "Open the
site-wide report" on a keyword's own visibility card) all pointed at
`#screen-...` ids, but nothing in the script listened for `hashchange` or
updated which `.screen` had `.is-active` when one was clicked — only the
dev harness's own "Screen" `<select>` dropdown actually switched screens.
Every in-app link was cosmetically wired but functionally inert; the
"active" nav item the owner saw was a single hardcoded `aria-current` on
array index 3 (Sources & Documents) baked in at build time, unrelated to
whatever was actually showing.

Fixed with real routing, not a hardcoded index swap:

* a `hashchange` listener plus an initial-load check (`location.hash` if
  present, else `screen-dashboard`) now actually switches screens;
* `show(id)` also updates `aria-current` on the owning nav link —
  matched by prefix, not exact id, so a sub-screen like
  `screen-knowledge-taranjebin` or `screen-visibility-detail` still
  correctly highlights its parent's nav entry (Knowledge Objects / AI
  Visibility) instead of showing no active tab at all once you're inside
  a detail view;
* every link anywhere in the document that already pointed at a real
  screen id now works, not just the sidebar.

Two smaller, explicitly requested fixes alongside it:

* identity truncation raised from 12 to 20 characters (with a CSS
  `text-overflow: ellipsis` safety net added so it still can't overflow
  the sidebar box on an unusually wide character set, not just relying
  on the character count);
* the sidebar Log out link gets a real hover/focus state (tinted
  background, danger-coloured text, semibold) — it had none before.

A quick heuristic scan for the same missing-margin-top pattern that
caused the earlier Settings spacing bug found 11 more candidates
elsewhere in the file. Unlike the Settings case, most of these sit inside
grid/flex containers that may already handle spacing via their own `gap`
— patching all 11 blind, without visual confirmation, risks introducing
double-spacing rather than fixing anything. Left as a noted follow-up
rather than guessed at.

```
node visual-harness/build.js   -> rebuilt, 421 KB, 85 icons (unchanged)
node visual-harness/check.js   -> 33/33
python -m py_compile (275 files) -> 0 errors
```

`FINAL PHASE 13 STATUS: BLOCKED` — unchanged. Everything above is a UI
correction to the static harness.

---

## Addendum 9 — login/OTP made real, Products grounded in AMPS schema, Admin console added, two self-inflicted regressions caught and fixed

The owner flagged that a prior pass claimed more than it delivered
(Research/Products both wrongly highlighting "Dashboard" as active) and
asked for items 1, 2 and 3 from an earlier prioritization together, done
carefully. This addendum covers that combined pass.

### Root cause of the wrong-active-tab regression

`NAV` had both `research` and `products` pointing at `screen-dashboard`
as a placeholder. Addendum 8's hash-router (which correctly matches
`aria-current` to whichever nav link owns the active screen) then
correctly highlighted every link sharing that target — Dashboard,
Research, AND Products all lit up together, because they genuinely did
share a target. Not a router bug; a leftover placeholder the router
finally exposed. Fixed by removing `Research` from the top-level nav
entirely (it now lives as a per-row and per-detail-screen "Research
again" action inside Knowledge Objects, matching the owner's own
instruction that research-triggering belongs under Knowledge, not
alongside it) and giving `Products` its own real screen instead of an
alias.

### Login + 6-digit code: now actually interactive

Previously the two auth screens existed as markup only — a real Google
"G" mark (the standard four-colour SVG, not a fabricated one) and a
CSS-only animated "tech" backdrop (network of drifting dots — no real
GIF asset exists or is safe to invent, so this is the same visual idea
without pretending a file exists), a hollow unfilled icon, and correct
flex-centering that already addressed the "buttons off-centre on mobile"
complaint — but the actual behaviour (timer, lockout, verification) was
just described in a caption, not built. That's now a real state machine:

* submitting an email starts a genuine 5-minute countdown on the resend
  button, which re-enables and relabels itself "Resend code" at zero;
* "Continue with Google" skips the code step entirely, straight to the
  dashboard, per the owner's explicit instruction that Google differs
  from email here;
* the code boxes auto-advance, support backspace-to-previous, and accept
  a pasted 6-digit code in one action;
* three wrong attempts locks the form for 1 hour (inputs disabled, a
  live-region message shown); three more lock it for 24 hours with a
  message pointing at the contact link — matching the owner's exact
  numbers. The fixture's own help text states the one code that
  "succeeds" (123456), since there is no backend to check a real one
  against.
* the wording throughout uses "Log in" (not "Sign in"), per the owner's
  explicit correction that the two are different actions.

### Products: grounded in the real AMPS 5.0 schema, not invented

The owner's AMPS 5.0 project-memory export (`MASTER_SPEC.md` §26–29)
defines real `products` / `offers` / `product_evidence` /
`product_relations` tables and states explicitly that Product and Offer
must stay separate. The Products screen's fixture fields
(sku/brand/category/origin/ingredients/certifications for the product;
price/currency/availability/stock/condition/valid dates for the offer)
were built against those actual field lists rather than a guessed shape,
and a product's detail keeps its identity and its offer in visibly
separate sections. One real bug caught while reviewing this data: two
fixture rows used `'₺—'` (the Turkish lira sign) as a price placeholder
for IRR-priced products — wrong currency mark on Iranian products, fixed
to a plain em dash.

### Admin console: a genuinely separate surface, not a bolted-on button

Reached only from the account menu (labelled as such — a real backend
would gate the route itself, which a static fixture cannot demonstrate).
When an admin screen is active: the merchant sidebar nav is swapped for
a distinct two-item admin nav (Overview / Users, plus a way back), a
small "ADMIN" badge appears next to the wordmark, and the topbar gets a
coloured accent — all driven by a single `:has(.admin-screen.is-active)`
CSS rule rather than JavaScript toggling a class, so there's no state to
get out of sync with which screen is actually showing. Built:
* **Overview** — platform-wide stat cards, explicitly captioned as
  fixture data a real `DashboardHealth`/`DashboardBillingSummary` read
  model would back;
* **Users** — a real sortable table (organization, plan, wallet balance,
  status, last login) with block/unblock and a link into each user's own
  detail page;
* **User detail** — wallet balance and a transaction table (captioned
  with a pointer to `BILLING_ARCHITECTURE.md`'s append-only ledger
  design, since this is exactly the kind of admin action ADR-084 already
  governs), plus an activity-history table and block/delete actions.

### Two regressions this pass introduced, caught by actually running the checks

* `no hard-coded colour in harness markup` failed on `#4471` — not a
  colour at all, but the text "Job #4471" in the new activity table,
  which the checker's hex-colour pattern matched anyway. Fixed by
  rewording to "Job ID 4471" rather than weakening the check.
* `no declared font-size below 12px` failed on the new `.admin-badge`,
  which used a literal `10px`. Fixed by using the existing `--text-xs`
  token (12px, the project's own floor) instead of a new hardcoded value.

Both were caught by running `node visual-harness/check.js` after the
admin-console addition and reading its failure output — not by
inspection — and fixed at the specific line each one pointed to.

```
node visual-harness/build.js   -> rebuilt, 530 KB, 86 icons (+1: the
                                   'sidebar-toggle' icon from Addendum 6
                                   plus this pass's registry additions)
node visual-harness/check.js   -> 33/33 (two real failures appeared
                                   mid-pass and were fixed at their root
                                   cause, not suppressed or weakened)
python -m py_compile (275 files) -> 0 errors
```

`FINAL PHASE 13 STATUS: BLOCKED` — unchanged; everything in this
addendum is UI/UX work in the static harness, not new backend, database,
or real-authentication evidence. The billing/entitlement/admin-API
backend this console's screens describe remains exactly what
`docs/billing/BILLING_ARCHITECTURE.md` says it is: designed, not built.
