# Design system

Status: **UX contract.** Implementation lives in
`frontend/design-system/` and is exercised by `visual-harness/`.

## 1. What it is for

The interface should read as trustworthy infrastructure. Concretely that
means: restrained colour, strong hierarchy, generous spacing, real
typography, no decorative gradients, no glassmorphism, no hero sections, and
no information presented with more confidence than the data behind it
carries.

Information density is welcome. Visual noise is not. The two are different:
a table of 248 sources with tabular numerals and quiet borders is dense; the
same table with a coloured pill on every cell is noisy.

## 2. Tokens

`frontend/design-system/tokens.css` is the only file permitted to contain a
colour literal. Components consume tokens. `visual-harness/check.js` fails
the build if a hex value appears in `components.css` or in markup.

Semantic colour categories, all of which have light and dark values:

```
primary  success  warning  danger  info  processing  archived  unknown
```

`processing` and `archived` are separate categories rather than shades of
`info` and `neutral`, because a list of 248 sources has to separate "a job is
running" from "here is a note" at a glance.

`unknown` is muted, never red. This is the visual expression of the
unknown-is-not-negative rule.

Spacing is a 4px scale. Radius has three tiers and they are assigned by what
is wrapped — pills and inputs at 4px, cards and dialogs at 8px — rather than
one radius applied to everything. Elevation has two levels, and shadow is
never used to separate things a border can separate.

## 3. Typography

Three families, each with a job:

| Token | Family | Used for |
|---|---|---|
| `--font-ui` | IBM Plex Sans | Latin interface text |
| `--font-fa` | Vazirmatn | Persian and Arabic-script content |
| `--font-mono` | IBM Plex Mono | identifiers only — DOI, PMID, SKU, UUID, SHA-256 |

Monospace is informational here, not stylistic: it makes character-level
differences in an identifier visible and gives the bidi algorithm a neutral
run to isolate. It is not used for small labels, which is a different habit
with a different motive.

The scale has six steps and deliberate gaps. 12px is the floor; nothing
smaller is allowed to carry meaning, and `check.js` enforces it.

Persian is selected by `lang`, not by `dir`, because a Persian title inside
an English page still needs the Persian face. Arabic-script text gets more
leading and a slightly larger optical size at the same nominal size.

## 4. Component inventory

```
AppShell   Sidebar   TopBar   Breadcrumbs   PageHeader
Button     IconButton   Tooltip   Badge   StatusBadge
Card       StatCard   DataTable   MobileList   Tabs
Dropdown   FilterPanel   SearchInput   Dialog   Drawer
Toast      Progress   Timeline   EmptyState   ErrorState   Skeleton
SourceTypeIcon   ProcessingStage   ProvenanceTrail
KnowledgeLink    EvidenceBadge     CoverageIndicator
```

`ConfidenceIndicator` from the checkpoint's list is deliberately renamed
`CoverageIndicator`. There is no confidence number in this system to
indicate; what there is, is how much of a claim's support is verified,
accessible and direct. A component named for a number that does not exist
invites someone to invent one.

Two components may not exist in two implementations. If a second card-like
thing is needed, it is a variant of `Card`, not a new component that happens
to look similar.

## 5. State coverage

Every screen defines: loading, empty, populated, partial, processing,
failed, unauthorized, forbidden, not found, stale, unavailable — for each
state that can actually occur on it. "Partial" and "stale" are the two most
often skipped and the two most often encountered in a system with a cache and
an async worker.

Loading uses skeletons. Processing uses a stage, not a percentage.

## 6. Errors

An error names the stage, the reason, whether anything changed, whether
retrying is safe, and what to do next. Errors do not apologise and are never
vague. HTTP status maps to distinct user-facing outcomes — 401, 403, 404,
409, 422, 429, 500 and 503 are seven different situations and are never
rendered as "Something went wrong". Technical detail stays available behind a
disclosure; stack traces stay out of the primary UI.

## 7. Empty states

An empty state explains why it is empty and offers the single next action. An
empty state during an outage is a lie; when a fetch failed, the screen shows
the error state instead.

## 8. Motion

Motion answers an action — a dialog opening, a row expanding, a value
changing. There is no entrance choreography and no hover animation on every
card. `prefers-reduced-motion` is honoured globally in `tokens.css`.

## 9. Responsive

Desktop gets the table. Mobile gets cards: the table reflows into stacked
rows and each cell keeps its header through `data-label`. Nothing scrolls
sideways to stay legible. `check.js` fails any cell missing its label.
