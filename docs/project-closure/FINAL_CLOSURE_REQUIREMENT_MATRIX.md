# Final Closure — Requirement Matrix

| Requirement | Source | Owner | Implementation | API | DB | Worker | UI | Test | Runtime | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| Background policy controls the worker (connected ≠ enabled) | owner prompt §5–10 | ADR-095 | `run_job` policy gate + routing `forbidden` set | `/agent-network/background-policies` | 0021 (+0022 `ai_jobs.task_type`) | yes | Settings › Background AI processing (account checkboxes) | 12 worker-path + 9 service | browser: policy saved from Settings | IMPLEMENTED_VERIFIED (internal) |
| Agent A → Agent B execution with handoff | §11–17 | ADR-096 | `AgentExecutionService` | run / handoff / accept routes | 0021 | AI job path | AI Center › Agent network › orchestration console (7 actions) | 8 + 12 | browser: register 2 agents, grant memory, session, task, run (1 AIExecution), handoff + memory checkpoint, wrong agent refused, accept, run (1 AIExecution) — TEST_PROVIDER | RUNTIME_VERIFIED (internal); EXTERNAL provider BLOCKED |
| Agent memory permission | §15 | ADR-096 | bindings enforced in service | memory-bindings route | 0021 | — | console step 2 | denial + audit test | browser | IMPLEMENTED_VERIFIED |
| Keyword → published content trace | §20–23 | REQ-KW-004 | `keyword_traces` | `/keyword-traces` | 0022 | — | Knowledge › keyword workspace trace view | 5 | — (API/UI wired) | TEST_VERIFIED (+UI) |
| Demand Intelligence (distinct sources → DemandSignal → research) | §24–25 | ADR-099 | `demand_service` | `/demand/*` (6 routes) | 0023 | — | Analytics › Demand intelligence panel | 6 | browser: site searches synced, GSC export imported, GSC connect = blocked, promote → research task | IMPLEMENTED_VERIFIED; live GSC/GA4 BLOCKED_EXTERNAL_DEPENDENCY |
| English locale | §26 | REQ-UX-001 | — | — | — | — | all screens | automated audit | 43 screens: 0 Persian UI strings, 0 attributes (136 Persian *data* nodes: merchant names/products) | RUNTIME_VERIFIED |
| Responsive | §27 | REQ-UX | CSS | — | — | — | all | automated audit | 43 screens × 320/375/768/1024/1280/1440, LTR+RTL: 0 overflow / 0 escapes / 0 small targets | RUNTIME_VERIFIED |
| AIExecution invariants | §17 | Phase 16 | unchanged | — | — | — | — | 1044 suite | agent runs produced exactly 1 AIExecution each | PRESERVED |
| Real AI provider | P12/P17 | — | adapter ready | — | — | — | — | — | — | BLOCKED_EXTERNAL_DEPENDENCY |
