"""Check proposal structures only; never asserts DB, scoring or Provider behavior."""
import hashlib
import json
import re
from pathlib import Path

from fastapi.openapi.models import OpenAPI
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = Path(__file__).resolve().parent


def main():
    api = json.loads((ROOT / 'docs/api/phase-1.5-quality.openapi.json').read_text())
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
                target = api
                for part in pointer[2:].split('/'):
                    target = target[part.replace('~1', '/').replace('~0', '~')]
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
    assert all(op['x-implementation-task'] == 'PHASE-1.5-T020' for op in operations)
    assert not any('confirm' in path or 'attest' in path for path in api['paths'])

    def validator(name):
        return Draft202012Validator({'components': {'schemas': schemas},
                                     '$ref': '#/components/schemas/' + name})

    uid = '11111111-1111-4111-8111-111111111111'
    binding = {'course_version': 1, 'scene_id': uid, 'scene_version_id': uid}
    cases = []
    feedback = {**binding, 'anchor_id': 'a', 'exercise_id': None,
                'exercise_version_id': None, 'description': '这段可能有问题'}
    cases += [('FeedbackRequest', feedback, True),
              ('FeedbackRequest', {**feedback, 'confirmed': True}, False),
              ('FeedbackRequest', {**feedback, 'exercise_id': uid}, False)]
    question = {'question_id': 'q1', 'question': '解释头指针', 'input_type': 'short_text'}
    exercise = {'kind': 'exercise', 'anchor_id': 'a', 'exercise_id': uid,
                'exercise_version_id': uid, 'question': '短文本练习',
                'items': [question, {**question, 'question_id': 'q2'}]}
    cases += [('ExerciseBlock', exercise, True),
              ('ExerciseBlock', {**exercise, 'answer_key': 'leak'}, False),
              ('ExerciseBlock', {**exercise, 'items': [question]}, False)]
    answer = {'question_id': 'q1', 'answer': '我的解释'}
    attempt = {'attempt_id': uid, 'binding': binding, 'exercise_id': uid,
               'exercise_version_id': uid, 'answers': [answer],
               'completeness': 'incomplete', 'reliability': 'provisional',
               'comparison_score': None, 'question_results': [],
               'mastery_effect': 'course_only', 'reason_code': 'INCOMPLETE'}
    withdrawn = {**attempt, 'completeness': 'complete', 'reliability': 'withdrawn',
                 'mastery_effect': 'revoked', 'reason_code': 'ANSWER_WITHDRAWN'}
    cases += [('Attempt', attempt, True), ('Attempt', withdrawn, True),
              ('Attempt', {**withdrawn, 'comparison_score': 1}, False),
              ('Attempt', {**attempt, 'mastery_effect': 'admitted'}, False),
              ('Attempt', {**withdrawn, 'question_results': [
                  {'question_id': 'q1', 'matches_reference': True, 'explanation': 'old'}]}, False)]
    tutor = {**binding, 'message': '请再解释一下', 'acknowledge_assisted_practice': True}
    cases += [('TutorRequest', tutor, True),
              ('TutorRequest', {k: v for k, v in tutor.items()
                                if k != 'acknowledge_assisted_practice'}, False),
              ('TutorRequest', {**tutor, 'acknowledge_assisted_practice': False}, False)]
    turn = {'turn_id': uid, 'operation_id': uid, 'binding': binding, 'message': '解释',
            'status': 'invalidated', 'markdown': None, 'anchor_refs': [],
            'reason_code': 'SOURCE_CHANGED'}
    cases += [('TutorTurn', turn, True),
              ('TutorTurn', {**turn, 'markdown': 'stale'}, False)]
    event = {'schema_version': 'free-course-events-v1', 'operation_id': uid,
             'seq': 1, 'type': 'tutor_ready', 'course_version': 1,
             'payload': {'turn_id': uid}}
    cases += [('TutorEvent', event, True),
              ('TutorEvent', {**event, 'payload': {'markdown': 'secret'}}, False),
              ('TutorEvent', {**event, 'type': 'done', 'payload': {'state': 'running'}}, False)]
    for name, value, valid in cases:
        assert bool(list(validator(name).iter_errors(value))) != valid, (name, value)
    policy = json.loads((PACKAGE / 'policy.json').read_text())
    generation = json.loads((ROOT / 'docs/acceptance/phase-1.5-generation-contract-r01/policy.json').read_text())
    assert policy['actual_provider_requests_authorized'] == 0
    assert policy['automatic_semantic_attestation'] is False
    assert policy['source_dispatch']['unknown_nonnull'] == 'reject'
    assert policy['source_dispatch']['free-course-correction-v1'] == 'audit_only_never_score'
    mentor = policy['mentor']
    assert mentor['attempts'] == 1 and mentor['automatic_retries'] == mentor['format_repairs'] == 0
    for dimension in ['attempts', 'input_tokens', 'output_tokens']:
        assert mentor['shared_course_' + dimension] == generation['limits']['course_' + dimension]
    assert mentor['parallel_with_generation'] is False
    assert schemas['TutorBudget']['properties']['attempts_used']['maximum'] == mentor['attempts']
    assert schemas['TutorRequest']['properties']['acknowledge_assisted_practice']['const'] is True
    examples = json.loads((PACKAGE / 'examples.json').read_text())
    assert examples['status'] == 'design_cases_not_runtime_results'
    assert len({case['id'] for case in examples['cases']}) == len(examples['cases'])
    assert all(case['given'] and case['expected'] for case in examples['cases'])
    links = 0
    for doc in [ROOT / 'docs/ADR/0026-course-quality-and-learning-evidence.md', PACKAGE / 'contract.md']:
        for target in re.findall(r'\]\(([^)]+)\)', doc.read_text()):
            assert (doc.parent / target.split('#')[0]).exists(), (doc, target)
            links += 1
    manifest = json.loads((PACKAGE / 'manifest.json').read_text())
    for item in manifest['files']:
        assert hashlib.sha256((ROOT / item['path']).read_bytes()).hexdigest() == item['sha256']
    print(f'PASS: OpenAPI structure, {len(refs)} refs, {len(operations)} planned operations, '
          f'{len(schemas)} schemas, {len(cases)} schema examples, shared-budget consistency, '
          f'{len(examples["cases"])} design cases, {links} links, {len(manifest["files"])} frozen files; '
          'no runtime verification')


if __name__ == '__main__':
    main()
