"""Offline normative arithmetic and proposal-integrity checks; no runtime claims."""
from __future__ import annotations

import hashlib
import json
import math
import re
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
BASE = Path(__file__).resolve().parent


def main() -> None:
    policy = json.loads((BASE / 'policy.json').read_text())
    cases = json.loads((BASE / 'examples.json').read_text())
    assert policy['actual_provider_requests_authorized'] == 0
    assert policy['actual_fee_authorized'] == 0
    assert policy['production_mode'] == 'catalog_only'
    assert not policy['independence']['H_content_access_authorized']
    assert not policy['stop']['automatic_second_batch']
    samples = policy['samples']
    assert samples['quality_courses'] == 2 * samples['quality_pairs'] + samples['quality_single_goals']
    assert samples['performance_create_slots'] == samples['performance_cold'] + samples['performance_warm']
    assert samples['performance_create_slots'] == len(samples['performance_target_lengths']) * samples['performance_targets_per_length'] * 2
    for case in cases['rates']:
        assert 0 <= case['ok'] <= case['total']
        passed = case['total'] > 0 and Decimal(case['ok']) >= Decimal(str(case['minimum'])) * case['total']
        assert passed == case['pass'], case['id']
    for case in cases['latencies']:
        values = sorted(math.inf if value is None else value for value in case['seconds'])
        result = values[math.ceil(0.95 * len(values)) - 1] if values else math.inf
        assert (result <= case['limit']) == case['pass'], case['id']
        assert (None if math.isinf(result) else result) == case['p95'], case['id']
    for case in cases['decisions']:
        assert case['observed'] in policy['stop']['immediate']
        assert case['expected'] == 'stop'
    links = 0
    for path in [BASE / 'contract.md', ROOT / 'docs/ADR/0027-independent-free-course-acceptance.md']:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            if '://' not in target and not target.startswith('#'):
                assert (path.parent / target.split('#')[0]).resolve().exists(), target
                links += 1
    manifest = json.loads((BASE / 'manifest.json').read_text())
    for item in manifest['files']:
        assert hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest() == item['sha256'], item['path']
    previous = 0
    for relative in [
        'docs/ADR/0024-approval-20261021.json',
        'docs/ADR/0025-approval-20261021.json',
        'docs/ADR/0026-approval-20261022.json',
        'docs/design/phase-1.5-ui-approval-20261022.json',
    ]:
        approval = json.loads((ROOT / relative).read_text())
        assert hashlib.sha256((ROOT / approval['proposal_manifest']).read_bytes()).hexdigest() == approval['proposal_manifest_sha256']
        for item in approval['files']:
            assert hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest() == item['sha256']
            previous += 1
    print(f"PASS: {len(cases['rates'])} rate / {len(cases['latencies'])} latency / {len(cases['decisions'])} stop examples; {links} links; {len(manifest['files'])} proposal hashes; {previous} previous approved files unchanged")
    print('Design only; no network, Provider, H content, credentials, PG or browser run.')


if __name__ == '__main__':
    main()
