# v5 dashboard browser audit (2026-10-22)

Scope: the two v5 cards in AI Center ("Knowledge transfer packages", "Models and their limits"), console and page
errors on all 52 `screen-*` ids, and a browser re-check of the 33 `check.js` rules. Defects are reported, not fixed.
Nothing under `visual-harness/` or `cloud-core/` was changed, and `visual-harness/build.js` was never run.

## 1. Setup (what was actually run)
* Browser: Playwright-core 1.64 (from the global `@playwright/cli`) driving the cached Chromium 1194,
  `141.0.7390.37`, headless. It launched and behaved normally. No download was needed. Revision 1247 (the one
  playwright-core 1.64 expects) was not installed, so small automation differences are possible.
* Dashboard served by `python -m http.server` on 127.0.0.1:8080 (a `file://` page cannot call the API: CORS is only
  enabled for the configured origin). API: Cloud Core on 127.0.0.1:8000, dev DB `aiol_v5c` at Alembic head 0046,
  `CORS_ALLOWED_ORIGINS=http://127.0.0.1:8080`.
* A throwaway organization (`audit-2026-10-22`, owner role) was registered and used. Data created in the dev DB: one
  provider, two models, one knowledge object, two KTP packages. No provider key, no "Test connection", no job.
* Static baseline: `node visual-harness/check.js` printed `33 passed, 0 failed` before and after.
* Raw JSON and screenshots stay in the gitignored `.devdb/audit-2026-10-22/`. This document holds no token or password.
  The token was scanned for in the DOM after connecting: absent from the HTML, inner text and all attributes; the
  token input is `type=password` and the connect form is hidden after connecting.

## 2. Console and page errors, all 52 screens
Every screen was visited by `location.hash` at 1280x900, once before connecting and once after connecting AI Center
(which also connects the other live screens). Listeners for `console` error/warning, `pageerror`, `requestfailed`
and HTTP status >= 400 were attached; a probe (deliberate `console.error`, thrown error, 404 fetch) confirmed that
they fire.
* Result: 0 console errors or warnings, 0 page errors, 0 failed requests, 0 HTTP errors, attributed to any screen in
  either pass (52 screens x 2 passes = 104 visits). All 52 screens became visible. No horizontal page overflow at 1280.
* One error exists outside the screen passes: `GET /favicon.ico` -> 404 at page load (seen in the later runs; the first
  script kept events only per screen visit, so it did not store load-time events). Harmless, but it is an error.
* The 52-screen pass only proves "loads without errors". It is not a control audit of those screens.

## 3. The two cards: control audit
Status vocabulary: COMPLETE_AND_VERIFIED = clicked in the browser and the result checked against the API.

| Control | Status | Evidence |
|---|---|---|
| Connect (URL + token) | COMPLETE_AND_VERIFIED | Body shown, requests 200 in the API log; token never in DOM text/attributes |
| Tab buttons "Providers & accounts", "Jobs & memory" | COMPLETE_AND_VERIFIED | Panes switch, aria-selected updates. The other four tabs (Routing, Agent network, Shared memory, Discovery) were not clicked: NOT_EXERCISED |
| Add provider (empty name) | COMPLETE_AND_VERIFIED | "Provider name is required." and no request |
| Add provider (name only) | COMPLETE_AND_VERIFIED | "Provider added."; row shown; `GET /ai-center/providers` lists it |
| Register model: no name | COMPLETE_AND_VERIFIED | "The model name is required." |
| Register model with all limits and a source | COMPLETE_AND_VERIFIED | API row: 200000 / 180000 / 8192 / 50 / 40000 / official_docs; row and form reset match |
| Register model with every limit blank | COMPLETE_AND_VERIFIED | API nulls; table shows "Unknown", "Unknown / Unknown", source "Unknown" (not 0) |
| Register / edit with 0, -5, 1.5 | COMPLETE_AND_VERIFIED (client side) | "Limits must be whole numbers of at least 1 (context window)."; API value unchanged. Server-side rejection not exercised through the UI |
| Model row "Edit limits" opens form | COMPLETE_AND_VERIFIED | Title "Edit limits - <model>", values and source pre-filled, focus moves to the first field |
| Edit form: Save limits | COMPLETE_AND_VERIFIED | 200000 -> 128000 and max input 180000 -> 120000: API and row match |
| Edit form: clearing a field | COMPLETE_AND_VERIFIED | Blank RPM -> API null, row shows "Unknown / 40000" |
| Edit form: Cancel | DEFECT (see D1) | Sets `hidden=true` and the API stays unchanged, but the form is never visually hidden |
| Edit form: Save with no model selected | NOT_EXERCISED | Form is always visible (D1), so this path is reachable; not tried |
| KTP status filter, all five values | COMPLETE_AND_VERIFIED | UI row counts and "1-2 of 2" / "1-1 of 1" match API totals (2, 0, 0, 1, 1); empty text "No package with this status." |
| KTP "Verdicts" on each row | COMPLETE_AND_VERIFIED | `nothing_accepted` row: "c1: rejected - UNKNOWN_ENTITY". `invalid` row: "Not used: MALFORMED: ..." (matches `invalid_reason` from the API) |
| KTP Previous / Next | PARTIALLY_VERIFIED | Both disabled with 2 rows (correct). Real paging was not exercised: it needs more than 25 rows |
| Reconciled / partly reconciled outcomes | NOT_EXERCISED | Seeding them needs a knowledge entity, a source and a document. Only `invalid` and `nothing_accepted` were seeded; the claim was rejected as UNKNOWN_ENTITY before the source check |

