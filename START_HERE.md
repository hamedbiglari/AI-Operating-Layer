# START HERE — AI Operating Layer, Phase 13 handoff

Read this file first. It takes about three minutes and will stop you
making the two mistakes this package is designed to prevent.

## 1. The status, before anything else

```
PHASE 12 = CONDITIONAL        (internal runtime strong; live providers blocked)
PHASE 13 = BLOCKED            (implemented, executed by nothing)
PHASE 14 = LOCKED
```

Phase 13 code exists, is complete, and **has never been run** — no test,
no migration, no render. Do not read "the code is there" as "the phase is
done". `docs/phase13/PHASE13_REPORT.md` §6 lists exactly what was and was
not executed, and §8 tells you how to change that.

## 2. What this package is

The **portable project state**: memory, decisions, verification records,
architecture, UX contract, and the full Phase 13 source tree.

Read in this order:

1. `docs/phase13/PHASE13_REPORT.md` — status, changes, forensic audit, verdict
2. `docs/phase13/REQUIREMENT_MATRIX.md` — every requirement, its evidence, its gaps
3. `docs/ai-context/CURRENT_STATE.md` — where the project actually is
4. `docs/DECISIONS.md` — ADR-001…081; **read ADR-079 in full**
5. `docs/ux/DASHBOARD_UX.md` + `docs/audits/PRODUCT_UX_ARCHITECTURE_CHECKPOINT_REPORT.md`
6. `docs/master-spec/MASTER_SPEC.md`

## 3. The one decision you must not miss

**ADR-079 supersedes the privacy narrowing in ADR-046.** The system now
collects visitor IP, coarse geography and time-on-page — which ADR-046
deliberately refused to collect, and which the UX checkpoint left as an
open owner decision. The owner has since decided to collect them.

ADR-046 is still on file, unedited. Do not "fix" the apparent
contradiction by deleting either one; the history is the point.

## 4. Things that must not be changed without a new ADR

* Cloud Core is the source of truth; the plugin is a thin adapter (§52).
* There is exactly one source manager, one job system (`SyncJob`), one
  query normalizer (`query_service.normalize_query`), one design system
  (`frontend/design-system/`), one icon registry
  (`frontend/icons/icon-paths.json`).
* `frontend/` files are canonical; the copies inside `wordpress-plugin/`
  are **generated** by `scripts/sync-design-system.php`. Never edit a
  copy — a parity test fails if you do.
* `AIOL_Actors::$signatures` is **generated** from
  `cloud-core/app/services/actor_signatures.py`. Same rule, same reason,
  and order within it is load-bearing.
* NULL is not zero, anywhere: `dwell_ms`, `mean_dwell_ms`,
  `result_count`, every `geo_*` field.
* An undecided access policy reports as `not_configured`, never
  `allowed`.
* No composite AI-visibility score (ADR-064). No unexplained trust score.
  No psychological or purchase-readiness inference (checkpoint §76/§77).

## 5. Before you write any code

Run the verification sequence in `PHASE13_REPORT.md` §8. If the 772-test
Phase 0–12 baseline does not pass on your machine, stop and fix that
first — you cannot tell a Phase 13 regression from a pre-existing failure
otherwise.

## 6. What Phase 13 does NOT include

The **Rights Layer** (MASTER §42) is not built. `docs/development.md` calls
Phase 13 "Rights Layer"; the recovered original roadmap calls it "Analytics
and Demand Intelligence"; the owner's instruction was analytics + AI
access. That naming conflict is recorded, not resolved. Someone has to
decide which one Phase 13 actually is.
