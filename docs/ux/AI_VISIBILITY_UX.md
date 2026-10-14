# AI Visibility UX

Two real backend systems, deliberately not merged into one screen with one
number. Merging them would manufacture a "visibility score" the moment they
touch — and `VisibilitySummary` (`cloud-core/app/schemas/visibility.py`)
already has an explicit rule against that: "contains no score, no percentage
and no ranking" (ADR-064). This document, and `#screen-visibility` in the
prototype, keep the same separation.

## 1. Two different questions

| | "How does AI answer about you?" | "Who is visiting your site?" |
|---|---|---|
| Backend | `VisibilityTest` (Cloud Core, Phase 10) | `AIOL_Actors` (WordPress plugin, ADR-046) |
| Direction | Outbound — the system asks a platform a prompt and records what came back | Inbound — a request hits the site and gets classified |
| Unit | One observation of one prompt on one platform at one moment | One HTTP request, classified by its User-Agent |
| Honesty mechanism | Tri-state `SignalPresence` (`PRESENT` / `ABSENT` / `NOT_CHECKED`) on five signals — never boolean, because a `false` cannot distinguish "checked, absent" from "never checked" (ADR-061) | Confidence level (`Detected` / `Probable` / `Verified` — the last not implemented) — because a User-Agent header is a claim, not a proof |

A merchant asking "am I visible to AI" is really asking both, and they have
different answers: a brand can be well-cited when ChatGPT is asked about it
directly, and simultaneously receive heavy indexing traffic from a crawler
that has nothing to do with any specific answer. Collapsing them into one
"AI Visibility Score" would erase that distinction — which is exactly the
kind of unexplained composite score §59 forbids.

## 2. What `VisibilityTest` does NOT track, on purpose

Section 31 of the master spec names seven things that must stay distinct:
Mention, Citation, Recommendation, Product Display, URL, **Click**,
**Purchase**. The model only has columns for the first five. The model's own
docstring states why: a click happens inside the platform's interface, which
this system cannot observe; a purchase happens on the merchant's site and
belongs to commerce/analytics data, not to a visibility observation.
Inventing either would be a guess wearing the shape of a measurement — the
UI must not add a "Clicks" or "Conversions" column that the backend cannot
honestly fill.

## 3. What `AIOL_Actors` does NOT track, on purpose

This is the more important discipline for the UI to inherit, because the
person who originally asked for this feature asked for more than the plugin
delivers — and the gap is a deliberate privacy narrowing, not an oversight.
The original ask included geographic origin, time of day, and dwell time.
The shipped class docstring is explicit about why those are absent: *"The
legacy log stored IP address and full request URI. This one stores neither:
no IP, no query string, path only, User-Agent truncated. An adapter log is
not an analytics product, and storing less is the only reliable way not to
leak more."* Human visitors are not logged at all — only automated clients.

The screen states this plainly rather than silently matching a narrower
feature set to a broader original request. A merchant who wanted geography
should be told it was a choice, not left to wonder if the feature is
half-built.

## 4. Confidence, not certainty

`AIOL_Actors::classify()` returns one of three confidence levels for every
row, and the UI renders the level next to every entry, never suppressing it:

- **Detected** — a known signature matched (`GPTBot`, `ClaudeBot`,
  `Googlebot`, etc.). Still self-reported; anyone can send any User-Agent
  string.
- **Probable** — a weaker heuristic matched (contains "crawler", "bot" as a
  whole word, etc.).
- **Verified** — would require reverse-DNS or published IP-range
  confirmation. Not implemented. The UI must never show a row as Verified
  today; doing so would claim proof the system does not have.

## 5. Demand signal — a related, separate system, not yet connected

`Query` (`cloud-core/app/models/query.py`) is Phase 6's answer to a
different but related ask from the original design conversation: when an AI
platform or a user searches for something the site does not yet answer,
that unmet demand should become a trackable, prioritizable signal
(`QueryStatus`: `DISCOVERED → CLASSIFIED → ARCHIVED`; `QueryPriority`:
`LOW/MEDIUM/HIGH/CRITICAL`; `QuerySource` includes `AI_TEST` and `SERP`, so
a `VisibilityTest` observation or a search-console import can seed one).

What does not exist yet: any link from a `Query` to a `KnowledgeGap`. A
discovered, high-priority, unanswered query does not automatically become a
gap a person can act on from `#screen-gap` — the two systems are adjacent,
not connected. Building that link is Phase 13 work (the original design
conversation's own roadmap maps "Analytics" and "Demand Intelligence" to
Phase 13, immediately following this checkpoint — see
`PRODUCT_UX_ARCHITECTURE_CHECKPOINT_REPORT.md` §P), not something to fake
in this prototype.

## 6. What this UX explicitly does not do

The original design conversation also asked, at points, for detecting a
visitor's "psychological state" from their query phrasing in order to
target them toward a purchase, and for remembering an individual across
sessions to re-offer a product ("hey, I recommended this to you before").
Neither belongs in this document or in any screen built against it. Both
sit squarely inside what checkpoint §76–77 already rules out: manipulative
profiling ("Easy target", "Likely to buy" labels), and the UI must never
grow toward that even where the backend could technically support tracking
an identifier across visits. Recommending a relevant product based on
demonstrated interest is in scope (§30–32); inferring and acting on
someone's psychological susceptibility to persuasion is not, regardless of
whether it would increase conversion.
