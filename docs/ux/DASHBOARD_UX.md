# Dashboard UX — Analytics, Demand and AI Access

**Phase:** 13
**Inherits:** `DESIGN_SYSTEM.md`, `ICON_SYSTEM.md`, `RTL_LTR_UX.md`,
`ACCESSIBILITY_UX.md`, `INFORMATION_ARCHITECTURE.md`. This document adds
screens; it redesigns none of those.

---

## 1. What the dashboard is for

Four questions, in the order a merchant actually asks them:

1. **Who is reading my site?** People or machines — and *which* machines.
2. **What is being read, and what is not?** With the numbers, sortable
   both ways.
3. **What did people and machines look for that I could not answer?**
4. **Am I connected, what is running, and what has been happening?**

Everything else is a detail view reachable from one of those four.

---

## 2. Screens added

| Screen | Harness id | Purpose |
|---|---|---|
| Analytics & demand | `#screen-analytics` | content ranking, geography, dwell, search demand |
| AI access | `#screen-access` | the policy table and the full agent registry |
| Connection & logs | `#screen-operations` | status strip, versions, adapter log, clear-log |

The WordPress admin equivalent is `admin/view-dashboard.php`, which
compresses all three into one page because the plugin is a control plane,
not the advanced environment (§69/§70).

---

## 3. The five rules this dashboard is built on

### 3.1 A null renders as "Not available", never as 0

`dwell_ms: null` means nobody measured it. `mean_dwell_ms: null` means
there were no samples. `geo_country: null` means no location was supplied.
Printing `0`, `0ms` or `—` for any of those converts an absence of
measurement into a measurement of absence, which is the single most
common way an analytics screen lies without anyone intending it to.

Implementation: `.not-available` in the harness, `.aiol-na` in the plugin.
Both render as text, not as a dash, so it survives a screenshot.

### 3.2 "AI crawler" and "AI answering" are never added together

Two columns, never a total. One is a copy being taken for a training
corpus; the other is a customer's question being answered right now. They
are the two facts the merchant is trying to tell apart, and a `bot_views`
column collapses the only distinction that changes what they do next.

The six-way split (`human · ai_crawler · ai_answer · agent · search ·
unknown`) is summed into `total_views` by the same function that writes
the components, so no column can disagree with the total.

### 3.3 Ascending is a first-class sort, not an afterthought

The default content view is **least seen first**. The merchant's question
is "where should I point content production next?", and the answer lives
at the bottom of a popularity list. A descending-only report silently
drops the more actionable half of the requirement.

Sorting is server-side through the canonical `apply_sort` (ADR-056). An
unknown sort field is a 422 naming the allowed values, never a silent
fallback — silently falling back means the order changes between pages and
the user never learns why.

`ip_address` and `user_agent` are **deliberately not sortable**. Sorting a
report by a visitor's IP is a lookup dressed as an ordering.

### 3.4 An undecided agent is shown as "Not decided", never "Free"

`AccessTier.UNSET` renders with the `unknown` badge variant and the word
*Not decided*. The dashboard also carries a standing count of agents in
that state, because an invisible default hardens into policy: a site can
end up in a training corpus it never agreed to, purely because nobody was
ever shown the choice.

### 3.5 Colour never carries state alone

Every status is icon + word + colour. This is an accessibility
requirement (§139, `ACCESSIBILITY_UX.md`) and also a practical one: a
screenshot pasted into a support thread has to be readable in greyscale
and by someone with a different colour vocabulary.

---

## 4. Icons

Seven icons were added to `frontend/icons/icon-paths.json` (67 → 74),
following the registry's single declared geometry — 24×24, `fill=none`,
`stroke=currentColor`, stroke-width 1.75, round caps and joins:

`analytics` · `geography` · `dwell` · `agent` · `shield` · `log` ·
`connection`

They were added **to the registry**, not drawn inline in the dashboard,
because the registry is the only place an icon path may be defined
(checkpoint M.1 §8). `visual-harness/check.js` re-ran 33/33 PASS after the
addition, including the "no stray `<svg>` outside the icon component" and
"no emoji as interface icon" checks.

Nothing new was needed for versions (`provenance-version`), sorting
(`action-sort`), cost (`cost`) or blocking (`lock`) — reusing an existing
icon beats adding a near-duplicate.

---

## 5. Geography, honestly

The geography table has a **"How we know"** column, and it is not
decoration. Values:

| Value | Meaning |
|---|---|
| `Edge header` | an upstream CDN resolved it and told us |
| `Adapter reported` | the adapter supplied it |
| *Not available* | nothing supplied a location |

There is no IP-geolocation database in this product and no lookup call.
A country column with no provenance is indistinguishable from a guess,
and a guessed country in a report is worse than an empty one because
nobody who spots it can correct it.

Coordinates are rounded to ~1 km. Enough to say "Tehran"; not enough to
say "this street".

---

## 6. The access screen's honest limit

The agent table carries a permanent callout stating that identification is
by User-Agent header, that a header is a claim rather than an identity,
that `Verified` is not implemented and therefore cannot appear, and that
**blocking by header stops honest agents and does not stop dishonest
ones.**

