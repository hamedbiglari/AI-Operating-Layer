# UX prototype harness

A single self-contained page that renders the critical Sources → Knowledge →
Provenance flow using the canonical design tokens and icon registry.

It exists to satisfy checkpoint §80 (a coherent visual prototype of the
critical flow, with real representative content) and to give §95 something
to measure.

## Files

| File | What it is |
|---|---|
| `build.js` | Generates `index.html` by inlining `frontend/design-system/*.css` and rendering icons from `frontend/icons/icon-paths.json`. **Out of date:** `index.html` is now well ahead of it, so edit `index.html` directly until `build.js` is reconciled (see `docs/v5/V5_DASHBOARD_AUDIT.md`, "Build drift"). It refuses to overwrite without `--force-overwrite`. |
| `index.html` | The generated prototype. Opens from `file://`; no server, no network beyond the web font. |
| `check.js` | Static conformance checks. No browser needed. **Not** the visual gate. |
| `measure.js` | Rendered verification across screen × locale × theme × width. **This** is the visual gate. |
| `i18n-glossary.md` | The approved Persian terms and conventions. Every Persian string in `index.html` follows it. |

## Single file, for now

`index.html` is also the only product UI that exists: its live screens talk to
Cloud Core. Keeping everything in one file is a pragmatic choice, not a
permanent one. Revisit splitting it into a separate frontend when **either**
the file passes about 15,000 lines **or** a second frontend consumer needs the
same screens.

## Run

```bash
node visual-harness/build.js     # currently refuses to run: it would delete the v5 work (see above)
node visual-harness/check.js     # 33 source-level checks, exit 0/1
node visual-harness/measure.js   # exit 0 pass, 1 fail, 2 ENVIRONMENT BLOCKED
```

`measure.js` needs Chromium:

```bash
npm install puppeteer && npx puppeteer browsers install chrome
```

## What each layer can and cannot prove

`check.js` proves source-level rules: no emoji as icons, no icon outside the
registry, no icon-only control without an accessible name, no hard-coded
colour outside `tokens.css`, no declared font size under 12px, no table cell
that loses its header when the table reflows, logical properties only, and no
invented composite score in the markup.

It proves nothing about rendering. Contrast as painted, reflow at a given
width, absence of horizontal overflow, focus-ring visibility, and bidi
behaviour with a real Persian font all require a browser. In an offline
container `measure.js` exits 2 and the visual gate is **ENVIRONMENT
BLOCKED** — which is not a pass, and per §101 the checkpoint may not be
called GREEN while it stands.

## Fixtures

The prototype uses representative content, never lorem ipsum: a Persian
DOCX, a very long supplier-certificate filename, a paywalled paper carrying a
DOI and a PMID, a failed conversion, an archived URL source, and an exact
duplicate. Numbers are illustrative and the page says so.

## Screens covered

Dashboard · Sources & Documents · Add source · Processing · Source detail ·
Provenance (linear trace, one-claim-many-sources fan, and a per-link remove
control) · Knowledge · Knowledge gap (four gap types, each with the action
set that gap actually supports) · **AI Visibility** (two real, separate
backend systems — outbound platform probes and inbound traffic
classification — deliberately not merged into one score) · Edge states
(exact duplicate, possible version, archive-with-dependencies, a three-tier
permanent-delete dialog for a source, a knowledge-object retire dialog with
its unbuilt tier shown disabled rather than faked, failed conversion, empty,
loading).

## Delete is not one button

Checkpoint §22 forbids a single generic "Delete." The prototype gives every
destructive path its own dialog instead of overloading Archive:

- **Source** (`#screen-detail` → Delete, `#screen-states`): three named
  choices — archive / remove from active knowledge / permanently delete —
  each with its actual consequence spelled out, not just a dependency count.
  The permanent-delete option is the one place bold + `--danger` red text
  appears together, reserved for the option that truly cannot be undone
  (§77).
- **Claim–evidence link** (`#screen-provenance`, fan panel): a real,
  already-supported one-shot removal (`DELETE /claim-evidence/{link_id}`) —
  no tiers needed, because it has no cascade. Each is a labelled icon button
  that turns red on hover/focus.
- **Knowledge object** (`#screen-knowledge` → Archive / delete,
  `#screen-states`): archiving is real and offered; a second tier for
  permanently deleting knowledge *content* is shown **disabled**, with the
  reason stated in the dialog, because the underlying API cannot do it yet.
  A working-looking button that silently did nothing would violate §67 more
  than an honest disabled one does.

The controls at the top switch screen, language/direction, theme and viewport
width. "Show every screen" renders all of them at once for a single scroll
review or a full-page screenshot.
