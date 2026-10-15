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

T046: `PlannedScenes` keeps private candidates with server UUID, content/dependency
digests and complete upstream snapshots. A predecessor must be reviewed as pass or
needs_human before dependent generation; reject/revise block the dependent stage.
Changing a candidate discards all dependent candidates and dispositions. A code
language mismatch fails. This workspace alone grants no publication qualification.
Scene generation uses the operation's shared call/deadline window, 4096 total output
per generation, no retry/fallback. New and legacy generator regressions: 13 passed.

T047: teaching-actions-v1 deterministically assembles show_resource, code key-step
highlights and ask_exercise references. Server-created UTF-8 anchors identify original
fields. Action validation recomputes the exact trusted template and bound resource
digests, rejecting cross-scene IDs, extra speech/HTML and stale content. No Provider
calls. Action/dependency regressions: 10 passed; Ruff and mypy172 passed.

T048: evidence-resource-review-v4 and Alembic 0027 add four-result evidence review,
separate local routing and append-only records bound to owner/unit/plan/operation.
Server anchor catalogs and mandatory checks are validated; schema/invalid anchor/hard
code/objective-format failures cannot be waived. Complete candidates are corrected and
re-reviewed at most twice. Missing reference context goes to human. Audit hashes use
actual transport bodies; legacy calls remain compatible. Synthetic review, mock HTTP,
old ReviewAgent and actual PG regressions: 73 passed, zero skips, om48b. Migration
empty roundtrip passed. Ruff and application mypy175 passed. Provider requests: 0.
