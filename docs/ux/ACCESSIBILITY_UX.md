# Accessibility

Status: **UX contract.** A page that renders is not an accessible page.

## 1. Non-negotiables

- **Never colour alone.** Every status is icon + word + colour. This is why
  the badge component has no icon-less variant.
- **Focus is never removed.** `:focus-visible` gives a 2px ring with offset.
  `check.js` fails on `outline: none` anywhere in the design system.
- **Icon-only controls carry a name.** Enforced by the renderer, which
  cannot build one without a label, and by a static check.
- **12px floor.** No declared size below it; enforced statically.
- **WCAG AA contrast** for body text and 3:1 for large text and UI
  boundaries, in both themes. Measurable only by rendering — see §5.

## 2. Structure

One `<h1>` per screen; heading levels never skip. Landmarks: `<nav
aria-label>`, `<main>`, `<aside>`. Tables use `<caption>`, `<th scope>`, and
carry `data-label` on every cell so the stacked mobile layout keeps its
headers. Field hints are real elements tied by `aria-describedby`, never
placeholders — a placeholder disappears exactly when it is needed.

## 3. Announcements

Status messages use `role="status"`; errors use `role="alert"`. Regions that
are fetching use `aria-busy`. A stage change during processing is announced
once, politely, not on every poll.

## 4. Interaction

Full keyboard traversal of every flow, including the dialogs. Dialogs trap
focus, restore it on close, and close on Escape. Tabs follow the ARIA tabs
pattern with arrow-key movement. Interactive targets are at least 32px, and
40px where touch is expected. `prefers-reduced-motion` is honoured globally.
`forced-colors` mode keeps borders visible.

## 5. What is verified and what is not

Statically verified (`visual-harness/check.js`, 33 checks, all passing):
icons hidden or labelled, icon-only buttons named, focus ring present and
never removed, reduced motion and forced colours handled, table captions and
cell labels, 12px floor, no emoji, no colour-only signalling by construction.

**Not verified — requires a browser:** computed contrast ratios, focus ring
as painted, reflow at each breakpoint, absence of horizontal overflow,
screen-reader announcement order, and keyboard traversal in a real WordPress
admin with another plugin present.

`visual-harness/measure.js` measures the first five and exits 2 —
ENVIRONMENT BLOCKED — where no Chromium exists. The last two need a human in
a real install. None of them may be recorded as PASS on the strength of the
static checks.
