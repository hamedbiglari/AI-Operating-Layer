# PILOT TEST RUNBOOK — live checks that complete the pilot

Run on an environment with normal outbound HTTPS. Record every result; do not mark PASS on fixtures.

## 0. Setup
1. `cd cloud-core && cp .env.example .env`; set `DATABASE_URL`, `REDIS_URL`, `SECRET_KEY`,
   `AI_CREDENTIAL_KEY`, `CORS_ALLOWED_ORIGINS`, and `RESEARCH_CONTACT_EMAIL=<your address>`
   (Crossref/NCBI etiquette). Optional: `NCBI_API_KEY` (raises the NCBI rate limit).
2. `alembic upgrade head` → expect `0026 (head)`; `bash scripts/verify_migration_cycle.sh` → "verified".
3. `pytest -q` → expect 1096 passed, 0 failed, 0 skipped.
4. Plugin: `bash wordpress-plugin/tests/run.sh` → "ALL PHP CHECKS PASSED".
5. Network check: `curl -s -o /dev/null -w '%{http_code}' 'https://api.crossref.org/works?rows=1'` → 200
   (same for `eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=mannitol&retmode=json` and
   `www.ebi.ac.uk/europepmc/webservices/rest/search?query=mannitol&format=json`).

## 1. Live federated search (Dashboard › Research › Research engine)
| Step | Expected | Record |
|---|---|---|
| Create KO "Taranjabin"; keywords: Taranjabin (primary), Persian manna (synonym), Alhagi maurorum (scientific name), mannitol (compound), laxative (clinical outcome) | saved with those kinds | |
| Search, mode "One keyword", keyword Taranjabin | crossref / pubmed / europepmc = ok, web = not configured; sources listed | provider result counts |
| Repeat the same search | "0 new" sources (dedup) | |
| Open a source | message "found … not reviewed"; content access = Abstract only or Metadata only (never Full text); DOI / PubMed / Europe PMC / library links open the right record | |
| Mode "AND / OR", `("Persian manna" OR Taranjabin) AND laxative` | runs; `mannitol;` style input rejected | |
| Temporarily block one host (e.g. hosts file) and search | that provider "failed" with its error; the others still return results | |

## 2. Compound question
| Step | Expected |
|---|---|
| Research question: subject Taranjabin, compound Mannitol, outcome laxative, population human | four route searches (direct subject, compound human, mechanism, co-occurrence) |
| "Extract candidates" | candidates only for sources whose abstract is held; metadata-only sources counted as "no readable text" |
| Approve a Mannitol trial with "What did the study test?" = Mannitol | status verified, **indirect**, route compound human; map: direct evidence for Taranjabin **absent**, clinical evidence for Taranjabin **indirect** |
| Approve a study that tested Taranjabin itself | **direct**; map: clinical evidence **direct** |
| Knowledge gap › Find more | a new question runs; nothing is resolved automatically |
| Check the KO | version / text unchanged by any research step |

## 3. Traceability
`GET /api/v1/research/keywords/{keyword_id}/chain` → project, task, query, provider, source; after a reviewed
candidate is linked to a claim (`POST /api/v1/claim-evidence`) → `complete_to_claim: true`.

## 4. Commerce loop (E2E-K2C-001)
Follow `docs/project-closure/CORE_KNOWLEDGE_TO_PURCHASE_E2E.md` (scripts in `docs/project-closure/e2e/`):
offer sync (price + stock) → recommendation → `/ai/ask` merchant_url → product page → cart → unpaid order.

## 5. External items still open
Commercial AI provider (`ANTHROPIC_API_KEY` + pricing), Google OAuth for GSC/GA4, SMTP for login codes,
Walrus endpoint, docker-compose runtime, MASTER_SPEC §55 pilot with the owner's real products and content,
official-source verification of the AI catalogue entries.

## PASS criterion
All tables above recorded with live results, sections 1–4 as expected, and the backend/plugin suites green on
the pilot environment. Only then change the verdict in FINAL_COMPLETION_REPORT.md from CONDITIONAL PASS to PASS.


## 6. Wallet and payments (after a real provider is configured)
| Step | Expected |
|---|---|
| Payment screen before configuration | "BLOCKED EXTERNAL DEPENDENCY", Add funds disabled |
| Configure the provider + webhook secret; add funds | provider checkout → webhook → "payment captured" in the ledger, once |
| Resend the same provider event (provider dashboard "resend") | acknowledged, **no second credit** |
| Reserve more than the available balance (API) | 402 |
| Reserve, settle a smaller amount | hold released, only the actual cost charged |

## 7. Live progress and export
Start a Celery worker, create an AI job, open AI Center › Jobs → the live line moves to "completed" and closes; "Export this
job's memory" downloads the JSON (owner/admin only).

## 8. Full-text acquisition
On a source with an open-access link, "Fetch full text" → "Full text acquired" only when a real document was converted;
a landing page reports "too short … nothing was claimed".
