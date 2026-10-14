# AI Development Rules

1. **Do NOT rewrite the entire project for a small task.**
2. **Read CURRENT_STATE.md before any implementation.**
3. **Inspect only files relevant to the task.**
4. **Preserve existing architecture unless necessary.**
5. **Preserve existing tests.**
6. **Add regression tests for every bug fix.**
7. **Do not modify old database migrations. Create new ones.**
8. **Maintain tenant isolation and RBAC.**
9. **Maintain audit logging.**
10. **Keep changes focused and minimal.**
11. **Never claim tests passed unless actually executed.**
12. **At the end of every task, report:**
    - files changed
    - database changes
    - API changes
    - tests added
    - tests executed
    - known limitations