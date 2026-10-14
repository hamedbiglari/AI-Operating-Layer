# Keyword & Knowledge Pipeline (ADR-092, REQ-KW-001/002/003/004)

## Status: REQ-KW-001/002/003 IMPLEMENTED; REQ-KW-004 REGISTERED_OPEN

## DB table: knowledge_keywords
Columns: knowledge_object_id, keyword, kind (primary/secondary/long_tail/question/commercial/
transactional/local/scientific/synonym/alias/spelling/entity/customer_question/ai_query),
intent, source, volume, country, language, notes, priority, import_batch, raw (original row),
last_research_task_id (traceability).
Unique: (knowledge_object_id, keyword, kind) — no duplicates, originals kept.

## Import formats (REQ-KW-002)
CSV, Excel (.xlsx / .xls), plain text (one keyword per line), JSON array, manual single entry.
Limits: 5000 keywords per import, 50 000 per knowledge object.
Each row gets a report entry (ok / skipped_duplicate / error).

## Search New Sources (REQ-KW-003)
`POST /knowledge/{ko_id}/keywords/search-sources` with selected keyword IDs:
1. Creates a Research Task per keyword (task type = web_search or custom)
2. Links the task back to the keyword: `last_research_task_id`
3. Returns { research_tasks: [...], keyword_count: N }
Traceability: keyword → research task ID.

## Pipeline intent (REQ-KW-004 — open)
The complete pipeline from keyword to published content:
```
Keyword → Research Task → Source Discovery → Source Ingestion
→ Evidence → Claim → Knowledge Object update → Published content
```
The first two links (keyword → research task) are implemented and traced.
The remaining links (source → evidence → knowledge → published) follow the existing
pipeline (Phase 3/5) but are not yet explicitly traced back to the originating keyword.

## Keywords ≠ SEO metadata
Keywords feed research (→ source discovery → knowledge), not only search-engine optimisation.
The system uses them to detect information gaps and drive content generation.