This is on the screen rather than in a footnote because a merchant who
believes "Forbidden" means "cannot" has been misled by their own admin
page — and they will believe it unless the page says otherwise.

---

## 7. The clear-log button

Clears the adapter's own log and its unsent telemetry buffer on this site.
It does **not** delete page views, agents or access decisions held in
Cloud Core.

That boundary is stated next to the button. A "clear log" control that
quietly erased the analytics record would be a destructive action wearing
a harmless label — and destructive actions in this product state their
consequences (§80, checkpoint UX-17).

---

## 8. RTL / LTR

No new rules; the existing ones applied.

* Persian content is selected by `lang`, not by `dir`, so a Persian title
  inside an English page gets the Persian face without flipping the page.
* Every identifier — path, agent signature, version string, IP prefix — is
  wrapped in `<bdi>` with a mono face, giving bidi a neutral run. A path
  like `/product/taranjabin-grade-a` beside a Persian title is exactly the
  case that looks correct in source and wrong on screen.
* Tables use logical properties and carry `data-label` on every cell, so
  the mobile card reflow does not lose a header.

**None of this is verified as painted.** See §10.

---

## 9. Responsive

Desktop: full table. Mobile: the same markup reflows to cards via
`data-label`, per `DESIGN_SYSTEM.md` — not a horizontally-scrolled
desktop table, and not a second markup tree.

The content table has 8 columns, which is the widest thing in the product
and the most likely to break. It is in the harness fixtures for exactly
that reason, alongside a long Persian title and a long path.

**Not verified as rendered.** See §10.

---

## 10. What is NOT verified

`node visual-harness/measure.js` exits 2: no browser, no network to
install one. Therefore, for every screen in this document:

* contrast as painted — **UNKNOWN**
* reflow and overflow at real widths — **UNKNOWN**
* focus-ring visibility — **UNKNOWN**
* keyboard traversal and screen-reader order — **UNKNOWN**
* Persian bidi with a real font — **UNKNOWN**

Static conformance is 33/33 PASS, and static conformance is not rendering.
Per §142 and the checkpoint's own §101, none of these converts to PASS.

---

## 11. Deliberately not built

* **Any cross-session visitor identifier.** Not needed for any question in
  §1, and its absence is what keeps this traffic analytics rather than
  people analytics.
* **Any psychological, receptiveness or purchase-readiness inference.**
  Checkpoint §76/§77 prohibits it; ADR-079 does not reopen it.
* **A price field on a `paid` policy.** Nothing in this product meters,
  invoices or collects; a number there would look like a working price.
* **A composite "AI visibility score."** ADR-064 forbids it and this
  dashboard does not smuggle one in as a summary card.
* **Automatic knowledge-gap creation from zero-result searches.** Surfaced
  as candidates only — see ADR-081.

## Session update — dashboard changes (version C)

Implemented against `visual-harness/index.html`.

### 1. Sidebar collapse — Claude-style, three states

    expanded                       normal
    collapsed                      hidden; main takes the width
    collapsed + pointer at edge    peeks, hides again on leave
    click the edge / the rail      pins open until clicked again

Peek and pin are driven by **different events** (pointer position vs click),
which is what stops a peek ever leaving the sidebar open and stops a click
being mistaken for a hover. The panel **floats** while peeking rather than
reflowing the grid — reflowing made the page jump every time the pointer
crossed the edge. A 180ms grace period covers the gap between the 14px edge
strip and the panel, without which the panel is unreachable.

The toggle moved from the topbar to the **top of the sidebar**, because it
belongs to the thing it controls.

**A conflicting older rule was removed, not left in place.** The previous
drag-to-peek CSS still reflowed the grid and fought the new rule; two CSS
blocks for one behaviour is how a UI starts depending on source order.

### 2. Hover submenu — Dashboard only

Exactly one `.nav__group--hover` exists, on Dashboard. Every other nav entry
is a plain link. Keyboard parity is explicit (ArrowRight/ArrowDown opens,
focusout closes), because hover alone leaves the submenu unreachable.

### 3. Research under Knowledge

Regenerating **prepends a new version** and marks the previous one
Superseded. Nothing is deleted: replacing in place would destroy the audit
trail the versioning exists to provide. Existing approved claims carry
forward as *candidates*, not approvals — the evidence behind them may have
changed.

### 4. Session indicator

`is-authenticated` gives the avatar a colour plus a heartbeat dot, exposed
through `window.aiolSetSession(bool, email)` so a real build drives it from
the session response. Animation is dropped under `prefers-reduced-motion`;
the colour signal stays.

### 5. Identifier clamp

20 characters, clamped in **both** CSS (`20ch`) and text, with the full
value preserved in `title` so copy-paste and screen readers agree with the
eye.

### 7/8. New screens and button grouping

`screen-traffic` and `screen-admin-billing` added. Traffic carries an
explicit banner that nothing on it is backed by a real table — `AIOL_Actors`
stores neither IP nor country nor dwell time (ADR-046), so those columns are
a schema change with retention consequences, not a display change.

Billing keeps **Available and Held as separate columns**: a pending charge
reduces what a tenant can spend without yet being revenue, and one number
would make both figures wrong.

`.btn-group` wraps, and stacks full-width below 640px.
