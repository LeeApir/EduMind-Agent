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

T049: `unit_material` binds one plan, exact scene/resource versions, dependencies and
trusted actions to learning-publication-v1 unit_digest before review. Restoring a
modified material fails. Independent unit review receives full plan, all resources,
actions and reference context; consistency cannot revise or start a global generation
loop. Current reject stops; uncertainty in any component retains needs_human. Binding,
action and consistency regressions: 17 passed; Ruff/mypy177 passed; Provider 0.

T050: Alembic 0028 stores immutable complete case payloads and append-only decisions.
One pending/approved case per owner/unit; local owner and unit locks serialize decisions,
cancellation and future publication. Only needs_human is eligible; current reject cannot
be overridden. Decisions bind the exact case digest, reviewer identity source, reason and
idempotency key. Replay returns the original decision, changed payload conflicts.
Cancellation/new plan/changed active policy invalidate the old case; canceled stays
canceled, other unfinished operations fail REVIEW_CASE_INVALIDATED. No publication
occurs in the decision service. Actual PG om50: migration empty roundtrip and 16 tests
passed, including concurrent replay and approval/cancellation. One test import omission
was corrected without changing its assertions. Ruff and application mypy180 passed.

T052: Alembic 0029 adds immutable publication/withdrawal snapshots, a current-publication
pointer, classroom publication_version and durable call counts/deadlines. The complete
pipeline commits private candidates and automatic audits between model stages, outside
network waits. A shared 20-call/180-second window reserves a durable slot before each
request; failure never refunds it and replay never restarts generation. Optional initial
profile/preview calls are not part of this service. Real acceptance still needs its own
approved monetary envelope and a budgeted gateway; no live run is authorized here.

Automatic qualification or an exact eligible human decision atomically publishes all
three resources/scenes, records approval_source, advances the pointer and classroom CAS,
and completes the operation. CLI approval shares this transaction. Public resource,
quiz/export/path and template qualification use complete publication provenance; private
candidates remain inaccessible. Legacy intro publication and curated signatures remain.

Planned reexplanation takes associated code/language from one snapshot: simpler/deeper
reuse the plan but bind new resource IDs and re-review all three; another_example must
change the example and rebuild the plan/resources. New operations invalidate old pending
cases. Waiting/failure keeps the old complete snapshot; historical resources retain their
own IDs. Classroom revision/generation changes reject late publication. Planned calls
are prepared as services here; T053 wires their API/SSE paths and UI.

Validation: isolated om52b migration empty roundtrip; final 50 PG tests passed, zero
skips, including legacy speech/control/reexplanation, populated downgrade refusal,
rollback, cancellation/publication race, exact resource reads and withdrawal. Initial
legacy tests used catalog_only and correctly returned 404; rerun in the isolated dynamic
mock-test process passed, without changing server configuration or assertions. The old
stage-pinned migration test now checks the first populated protective migration and
unchanged head, as newer protected tables precede 0026. Ruff/mypy185 passed; Provider 0.
