# Final Closure — Test Accounting (fresh DB `aiol_last`, migrations 0001→0023)

| | Count |
|---|---|
| TOTAL collected | 1044 |
| PASSED | 1044 |
| FAILED | 0 |
| SKIPPED | 0 |
| XFAIL | 0 |
| EXCLUDED (deselected) | 0 |
| NOT_RUN | 0 |

Run in four chunks (219 + 347 + 240 + 238). Plugin: 221/221 assertions, PHP lint clean.

## Exclusion audit
- The previous report's "2 documented exclusions" were not skipped tests. They were entries in the
  sorting contract's list of routes allowed not to expose `sort`. One of them,
  `/api/v1/agent-network/agents`, hid a real convention gap: it is now canonically sortable and the
  entry was **removed**. The remaining entry `/api/v1/telemetry/search-demand/terms` is a ranked
  aggregate (GROUP BY with its own `ascending` flag) — kept, justified in the test file.
- Conditional skip markers exist (fixtures missing, PostgreSQL unreachable, plugin checkout absent);
  none triggered in this run (0 skipped).
