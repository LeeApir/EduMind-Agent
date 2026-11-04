"""Read-only r02 receipt/mapping/stop check. No Provider calls or terminal access."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT)]
from cryptography.fernet import Fernet  # noqa: E402
from scripts import head_course_goal as entry  # noqa: E402

HERE = Path(__file__).resolve().parent
VAULT = Path('/Users/apir/.local/share/edumind/head-goal-r02')
SHA = '41d0bb3aec551b3ad08fa63e711476710c44d43483d41477fb5eb077b72cbc6a'


def read(path):
    return json.loads(path.read_text())


def main():
    assert entry.package_digest() == SHA
    approval = read(VAULT / 'approval.json')
    window = read(HERE / 'execution-window.json')
    assert approval['package_sha256'] == SHA
    assert approval['planning_wire_version'] == entry.plan_wire.VERSION
    assert approval['accept_ADR0052_R02_and_batch_C2'] is True
    assert window['starts_epoch'] == approval['starts_epoch']
    assert window['expires_epoch'] == approval['expires_epoch']
    assert window['expires_epoch'] - window['starts_epoch'] == 600
    assert window['actual_http_requests'] == 1 and window['remaining_requests_invalidated'] == 2
    assert window['generated_plans'] == 1 and window['accepted_plans'] == 0
    assert window['stopped'] and window['generated_complete_courses'] == 0
    assert (VAULT / 'STOP').exists() and not (VAULT / 'ACTIVE').exists()
    assert len(list(VAULT.glob('*.attempt.json'))) == 1
    context = read(VAULT / 'context.json')
    request = read(VAULT / 'plan.request.json')
    assert request == entry.planning_body(context['planning_inputs'])
    attempt = read(VAULT / 'plan.attempt.json')
    assert attempt['package_sha256'] == SHA
    assert attempt['evidence_kind'] == 'actual_provider_response'
    assert attempt['request_sha256'] == hashlib.sha256(entry.canonical(request)).hexdigest()
    original_index = read(HERE / 'originals-manifest.json')
    for name, sha in original_index['files'].items():
        assert hashlib.sha256((VAULT / name).read_bytes()).hexdigest() == sha, name
    for name in ('plan.request.json', 'plan.attempt.json', 'plan.output.json',
                 'plan.mapping.json', 'plan.binding.json', 'plan.body.json',
                 'plan-review.json', 'planning-review.failure.json'):
        assert (HERE / name).read_bytes() == (VAULT / name).read_bytes(), name
    # This is the local HTTP-body encryption key, never a Provider credential.
    cipher = Fernet((VAULT / 'raw.key').read_bytes())
    value = entry.verify_saved(VAULT, 'plan', cipher)
    raw = entry.raw_io.decrypt(VAULT / 'plan.raw.enc', cipher)
    body = read(VAULT / 'plan.body.json')
    assert body['http_status'] == 200 and body['body_complete']
    assert len(raw) == body['raw_bytes'] == 6312
    assert hashlib.sha256(raw).hexdigest() == body['raw_sha256']
    review = read(HERE / 'plan-review.json')
    assert review['plan_digest'] == entry.digest('head-plan', plan=value['plan'])
    assert review['verdict'] == 'stop_planning_consistency'
    assert review['teaching_generation_allowed'] is False
    assert value['plan'] == read(HERE / 'plan.binding.json')['payload']['plan']
    assert not any((VAULT / name).exists() for name in (
        'generate.attempt.json', 'generate.record.json', 'repair.attempt.json',
        'repair.record.json', 'published.json',
    ))
    app = read(HERE / 'app-stop-result.json')
    assert app['state'] == 'failed' and app['reason_code'] == 'PLANNING_REVIEW_FAILED'
    assert app['head_version'] == app['planning_results'] == 1
    assert app['scene_generation_results'] == 0
    print('PASS: 1 HTTP200/complete raw/mapping verified; planning review nonpass; '
          '0 complete courses; STOP/unused2invalidated. Provider calls in this check:0.')


if __name__ == '__main__':
    main()
