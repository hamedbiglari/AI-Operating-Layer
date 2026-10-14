Scripts used for CORE_KNOWLEDGE_TO_PURCHASE_E2E.md. Paths are those of the verification
sandbox; `state.json` (holds tokens) is deliberately not committed. Order:
`up.sh` → `e2e_core_setup.py` → (wp-cli steps in the E2E document) → `e2e_loop.py` →
`e2e_purchase.py` → `e2e_tenant.py`.
