# Information Architecture

Status: **UX contract.** Binding on Phase 13+ unless superseded by an ADR.

## 1. The object model the UI must not blur

```
SOURCE            the conceptual origin  ("this 2025 review paper")
  └─ DOCUMENT     a piece of content taken from it
       └─ ARTIFACT  something derived: Markdown, tables, assets, OCR text, chunks
CLAIM             a statement, with a status of its own
EVIDENCE          a link between a claim and a place in a source
KNOWLEDGE OBJECT  the curated, published thing a person reads
PRODUCT           a normalized product knowledge object
OFFER             price, availability, seller — deliberately not on the Product
```

Four collapses are forbidden, because each one destroys a distinction the
backend already enforces:

| Never collapse | Because |
|---|---|
| Source → File | A DOI, a URL and a supplier's PDF are all sources; only one is a file. Re-uploading the same bytes must not create a second source. |
| Document → Knowledge | `Document.content` is the canonical Markdown. It is an artifact. A Knowledge Object is curated and published, and has its own status lifecycle. |
| Product → Offer | `Product` carries no price or stock column, on purpose. An interface that shows one card with both implies a single authority over both. |
| Claim → Evidence | A claim has `status` (draft…disputed); a link to evidence has `relation` (supports/contradicts/mixed/neutral). Merging them makes "three studies disagree" unrepresentable. |

## 2. Primary navigation

```
Dashboard
Knowledge
Research
Sources & Documents
Products
AI Visibility
Settings
```

Deferred, and **not** to be shown as empty shells: Customers, Orders,
Analytics, Rights, Integrations. A greyed-out nav item for an unimplemented
module is a fake feature (§67).

Both clients use this order. The WordPress plugin exposes a subset —
Dashboard, Knowledge, Sources & Documents, Products, AI Visibility,
Settings — never a different vocabulary or a different order.

## 3. Sources & Documents is a first-class area

It is not a file manager. Its job is to answer, for any source, the thirteen
questions in checkpoint §1 — what it is, where it came from, what stage it
is at, what was extracted, what it contributed, what depends on it, which
version was used, and whether a person needs to look at it.

Sub-routes:

```
/sources                       list, server-filtered and server-sorted
/sources/new                   source chooser
/sources/{id}                  detail shell
/sources/{id}/artifacts        original, Markdown, tables, assets, OCR
/sources/{id}/knowledge        what it contributed
/sources/{id}/claims
/sources/{id}/evidence
/sources/{id}/provenance       bidirectional trace
/sources/{id}/history          processing versions
/jobs/{id}                     asynchronous operation detail
```

## 4. One identity across clients

A source opened in WordPress and the same source opened in the Web App are
the same row in Cloud Core, with the same id, the same status and the same
processing history. There is no local status, no plugin-side copy, and no
second document store.

`wordpress_mappings` is adapter state, not truth (ADR-038). The UI must never
present it as the source of a status.

## 5. Caches may be stale, and must say so

Cloud Core is authoritative. The plugin caches. When a view renders from a
cache that could not be revalidated, it says so and offers a refresh — it
does not present stale data as current, and it does not show an encouraging
empty state during an outage (a rule the existing mappings screen already
follows and which generalises).
