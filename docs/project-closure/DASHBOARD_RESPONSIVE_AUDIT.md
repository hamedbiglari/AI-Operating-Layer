# Dashboard Responsive & Visual Audit (Phase 14 owner)

Method: automated audit of all 41 screens at 360 / 390 / 768 / 1024 / 1400 px in LTR and RTL
(`visual-harness/audit/`), plus screenshot review of mobile, tablet, desktop, RTL and dark.

## Defects found and fixed
| # | Defect (measured) | Fix |
|---|---|---|
| 1 | No global border-box: mobile card-table rows 34 px wider than their container (every table screen) | `*, *::before, *::after { box-sizing: border-box }` |
| 2 | Standalone inputs/selects outside `.field` unstyled, 19–21 px tall (Research entity picker, Chat box) | zero-specificity base control style, 40 px min height |
| 3 | Source search box 280 px tall and plan select 220 px tall on phones (width `flex-basis` applied to height in column layout) | `flex-basis: auto` + `min-inline-size: min(…, 100%)` |
| 4 | Badges escaping cards in key-value lists (Gap, AI visibility, Settings) up to 313 px at 360 px | badges in `.kv dd`/dialogs may wrap within the column |
| 5 | Dialog choice rows 10 px wider than the dialog at 360 px | `minmax(0, 1fr)` grid column |
| 6 | Long emails / Persian names escaping headings and breadcrumbs | `overflow-wrap: anywhere` |
| 7 | "Resend code" link 15 px tall; icon buttons shrinking to 20 px | 24 px minimum; 44 px on touch devices (`pointer: coarse`) |
| 8 | Justified callout text left wide word gaps on phones | start-aligned below 640 px |
| 9 | Links had no colour: browser default blue, **1.8:1 contrast in dark theme** | links use `--primary` (7.6 / 6.7:1) |
| 10 | Muted text 3.5:1 (light) / 4.47:1 (dark); info badge 4.47:1 | tokens adjusted → 5.3 / 5.5 / 5.4:1 (WCAG AA) |
| 11 | Live-panel spacing 48 px vs 16 px elsewhere; Connect buttons shorter than inputs | 24/16 px rhythm; 40 px button height |

## Result
Final audit: **0 remaining problem entries** across 41 screens × 5 widths × LTR and RTL; no page-level
horizontal overflow at any width; no flex-basis/height defects; all measured contrasts ≥ 4.5:1;
all 41 screens load without runtime errors; sidebar collapse still works.

## Known, accepted
- Checkboxes are 20 px; their table cell / label is the hit area (WCAG 2.2 2.5.8 spacing exception).
- The RTL preview shows English copy, so an English string in RTL puts sentence punctuation / a
  leading number on the other side ("min ago 15"). A per-block `unicode-bidi: plaintext` fix was
  tried and **reverted**: it left-aligned English blocks inside the RTL layout. Real Persian copy
  renders correctly.
- Pre-existing console warnings for SVG `width="var(--icon-size)"` attributes (rendering is correct).
