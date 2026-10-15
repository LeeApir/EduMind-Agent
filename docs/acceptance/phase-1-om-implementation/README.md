# T044–T054 implementation and offline acceptance preparation

This is the **new shared-plan combination**, not a continuation of the retired r11
route. T040 remains blocked. No real Provider requests, paid-run authority, deployment
or dynamic opening is granted. The default catalog_only configuration is unchanged.

- `frozen-combination.json`: current source SHA256 closure, 100 new generation targets,
  20 severe / 20 correct / 10 long audit slots, eight diagnostic categories, 20 offline
  route scenarios, unchanged quality thresholds, and the conservative request envelope.
- `benchmark-materials.json`: 50 concrete assistant-authored semantic units, with plan
  drafts and three resource envelopes. C is display-only; no candidate C was compiled
  or executed. Deliberately unsafe examples exist solely as review inputs.
- `proposed-labels.json`: separate proposed ground truth and concrete counterexamples.
  **All 50 require independent human review.** These labels are not sent as model input
  and are not human course approvals. Paired examples share code; long examples repeat
  bounded context. Do not describe these as statistically independent random draws.
- `not-run-report.json`: all 100/20/20/10 denominators retained, every slot NOT_RUN.
  Missing responses remain in the denominator. Human approvals never fill the automatic
  quality numerator. Detection, classification, unsupported findings and completion are
  distinct; schema completeness is not factual correctness.
- `validation.json`: actual zero-Provider validation and limits of that evidence.

The generation roster targets the approved phase-1.1.0 graph; selecting that graph for
a future real run is part of its new configuration freeze, not a change to current
server configuration. Runtime Web requests use shared-plan-v1; older client contracts
are retained explicitly and cannot be used as a new-chain failure fallback.

## Reproduce the offline checks

From repository root:

```
backend/.venv/bin/python scripts/prepare_om_redesign_acceptance.py --check
cd backend && .venv/bin/pytest -q tests/test_om_redesign_acceptance_preparation.py
```

The preparer has no Provider/credential/transport imports. `--run` returns exit 2,
NOT_AUTHORIZED and zero requests **before reading the frozen preparation**. There is no
flag that approves or spends a budget. An actual trusted execution runner belongs to
T040 and must bind an independently approved exact run; this CLI cannot become one by
editing a JSON approval file.

## Budget envelope and remaining real-run gates

Current new Web pipeline omits optional profile inference/temporary text and has a
shared 20-call maximum (including any goal mapping), total 180 seconds and single-call
60 seconds, with no retry or implicit fallback. Request slots are durably consumed
before sending; canceled/failed attempts do not restore capacity.

This offline envelope conservatively allocates eight diagnostics × 20 = 160 requests,
100 generation targets × 20 = 2000, and 50 audit units × four reviews = 200, at most
**2360** requests. The largest per-call total output limit is 4096 (including reasoning),
so a deliberately conservative total output bound is 9,666,560 tokens. Many actual
calls use 2048; this is an upper envelope, not expected consumption or exact wire slots.
Offline mixed-route cases and human CLI decisions use zero model calls.

Exact Provider/model/sampling/graph configuration, independent labels, reference and
wire/derived-slot freeze, current official input-token and price proof, an exact CNY
ceiling, and explicit paid-run approval remain required. The monetary ceiling is null
and authorized fees/requests are zero. Once proven, a cost envelope can use the sum of
per-slot verified input/output token bounds × verified same-currency prices. Never use
UTF-8 byte counts as token estimates or import the old ledger's unused capacity.

## Validation and interpretation

Twenty route cases execute real local schema/anchor/hard-code/action/routing gates with
synthetic review bodies. They test routing, not semantic recall. Reporting tests verify
94 automatic + six human approvals cannot satisfy the ≥95 automatic gate even if the
mixed total reaches 100. Every new formal candidate and label still needs the separate
T040 ground-truth procedure; no new real quality score has been produced here.

Integration used the actual dedicated PostgreSQL database om54 and injected synthetic
Gateways/mock HTTP: all new stages plus legacy learning loop, quiz, notes, paths,
catalog sessions/mode, ReviewAgent, Gateway and DeepSeek parser tests. The Web suite and
real Chromium mock journey cover page recovery and exact publication reads. This does
not certify real model quality, real paid TLS traffic, Worker rendering, concurrency at
production load or cross-course teaching quality. Existing DSL isolation and its
separate quality/Worker gates remain in force.

Do not advance T040/T041 or open dynamic mode from these engineering checks. Original
T033 and r01–r11 results, labels, counters and retirement records remain unchanged.
