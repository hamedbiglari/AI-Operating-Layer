# Product UX architecture

Status: **UX contract.** Entry point for the other documents in this folder.

## 1. What the product is

A Knowledge Operating Layer: it turns sources into trusted, traceable,
continuously manageable knowledge, and connects that knowledge to discovery
and commerce.

It is not a file uploader with AI extraction. The difference is not
positioning, it is a set of interface obligations — every published statement
must be traceable to a document, every status must mean what the backend
means by it, and nothing may be presented with more certainty than the data
supports.

```
Source → Document management → Processing → Artifacts → Knowledge
       → Evidence / provenance → Discovery → Product / commerce
```

## 2. One product, two clients

```
                 CLOUD CORE  (source of truth)
                        │
        ┌───────────────┴───────────────┐
   Web application                WordPress plugin
        └───────────────┬───────────────┘
                   same API, same objects, same user model,
                   same status semantics, same source lifecycle
```

The plugin may not become a separate product. The Web App may not build a
competing source manager. Research may not create a third file store.
WordPress Media remains the local media mechanism; Cloud Source identity
remains canonical for anything the knowledge layer derives truth from.

The Web App does not exist yet. That is the single largest gap this
checkpoint found — see the report, UX-001.

## 3. Commerce is contextual

Informational intent gets an answer, its evidence, and relevant products.
Transactional intent gets the product, its price, its availability, its trust
record, and a route to the merchant. Commerce is never forced into an
informational interaction, and relevant products are never hidden when intent
is clearly commercial.

`Product ≠ Offer` at every surface.

## 4. Design for trust, not manipulation

No dark patterns, forced upsells, hidden pricing, manufactured scarcity or
urgency, fabricated popularity, fabricated trust, or confusing destructive
buttons.

Where the system models a person's decision context, the labels stay neutral
and describe need, not exploitability: `Information need`, `Evidence need`,
`Trust need`, `Commercial intent`, `Product interest`. Never "easy target",
"weak objection", "likely to buy". The backend's own vocabulary already
follows this rule (`NeedLevel`, `PurchaseIntent`, `ConsentStatus`,
`SignalState`), and the interface must not reintroduce what the data model
refused.

## 5. No fake features

If a capability is not implemented, there is no button for it, no chart of
it, no progress bar for it, and no empty section implying it is coming. A
deferred nav item is absent, not greyed out.

## 6. Glossary

One vocabulary across the Web App, the plugin, the API docs, help text and
error messages:

```
Source              the conceptual origin of information
Document            a piece of content taken from a source
Artifact            anything derived from a document
Knowledge Object    curated, published knowledge with its own lifecycle
Claim               a statement, with its own status
Evidence            a link from a claim to a location in a source
Research Project    an investigation; Research Task, one unit of its work
Knowledge Gap       a named absence, with a recommended action
Product             a normalized product knowledge object
Offer               price, availability, seller
Trust Record        a verified assertion backed by an Evidence row
Visibility Observation  one probe of one platform, with its collection method
Job                 one asynchronous operation with a visible lifecycle
Processing Version  one pass of the ingestion pipeline over a source
Provenance          the recorded path from a statement to its origin
```

## 7. Documents in this folder

| File | Covers |
|---|---|
| `INFORMATION_ARCHITECTURE.md` | object model, navigation, routes, identity |
| `SOURCE_DOCUMENT_UX.md` | lifecycle, upload, duplicates, archive, reprocess |
| `KNOWLEDGE_PROVENANCE_UX.md` | bidirectional trace, conflicts, freshness |
| `DESIGN_SYSTEM.md` | tokens, typography, components, states |
| `ICON_SYSTEM.md` | registry, geometry, accessibility, RTL |
| `RTL_LTR_UX.md` | language architecture, bidi, plugin i18n |
| `ACCESSIBILITY_UX.md` | contracts, and what is and is not verified |

Implementation: `frontend/design-system/`, `frontend/icons/`,
`visual-harness/`. Findings and gates:
`PRODUCT_UX_ARCHITECTURE_CHECKPOINT_REPORT.md` at the repository root.
