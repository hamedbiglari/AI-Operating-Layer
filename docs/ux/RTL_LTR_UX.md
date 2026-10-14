# RTL / LTR and language architecture

Status: **UX contract.**

## 1. Five languages, not one

These are separate and must never be assumed equal:

```
Application UI language        what the chrome is written in
Content language               what a Knowledge Object is written in
User language preference       what this person chose
Source language                what the original document is written in
Knowledge representation lang  what a claim is stored in
```

Default UI language is English. Persian is first-class content, not a
translation of the interface. The normal case in this product is an English
UI rendering Persian knowledge derived from an English scientific source —
all three at once, on one screen.

## 2. Direction is semantic, not mechanical

`dir` follows the UI language on the document, and is set per element for
content in another direction. Layout adapts through logical properties
(`padding-inline`, `margin-block`, `inset-inline-start`, `text-align: start`)
so there is no RTL stylesheet to maintain and nothing to keep in sync.
`check.js` fails on any physical side property in `components.css`.

Mirroring is opt-in per icon, never global. See `ICON_SYSTEM.md` §4.

## 3. Bidi isolation is mandatory for identifiers

A DOI, PMID, URL, SKU, UUID or hash placed inside Persian text will be
reordered by the bidi algorithm unless it is isolated. Every identifier is
wrapped in `<bdi class="identifier">`, which sets `unicode-bidi: isolate` and
`direction: ltr`.

This applies to: DOI, PMID, ISBN, URLs, SKUs, UUIDs, SHA-256 hashes, job ids,
MIME types, converter versions, file names, and scientific notation.

Today there is not one `<bdi>` in the WordPress plugin, and it renders
`object_id` UUIDs and endpoint URLs inside translated Persian sentences.
Recorded as UX-015.

## 4. Numbers

Prose numbers follow the locale. Numbers that must be unambiguous — a price,
an SKU, a DOI fragment, a version, a measurement in a scientific table — are
rendered Latin and isolated, via `.numeric-latin`. Counts in tables use
tabular numerals so columns align.

## 5. Typography

Persian gets a real face (Vazirmatn), more leading, and slightly larger
optical sizing at the same nominal size. The face is selected by `lang`, so a
Persian title inside an English page gets it. Persian text is never rendered
in a Latin fallback that has no Arabic-script coverage.

Long Persian titles wrap (`overflow-wrap: anywhere`); they are never
truncated with an ellipsis in a list, because a truncated Persian title often
loses the distinguishing word.

## 6. Plugin i18n status

The plugin loads its text domain and ships a POT with 145 strings plus an
`fa_IR` PO. 69 of those 145 are untranslated — about 48%. A Persian merchant
sees a half-English admin screen today. Recorded as UX-016.

The plugin also lacks a `Domain Path` header and does not call
`wp_style_add_data($handle, 'rtl', 'replace')`, so WordPress's own RTL
stylesheet mechanism is not wired up. The current CSS happens to use logical
properties and so mostly survives; that is fortunate rather than designed.
Recorded as UX-017.

## 7. What has not been verified

Everything above is a source-level property. None of it has been checked
against a rendered page with a real Persian font, because no browser is
available in this environment. Bidi behaviour in particular cannot be
asserted from source. See the checkpoint report, §95 gate.