Not audited: every control on the other ~50 screens; the other four AI Center tabs; the older live screens
(Dashboard, AI executions); "Test connection", credential entry and job creation (no live calls by decision).

Not built or shown: the ADR-135 task dependency graph. It is BACKEND_ONLY: there is no dashboard card, and
`depends_on` is not in the job view. `waiting_on` appears only inside the raw handoff JSON after a real resource
switch, which needs a live job run.

## 4. Defects found (reported, not fixed)
* **D1. The "Edit limits" form is always visible.** `#aic-edit-model` has the `hidden` attribute (true) but computed
  `display: grid`, because `.aic-form { display: grid }` (index.html:2966) overrides the browser's `[hidden]` rule.
  The form shows at first load with empty fields, under "Register a model", and Cancel does not hide it.
  Screenshots: `models_empty_1280.png`, `models_light_390.png`.
* **D2. Rule 17 fails at runtime for AI Center tables.** The `row()` helper creates `td` cells without `data-label`:
  44 cells in 5 tbodies (`aic-providers` 4, `aic-accounts` 7, `aic-models` 16, `aic-ktp` 12, `aic-discovery` 5) of 987
  cells in the whole DOM. At 390px the stacked cards show values with an empty label column
  (computed `::before` content `""`; a table that sets `data-label` shows e.g. "Source"). Screenshots:
  `models_light_390.png`, `ktp_light_390.png`. `check.js` cannot see this because the cells are built by JS.
* **D3. Words break mid-word at 1280.** `.screen td { overflow-wrap: anywhere }` plus narrow columns gives
  "Unknow / n", "Verdic / ts" (the Verdicts button) and, in RTL, "documentatio / n". Screenshots:
  `models_seeded_1280.png`, `ktp_light_1280.png`, `models_fa_rtl_1280.png`.
* **D4. Persian font does not reach the UI text.** With `lang=fa` on `<html>` the root gets Vazirmatn first, but
  `body` and `.screen` keep "IBM Plex Sans" (computed), so card text in Persian mode uses Plex. Only elements that
  carry their own `lang="fa"` (the sample Persian spans) compute Vazirmatn. The web font itself does load from the
  Google Fonts stylesheet when such text is visible (`document.fonts.check` true on `screen-sources`; "unloaded"
  on screens with no Persian text). The card text itself is English in RTL mode, so no Persian was rendered in the card.
* **D5. Computed font size 10px.** `span.notif-count` ("3") computes 10px, although the source rule "no declared
  font-size below 12px" passes. Not in the two cards.
* **D6. Three tables in the rendered DOM have no `<caption>`** (63 tables, 3 without). Source check says 60/60.
  The three were not identified.
* **D7. KTP "From" column shows the raw `user:<uuid>`** for packages submitted by a person. Cosmetic.
* **Build drift.** `visual-harness/README.md` says `index.html` is generated by `build.js`, but `build.js` has no
  `aic-ktp` code. Running it would delete the v5 cards, so fixes for D1-D3 must go into `index.html` directly or
  after `build.js` is reconciled.

## 5. The 33 rules in a browser
"Source-only" means the rule is about source structure (a registry, a CSS file, tokens) that a rendered page cannot
confirm; the static PASS stands and no browser result is claimed. Totals: 16 browser PASS (rule 22 partial), 4 browser FAIL,
3 UNRESOLVED, 10 source-only. It is **not** 33/33 visually checked.

