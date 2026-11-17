"""Offline design consistency checks; no DB, network, provider or runtime tests."""
import hashlib
import json
import re
from pathlib import Path

from fastapi.openapi.models import OpenAPI
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = Path(__file__).resolve().parent


def main():
    api = json.loads((ROOT / 'docs/api/phase-1.5-generation.openapi.json').read_text())
    OpenAPI.model_validate(api)
    schemas = api['components']['schemas']
    for schema in schemas.values():
        Draft202012Validator.check_schema(schema)
    refs = []

    def walk(value):
        if isinstance(value, dict):
            if '$ref' in value:
                pointer = value['$ref']
                assert pointer.startswith('#/')
                node = api
                for part in pointer[2:].split('/'):
                    node = node[part.replace('~1', '/').replace('~0', '~')]
                refs.append(pointer)
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)

    walk(api)
    operations = [op for path in api['paths'].values() for op in path.values()]
    assert len({op['operationId'] for op in operations}) == len(operations)
    assert all(op['x-runtime-status'] == 'planned' for op in operations)
    assert all(op['security'] == [{'sessionCookie': []}] for op in operations)
    policy = json.loads((PACKAGE / 'policy.json').read_text())
    limits = policy['limits']
    assert limits['operation_attempts'] == sum(limits[k] for k in (
        'primary_plan_calls', 'primary_scene_calls', 'transport_retry_pool', 'format_repair_pool'))
    assert limits['scenes_max'] == limits['primary_scene_calls']
    assert limits['heartbeat_seconds'] < limits['lease_seconds'] < limits['call_seconds']
    assert limits['operation_attempts'] <= limits['course_attempts']
    assert limits['operation_input_tokens'] <= limits['course_input_tokens']
    assert limits['operation_output_tokens'] <= limits['course_output_tokens']
    states = policy['operation_states']
    assert not set(states['active']) & set(states['terminal'])
    assert all(t not in states['transitions'] for t in states['terminal'])
    reached = {'queued'}
    for _ in range(len(states['active']) + len(states['terminal'])):
        reached |= {t for source in reached for t in states['transitions'].get(source, [])}
    assert reached == set(states['active'] + states['terminal'])
    assert policy['actual_provider_requests_authorized'] == 0

    def validator(name):
        return Draft202012Validator({'components': {'schemas': schemas},
                                     '$ref': '#/components/schemas/' + name})

    uid = '11111111-1111-4111-8111-111111111111'
    base = {'schema_version': 'free-course-events-v1', 'operation_id': uid,
            'seq': 1, 'type': 'scene_ready', 'course_version': 1,
            'payload': {'scene_id': uid, 'scene_version_id': uid}}
    validator('Event').validate(base)
    invalid_events = [
        {**base, 'course_version': None}, {**base, 'payload': {'scene_id': uid}},
        {**base, 'type': 'done', 'payload': {'state': 'running'}},
        {**base, 'type': 'clarification_required', 'payload': {}},
        {**base, 'type': 'error', 'payload': {}},
        {**base, 'payload': {**base['payload'], 'correct_answer': 'secret'}},
    ]
    for event in invalid_events:
        assert list(validator('Event').iter_errors(event)), event
    validator('ResumeRequest').validate({'kind': 'resume', 'expected_head_version': None,
                                         'source_operation_id': uid})
    assert list(validator('ResumeRequest').iter_errors({'kind': 'resume', 'source_operation_id': uid}))
    assert list(validator('CancelRequest').iter_errors({'owner_id': uid}))
    scene = {'course_id': uid, 'course_version': 1, 'scene_id': uid,
             'scene_version_id': uid, 'blocks': [{'kind': 'text', 'anchor_id': 'a',
                                                'markdown': '正文'}], 'actions': []}
    validator('SceneProjection').validate(scene)
    assert list(validator('SceneProjection').iter_errors({**scene, 'blocks': [
        {'kind': 'code', 'anchor_id': 'a', 'language': 'c', 'source': 'int x;'}]}))
    assert list(validator('TextBlock').iter_errors(
        {'kind': 'text', 'anchor_id': 'a', 'markdown': ''}))
    assert list(validator('Action').iter_errors(
        {'type': 'show_step', 'anchor_id': 'a', 'step_index': None}))
    assert list(validator('Action').iter_errors(
        {'type': 'highlight_block', 'anchor_id': 'a', 'step_index': 2}))
    examples = json.loads((PACKAGE / 'examples.json').read_text())
    assert examples['status'] == 'design_cases_not_runtime_results'
    assert len({case['id'] for case in examples['cases']}) == len(examples['cases'])
    assert all(case['given'] and case['expected'] for case in examples['cases'])
    links = 0
    for doc in [ROOT / 'docs/ADR/0025-progressive-course-generation.md', PACKAGE / 'contract.md']:
        for target in re.findall(r'\]\(([^)]+)\)', doc.read_text()):
            assert (doc.parent / target.split('#')[0]).exists(), (doc, target)
            links += 1
    manifest = json.loads((PACKAGE / 'manifest.json').read_text())
    for item in manifest['files']:
        assert hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest() == item['sha256']
    print(f'PASS: OpenAPI structure, {len(refs)} refs, {len(operations)} planned operations, '
          f'{len(schemas)} schemas, budget/state consistency, 15 schema examples, '
          f'{len(examples["cases"])} design cases, {links} links, {len(manifest["files"])} frozen files; '
          'no runtime verification')


if __name__ == '__main__':
    main()
