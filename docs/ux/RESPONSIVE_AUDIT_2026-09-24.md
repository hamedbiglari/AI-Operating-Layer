# Dashboard Responsive Audit — 2026-09-24

Scope: all 41 screens of `visual-harness/index.html`, widths 360 / 390 / 768 / 1024 / 1400 px,
LTR and RTL (Persian), light and dark. Tools: `visual-harness/responsive-audit.js` (new: page
overflow, elements escaping their card, targets < 24 px, flex-basis-as-height) and the project's
own `visual-harness/measure.js` (contrast, text size, targets < 32 px, clipping).

## Defects found and fixed (all CSS, one block at the end of <head>)
| # | Defect | Where | Fix |
|---|---|---|---|
| 1 | No global border-box: 100 %-wide padded elements overflowed (mobile card rows 34 px wider than their wrapper) | all card tables | `*, *::before, *::after { box-sizing: border-box }` |
| 2 | Unstyled standalone inputs/selects, 19–21 px tall | Research entity picker, Chat box, others | zero-specificity base style, 40 px min height |
| 3 | Width-intended flex-basis became height in column layouts: search box 280 px tall, plan select 220 px tall | Sources, Admin user ×5 | basis auto + min width |
| 4 | Non-wrapping badges escaped cards by up to 313 px | Gap, AI Visibility, Settings | badges inside key/value lists may wrap |
| 5 | Dialog choices: text column 39 px wide, action overlapping title | Edge states (delete dialog) | action moves under the text on narrow containers; titles on their own line |
| 6 | Long emails / Persian names escaping headings and breadcrumbs | Admin user pages | `overflow-wrap: anywhere` |
| 7 | Card-buttons with browser-default black text — invisible in dark mode | Add source | `button.card { color: inherit }` |
| 8 | Sortable header buttons 32 px wider than their cell (`all: unset` reset box-sizing) | every sortable table | border-box restored |
| 9 | Identifiers at 11.7 px | several | ≥ 12 px |
| 10 | Targets under 24/32 px (resend link 15 px, icon button 20 px, search input 24 px) | OTP, Sources | minimum sizes; 44 px on touch devices |
| 11 | English strings mis-ordered in RTL ("min ago 15", period on the wrong side) | cards in fa mode | `unicode-bidi: plaintext` per paragraph (W3C dir=auto practice); short values keep the RTL edge |
| 12 | Live panel spacing uneven with the page header | wired screens | margin aligned to card gap |

## Result
- `responsive-audit.js`: **0** page overflows, **0** elements escaping their card, **0** targets
  under 24 px — LTR and RTL, 41 screens × 5 widths.
- `measure.js` (128 combinations): contrast failures 120 → **0**, text < 12 px 24 → **0**,
  targets < 32 px 16 → **0**, overflow **0**. It still reports **VISUAL GATE: FAIL** because its
  "clipped" counter (36) counts intentional patterns: screen-reader-only text (`.visually-hidden`),
  the table header hidden in mobile card mode, and horizontal scroll containers (`.table-wrap`,
  `.tabs`). The gate was not modified.
- `check.js`: 33/33.
- Known exception: checkboxes are 20 px; the surrounding cell/label is the hit area (WCAG 2.2
  2.5.8 spacing exception).

## Addendum — dialogs and profile & verification (same day)
| # | Change | Verification |
|---|---|---|
| 13 | Collapse button chevron restored: the chevron SVG carries the registry `icon` class (required by `check.js`), which the rule hiding the button's screen-reader icon (`#sidebar-collapse .icon`) also matched, making it 1×1 px and transparent. The hide/rotate rules now exclude `.sidebar-collapse-chevrons` | measured 10×10 px, visible, screenshot |
| 14 | Profile-photo dialog: close (×) button in the top end corner; Done receives initial focus | × closes the dialog (browser) |
| 15 | Save confirmation before any edit is applied: icon, "Save your changes?", a summary of every changed field (old value struck through → new value), "Keep editing" / "Yes, save changes", × close; nothing to save → Save disabled with an explanation | no-change, cancel, confirm, × paths (browser) |
| 16 | Success popup redesigned (icon, "All set!", message, Done, ×); used by every save/send action | browser |
| 17 | Profile & verification: account-completion and identity data (personal, contact, address, business, identity document + uploads) shown as a card with a completeness count ("13 of 18 done" — a measured count of required details, with a decorative bar; no ARIA progress value, per the harness honesty rule) and status badges on the user's Settings page and on every admin user page; editable by the user ("Edit profile" / "Complete my profile") and by the super admin (user edit panel), the super admin additionally recording the verification decision (status, phone verified, note to user) | edit → confirm → saved → card and count update (13 → 17 of 18); admin sets "Verified" → badge updates |

Sample data only: the backend has no profile/KYC fields yet (these are UI requirements; the
storage and review workflow would be backend work under the existing owner).

Re-run after the changes: responsive audit 0 page overflow / 0 escapes / 0 small targets
(LTR and RTL, 41 screens × 5 widths); `check.js` 33/33 (new dialog icons use the registry class; no tick glyphs); `measure.js` contrast 0, text < 12 px 0,
targets < 32 px 0 (clipped counter unchanged: intentional patterns). The only failing network
request is Google Fonts, blocked by this sandbox's network (pre-existing).
