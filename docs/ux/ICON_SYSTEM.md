# Icon system

Status: **UX contract.** Registry:
`frontend/icons/icon-paths.json`. Renderers: `icon.js` (Web App),
`class-aiol-icon.php` (WordPress plugin).

## 1. One registry, two renderers

The PHP renderer reads the same JSON file the JavaScript renderer imports. It
does not keep a copy. That is what makes "one icon system across both
clients" structural rather than a promise: the plugin cannot drift without
someone editing the shared registry, and the Web App renderer throws on a
name the registry does not contain.

67 icons in seven categories: `nav`, `source-type`, `processing`, `status`,
`provenance`, `action`, `misc`.

## 2. Geometry

One geometry for everything, declared once in the registry:

```
viewBox      0 0 24 24
fill         none
stroke       currentColor
strokeWidth  1.75   (overridable per-surface via --icon-stroke)
linecap      round
linejoin     round
```

`currentColor` throughout, so an icon inherits its meaning's colour and works
in both themes without a second set of files. Default size is 16px from
`--icon-size`; 20px and 24px variants exist for headers and empty states.
Icons sit on the text baseline (`vertical-align: -0.15em`).

## 3. Accessibility

Two states, no third:

- **Decorative** (the default): `aria-hidden="true"`, `focusable="false"`.
  Correct whenever the icon sits beside its own label, which is the normal
  case here because colour and icon may never carry state alone.
- **Meaningful**: `role="img"` with a `<title>`, requires a `label`.

`iconButton()` / `AIOL_Icon::button()` cannot be constructed without a label.
An icon-only control without an accessible name is a review failure, not a
style preference. `check.js` fails the build on either violation.

## 4. RTL

Only icons marked `"mirror": true` in the registry flip, and they flip via
one CSS rule (`[dir="rtl"] .icon--mirror { transform: scaleX(-1) }`), not via
a second set of paths.

Mirrored: search, back, external link, edit, copy, convert, trace, duplicate,
disclosure chevrons. Not mirrored: clock, shield, flask, database, check,
warning triangle, gear, archive box. Mechanically mirroring everything is the
RTL failure this rule exists to prevent — a clock does not run backwards in
Persian.

## 5. Banned

No emoji. No Unicode box-drawing, arrow or tick glyphs standing in for icons.
No raster icons. No second icon library. No `<svg>` markup inlined at a call
site. All five are checked statically.

The one remaining exception is the WordPress admin **menu** glyph
(`dashicons-networking`), which WordPress requires as a dashicon string for
the top-level menu item. It is the only non-registry glyph in the product and
is recorded as UX-018.

## 6. Semantic mapping lives in the renderer

The mapping from a domain value to an icon is defined once, in the renderer,
keyed by literal `cloud-core` enum values — `extractionStatusIcon`,
`conversionStatusIcon`, `jobStatusIcon`, `sourceTypeIcon`,
`AIOL_Icon::for_sync_status`. Screens do not write `switch` statements over
status strings.

An unrecognised value resolves to `status-unknown` and is logged. It never
resolves to a cheerful default, and it is never silently swallowed.

## 7. Adding an icon

Add it to `icon-paths.json` with a category and, if it is directional, the
`mirror` flag. Rebuild the harness. `check.js` verifies uniqueness, that
every icon has a path and a category, and that the harness contains no SVG
outside the component.
