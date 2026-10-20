"""Read-only, no-network verification of R02-v2 and the A02 evidence ruling."""
# ruff: noqa: E402
import asyncio
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'backend')]
from acceptance_support.qwen_review_budget import sha
from app.services.unit_material import restore_material
from prepare_five_hour_materials import capture_case
import run_five_hour_remaining as prior

BASE = ROOT / 'docs/acceptance/phase-1-five-hour-material-review-r01'


def read(path):
    return json.loads(path.read_text())


async def check():
    # Verifies original materials, source freeze, stopped parent ledger and old results.
    prior.authorize()
    for package, private in [
        (prior.PACKAGE, prior.PRIVATE),
        (ROOT / 'docs/acceptance/phase-1-five-hour-a02-retest-r01', ROOT / 'local-materials/phase-1-five-hour-a02-retest-r01'),
    ]:
        assert sha((private / 'run.sqlite').read_bytes()) == read(package / 'terminal.json')['ledger_sha256']
    manifest_path = BASE / 'manifest.json'
    if manifest_path.exists():
        manifest = read(manifest_path)
        assert manifest['real_requests_authorized'] == 0
        for name, digest in manifest['files'].items():
            path = ROOT / name
            assert path.resolve().is_relative_to(ROOT) and not path.is_symlink()
            assert sha(path.read_bytes()) == digest, name
    old = read(prior.parent.BASE / 'cases/R02.json')
    new = read(BASE / 'R02-v2.json')
    restore_material(new['material'])
    assert new['actual_model_result'] is None
    assert new['scope'] == old['scope'] == 'resource'
    assert new['selected_role'] == old['selected_role'] == 'explanation'
    assert new['input_snapshot']['metadata'] == old['input_snapshot']['metadata']
    assert new['material']['plan'] == old['material']['plan']
    assert new['material']['binding']['policy_digest'] == old['material']['binding']['policy_digest']
    assert new['material']['binding']['unit_id'] != old['material']['binding']['unit_id']
    assert new['material']['unit_digest'] != old['material']['unit_digest']
    def by_role(case):
        return {c['role']: c for c in case['material']['candidates']}

    a, b = by_role(old), by_role(new)
    for role in ['code','exercise']:
        assert a[role]['envelope'] == b[role]['envelope']
    assert a['explanation']['envelope'] != b['explanation']['envelope']
    assert b['explanation']['envelope']['content']['markdown'] == (BASE / 'R02-v2-student.md').read_text().rstrip('\n')
    request = read(BASE / 'R02-v2-request.json')
    assert await capture_case(new) == request
    old_wire = json.loads(bytes.fromhex(read(prior.parent.BASE / 'requests/R02.json')['wire_hex']))
    new_wire = json.loads(bytes.fromhex(request['wire_hex']))
    assert old_wire['input'][0] == new_wire['input'][0]  # Exact system instruction unchanged.
    assert old_wire['text']['format'] == new_wire['text']['format']
    payload = json.loads(new_wire['input'][1]['content'])
    assert payload['candidate']['envelope'] == b['explanation']['envelope']
    assert not {'expected_verdicts','labels','actual_model_result'} & payload.keys()
    label = read(BASE / 'R02-v2-label.json')
    assert label['actual_result'] is None and label['expected_verdicts'] == ['pass']
    evidence = read(BASE / 'A02-evidence.json')
    source_path = ROOT / evidence['source']
    assert sha(source_path.read_bytes()) == evidence['source_sha256']
    source = read(source_path)
    for part in evidence['source_pointer'].strip('/').split('/'):
        source = source[int(part)] if isinstance(source,list) else source[part]
    assert evidence['plan'] == source['plans'][0]['plan']
    assert evidence['resources'] == source['resources']
    assert evidence['original_request'] == source['plans'][0]['input_snapshot']['teaching_context']['original_request']
    ruling = read(BASE / 'A02-adjudication.json')
    assert ruling['plan_commitment']['objective'] in evidence['plan']['objectives']
    assert ruling['plan_commitment']['exercise_scene'] in evidence['plan']['scenes']
    exercise = next(r for r in evidence['resources'] if 'items' in r['content'])['content']['items']
    assert len(ruling['questions']) == len(exercise) == 3
    for actual, checked in zip(exercise, ruling['questions'], strict=True):
        assert all(checked[k] == actual[k] for k in ('id','question','answer','explanation'))
    assert ruling['recommended_existing_contract_result']['verdict'] == 'needs_human'
    assert not ruling['recommended_existing_contract_result']['findings']
    print(json.dumps(dict(result='passed',real_provider_calls=0,offline_mock_review_wires=1,old_freezes_and_ledgers='unchanged',R02='restorable new material, exact offline request, unchanged goal/prompt/schema/sibling content',A02='original evidence exact; semantic adjudication authored separately, not proved by this checker')))


if __name__ == '__main__':
    asyncio.run(check())
