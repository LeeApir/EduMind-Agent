# Shared-plan learning implementation

Approved design: ADR-0015 and its frozen minimum contract. Runtime schema is packaged
at `backend/app/services/learning_contract.schema.json`; regression tests compare its
bytes with the approved schema. No runtime dependency on the repository docs folder.

T044: Alembic `0026_learning_plans` adds immutable owner/unit/operation-scoped plan
snapshots and nullable scene/resource bindings. Legacy `intro` rows remain unbound.
Input/reference/policy snapshots retain audit material alongside domain-separated
SHA256 digests. Planned candidates cannot be rewritten or attached retrospectively.
Downgrade with existing plan data fails before removing columns. Plans grant no
publication qualification and no new API response fields are exposed at this step.

Actual PG validation (isolated `edumind_catalog_phase1_om44b`):

```
EDUMIND_CATALOG_TEST_PG_CONTAINER=edumind-phase1-t037-pg backend/.venv/bin/python scripts/run_provider_storage_tests.py edumind_catalog_phase1_om44b tests/test_learning_plan_persistence.py tests/test_learning_persistence.py tests/test_catalog_sessions.py
```

Upgrade/empty downgrade/upgrade passed; 11 tests passed with zero skips, including
actual Alembic refusal to downgrade populated plans and unchanged legacy reads.
Provider requests: 0. Ruff and application mypy (169 modules) passed.
