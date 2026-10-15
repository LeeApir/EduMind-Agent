# Trusted local review maintenance

No human processing SLA. Without an available maintainer, a case remains awaiting_human;
existing reviewed catalog courses remain usable. A CLI decision is an actual human
semantic conclusion only when a real maintainer inspects the complete accurate case.
Synthetic test decisions are never counted as real course signoffs.

On the trusted host, an administrator provisions a regular private (0600) JSON file
owned by root or the current effective Unix UID. Set EDUMIND_REVIEWER_CONFIG to it:

```json
{"version":"local-reviewers-v1","operators":[{"uid":501,"reviewer_id":"Lee"}]}
```

Replace uid with the actual approved operator UID. The CLI derives identity from the
OS and this allowlist, not --reviewer, student cookies, model output or approval JSON.
It trusts maintenance host/config administration; it is not cryptographic remote auth.
Set EDUMIND_DATABASE_URL via secure host configuration; do not load Provider credentials.

```
backend/.venv/bin/python scripts/review_learning_cases.py list
backend/.venv/bin/python scripts/review_learning_cases.py show CASE_UUID
backend/.venv/bin/python scripts/review_learning_cases.py show CASE_UUID --body
backend/.venv/bin/python scripts/review_learning_cases.py show CASE_UUID --export NEW_PRIVATE_PATH
backend/.venv/bin/python scripts/review_learning_cases.py decide CASE_UUID --case-digest EXACT_DIGEST --verdict approve --reason ACTUAL_REASON --idempotency-key UNIQUE_KEY
```

Default output contains metadata/digest only. --body explicitly shows the full plan,
resources, actions, reference context and four automatic reviews on the trusted terminal.
Exports are explicit 0600 new files, never overwritten. The CLI never runs model/code,
reads Provider keys or grants approval from a supplied passed=true file. A changed,
canceled, expired or cross-owner case fails; same exact decision key replays its receipt.
This step records the decision; T052 integrates the atomic publication transaction.

Validation: CLI --help, Ruff, app mypy181; 9 actual PG/identity/export/case tests passed
in isolated om50, no skips. Only synthetic lifecycle records were created; Provider 0.