| # | Rule (as printed by `check.js`) | Static | Browser method | Browser result |
|---|---|---|---|---|
| 1 | icon registry has unique names | PASS | none | NOT_VISUALLY_CHECKABLE (source-only) |
| 2 | every icon has a path | PASS | none | NOT_VISUALLY_CHECKABLE (source-only) |
| 3 | every icon is categorised | PASS | none | NOT_VISUALLY_CHECKABLE (source-only) |
| 4 | one canonical geometry declared | PASS | none | NOT_VISUALLY_CHECKABLE (source-only) |
| 5 | no emoji | PASS | scanned all text and attribute text in the DOM | PASS |
| 6 | no Unicode box/arrow/tick glyphs | PASS | same scan | PASS |
| 7 | no raster image | PASS | 0 `img`, 0 computed `url()` backgrounds | PASS |
| 8 | no inline SVG outside the icon component | PASS | 589 `svg`, class check | PASS (0 offenders) |
| 9 | every icon hidden or labelled | PASS | 589 `svg` | PASS (0 unmarked) |
| 10 | icon-only buttons have an accessible name | PASS | 45 icon-only buttons; `aria-label`/`labelledby`/`title` (not the accessibility tree) | PASS (0 unnamed) |
| 11 | icon-only buttons exist | PASS | count | PASS (45) |
| 12 | focus ring never removed | PASS | Tab then focus; computed outline on 4 controls of the two cards | PASS (solid 2px, offset 2px, `:focus-visible` true) |
| 13 | focus-visible styling defined | PASS | same | PASS |
| 14 | reduced motion honoured | PASS | `reducedMotion: reduce`, max duration over all elements | PASS (400 ms transitions / 13000 ms animations -> 0.01 ms) |
| 15 | forced-colors handled | PASS | `forcedColors: active` (matches true), screenshot viewed | PASS (visual: borders on buttons, fields and badges); contrast not measured |
| 16 | data tables have a caption | PASS | `table` without `caption` | FAIL (3 of 63, D6) |
| 17 | every table cell carries `data-label` | PASS | `td` census and 390px `::before` | FAIL (44 cells, D2) |
| 18 | components.css has no hard-coded colour | PASS | none | NOT_VISUALLY_CHECKABLE (source-only) |
| 19 | no hard-coded colour in harness markup | PASS | none | NOT_VISUALLY_CHECKABLE (source-only) |
| 20 | harness chrome separated | PASS | none | NOT_VISUALLY_CHECKABLE (source-only) |
| 21 | every semantic status category has a token | PASS | only warning and danger badges rendered | NOT_VISUALLY_CHECKABLE (source-only) |
| 22 | dark theme defined for every status token | PASS | computed colours of the 2 KTP badges, light vs dark, screenshot viewed | PASS for warning and danger only; other categories not rendered |
| 23 | no declared font-size below 12px | PASS | min computed size over 90 visible text nodes | FAIL (10px, D5) |
| 24 | a real Persian face is first in the Persian stack | PASS | computed `font-family`, `document.fonts` | FAIL at UI-text level (D4); `<html>` and `lang="fa"` spans PASS |
| 25 | Persian is selected by lang, not by dir | PASS | root `lang=en dir=rtl` vs `lang=fa dir=ltr` | UNRESOLVED: body text is Plex in every case (D4), so the probe cannot tell |
| 26 | identifiers are bidi-isolated | PASS | computed `unicode-bidi` | PASS (`isolate`) |
| 27 | harness isolates identifiers with `<bdi>` | PASS | `bdi.identifier` count | PASS (47; the AI Center row `bdi` has no class but computes `isolate`) |
| 28 | components use logical properties | PASS | none | NOT_VISUALLY_CHECKABLE (source-only); RTL screenshots of both cards look mirrored correctly |
| 29 | only registry-marked icons are mirrored in RTL | PASS | `transform` of 585 `svg.icon` in `dir=rtl` | UNRESOLVED: 2 non-mirror icons have a transform, only 1 of 45 mirror icons does; not identified, may be intended |
| 30 | a distinct "not available" treatment exists | PASS | none | NOT_VISUALLY_CHECKABLE (source-only) |
| 31 | the harness actually uses it | PASS | `.not-available` count | PASS (22) |
| 32 | no invented composite score | PASS | pattern scan of all text | PASS |
| 33 | no fake progress percentage | PASS | `aria-valuenow`, inline `width:N%` | UNRESOLVED: 0 `aria-valuenow`, but 19 elements with inline `width:N%` were not inspected |

## 6. Screenshot index (`.devdb/audit-2026-10-22/`, all opened and looked at)
* Models: `models_empty_1280`, `models_seeded_1280` (the sticky dev bar overlaps the top; cosmetic), `models_light_1280`,
  `models_light_390`, `models_dark_1280`, `models_fa_rtl_1280`, `models_fa_rtl_390`, `models_forced_colors_1280`.
* KTP: `ktp_empty_1280`, `ktp_filtered_empty_1280`, `ktp_seeded_1280`, `ktp_detail_row1_1280` (UNKNOWN_ENTITY),
  `ktp_detail_row2_1280` (MALFORMED), `ktp_light_1280`, `ktp_light_390`, `ktp_dark_1280`, `ktp_fa_rtl_1280`,
  `ktp_fa_rtl_390`, `ktp_focus_ring_1280`, `ktp_forced_colors_1280`.
* The variant shots (`*_light_*`, `*_dark_*`, `*_fa_rtl_*`) were taken with the sticky dev bar made non-sticky by a
  runtime-only style injection (no file changed). `models_dark_1280`, `ktp_dark_1280`, `ktp_fa_rtl_*`,
  `models_fa_rtl_*`, `ktp_light_390`, `models_light_390` and the forced-colors KTP shot were viewed; `ktp_light_1280`,
  `models_light_1280`, `models_forced_colors_1280` and `ktp_focus_ring_1280` were generated but not individually viewed.
