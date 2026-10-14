# Pre-existing Defect Register (verified pre-existing; not Phase 17)

| ID | Defect | Verified how | Owner | Severity |
|---|---|---|---|---|
| D-01 | `Base.metadata.create_all` fails on a fresh DB (`ai_agents` composite FK has no matching unique target in the model) | reproduced on the pre-Phase-17 tree | Phase 13 | Medium (tests must use an alembic DB) |
| D-02 | `visibility_tests` composite FKs use plain `ON DELETE SET NULL` with NOT NULL `organization_id` | schema reading; untouched by P17 | Phase 12 | Medium (deleting a referenced query fails) |
| D-03 | `test_phase13_telemetry::test_unknown_sort_field_is_422_naming_the_allowed_values` | fails identically before P17 | Phase 13 | Low (test expects old error shape) |
| D-04 | `test_phase13_telemetry::test_a_human_view_has_no_agent_signature_not_a_placeholder` | same | Phase 13 | Low–Medium |
| D-05 | `test_phase13_access_and_agents::test_specific_agent_rule_beats_a_stricter_general_rule` | same | Phase 13 | Medium (access-policy precedence) |
| D-06 | `test_sorting.py` ×3: 7 telemetry collection routes lack sorting/exclusion | same failures on pre-P17 tree | Phase 13 | Low |
| D-07 | Plugin test `absorption`: "no IP address is read or stored anywhere" fails — `includes/class-aiol-geo.php` reads `REMOTE_ADDR` | first-ever plugin test run (this audit) | Phase 13 (test stale after ADR-079 / P13-REQ-002) | Low (conflict C-2; the test, not the code, is out of date) |
| D-08 | Plugin test `design system parity` ×2: plugin copies of `components.css` and `icon-paths.json` differ from canonical `/frontend` | first-ever plugin test run | Phase 13 | Low (project's own remedy: `php scripts/sync-design-system.php`) |
| D-09 | Harness SVGs use `width="var(--icon-size)"` attributes → console warnings | Chrome console | Phase 13 dashboard | Low |
| D-10 | Harness mobile card tables overflow their container by 34 px | measured on existing Sources screen | Phase 13 dashboard | Low |
| D-11 | Project memory (`CURRENT_STATE.md`) stale since Phase 13 | file content | all | Fixed in this audit (documentation) |

## Re-review (existing-requirements closure pass)
All of D-01…D-10 re-confirmed pre-existing; none blocks the core Knowledge→Product→Purchase
loop (E2E-K2C-001 passed with them present). D-07/D-08 re-observed on the second plugin run
(216/219). D-11 closed. New defect found and fixed in this pass (not pre-existing to the
product, but pre-existing in Phase 11): **C-P11-01** `/ai/ask` carried no merchant URL — see
CORE_KNOWLEDGE_TO_PURCHASE_E2E.md.

## Final existing-owner closure pass
| ID | Outcome |
|---|---|
| D-03 | CLOSED — stale test (pre-envelope `detail`); updated to the project error envelope |
| D-04 | CLOSED — real defect (human fingerprint exposed); fixed |
| D-05 | CLOSED — real, security-relevant defect (agent-specific rules never matched; named-agent block could be bypassed); fixed + fail-open test |
| D-06 | CLOSED — six routes moved to canonical sorting; one ranked aggregate documented as exclusion |
| D-07 | CLOSED — plugin test updated to accepted ADR-079 |
| D-08 | CLOSED — plugin design-system copies regenerated |
| D-01, D-02, D-09, D-10 | OPEN (unchanged; do not block the core loop) |
