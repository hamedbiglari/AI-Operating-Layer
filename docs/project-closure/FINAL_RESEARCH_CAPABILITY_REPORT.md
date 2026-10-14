# FINAL RESEARCH CAPABILITY REPORT (2026-09-29, migrations 0001→0032)

What the research engine can and cannot do today. Every "can" below is covered by an executed test.

## It can
- **Ask in many ways.** 23 keyword kinds (primary, scientific name, synonyms, common names, compounds,
  mechanisms, clinical outcomes, safety, preparation, dose, language variants, related entities…) and five
  query modes: one keyword, several (OR), exact phrase, AND/OR/NOT with parentheses, and an agent-expanded
  query. A **query set** saves the whole thing so it can be re-run and compared over time.
- **Search several providers at once.** Crossref, PubMed (E-utilities) and Europe PMC, each on its own fixed
  official host. One provider failing never removes another's results; all failing is reported as a failed
  task, not as an empty answer.
- **Deduplicate honestly.** DOI, then PMID, then canonical title. A repeated search reports 0 new sources.
- **Say what it actually holds.** Eleven access states, including title only, landing page only, paywalled,
  registration required and access blocked. A database rule forbids claiming full text without an origin.
- **Acquire full text two ways.** Fetch an open-access copy through the SSRF-guarded fetcher, or accept an
  article the user obtained legally and uploaded. In both cases the claim is made only if a real document
  parsed; anything shorter leaves the source untouched and says why.
- **Separate the routes.** Ten evidence routes. A study of a compound, a related species, a formulation or a
  combination is evidence about *that*, never about the subject — enforced by a database CHECK, not by
  convention. The labelled graph shows subject → contains → compound → studied_in → study → reports_outcome,
  and marks a `contains` edge as assumed until a reviewed source documents it.
- **Keep the human in the loop.** Discovery creates sources only. Candidates wait in `pending_review`, and
  approval requires stating what the study actually tested. The research engine never edits a knowledge object.
- **Count independent findings.** Reviews, reanalyses, preprints and duplicate records of one study are
  grouped transitively, so twenty reviews of three trials report three independent findings. A citation alone
  does not group.
- **Stop for a stated reason.** Every round is recorded (seen / new / duplicates / providers ok / failed) and
  saturation reports one of eight reasons. All providers being down is explicitly *not* saturation.
- **Show disagreement instead of resolving it.** Conflicts are objects with a side-by-side comparison and five
  states; a resolution requires a written reason.
- **Track what is still missing.** An evidence-completion task names the route and directness that would
  satisfy it, and can only be closed by evidence that actually matches — or by a written dead-end reason.
- **Trace everything.** keyword → project → task → query → provider → source → document → evidence → claim →
  knowledge object, with the chain reported as incomplete until it really reaches a claim.

## It cannot (stated plainly)
- **Reach the live scholarly hosts in this sandbox.** The allow-list rejects them; provider behaviour is proven
  against documented-format fixtures. This is the one thing standing between CONDITIONAL PASS and PASS.
- **Search ClinicalTrials.gov, Scopus, Web of Science, or the web.** The provider interface exists; these
  adapters do not. A run reports `web: not_configured` rather than pretending.
- **Judge science.** It records study design, population, sample size, directness and strength as found; it
  does not compute a quality score, and it never converts uncertain evidence into advice.
- **Guess dependencies between sources.** Someone has to record them.
- **Read a paywalled article.** It shows every legitimate way to obtain it and waits for the person.

## Acceptance
`tests/test_acceptance_taranjabin.py` runs the whole chain on one real example — keyword cluster, discovery,
dedup, abstract-only and title-only states, open-access discovery, user upload, parsing, review, direct vs
indirect, conflict, dependency, gap, completion task, Find More, iteration, stopping condition and the
person-made knowledge update — through the production code path, in one test.
