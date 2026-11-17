"""Check proposal structure only; never asserts runtime behavior or approval."""
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[3]
PACKAGE = Path(__file__).resolve().parent
API = ROOT / 'docs/api/phase-1.5-free-course.openapi.json'


def main():
    api = json.loads(API.read_text())
    count = 0

    def visit(value):
        nonlocal count
        if isinstance(value, dict):
            if '$ref' in value:
                target = api
                assert value['$ref'].startswith('#/'), value['$ref']
                for part in value['$ref'][2:].split('/'):
                    target = target[part.replace('~1', '/').replace('~0', '~')]
                count += 1
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(api)
    for schema in api['components']['schemas'].values():
        Draft202012Validator.check_schema(schema)
    operations = []
    for path in api['paths'].values():
        for operation in path.values():
            assert operation['x-runtime-status'] == 'planned'
            assert operation['security'] == [{'sessionCookie': []}]
            operations.append(operation['operationId'])
    assert len(operations) == len(set(operations)) == 6
    validator = Draft202012Validator(api['components']['schemas']['CreateCourse'])
    for example in [{'goal': '学习链表'}, {'goal': '指针', 'code_language': None}]:
        validator.validate(example)
    for example in [
        {}, {'goal': ''}, {'goal': 'x' * 4001}, {'goal': 'x', 'owner_id': 'foreign'},
        {'goal': 'x', 'endorsement': 'approved'}, {'goal': 'x', 'code_language': 'python'},
    ]:
        assert list(validator.iter_errors(example)), example
    examples = json.loads((PACKAGE / 'examples.json').read_text())
    assert examples['status'] == 'design_cases_not_runtime_results'
    ids = [case['id'] for case in examples['cases']]
    assert len(ids) == len(set(ids)) == 25
    assert all(case['given'] and case['expected'] for case in examples['cases'])
    docs = [ROOT / 'docs/ADR/0024-free-course-identity-and-owner-access.md', PACKAGE / 'contract.md']
    links = 0
    for doc in docs:
        for target in re.findall(r'\]\(([^)]+)\)', doc.read_text()):
            assert (doc.parent / target.split('#')[0]).exists(), (doc, target)
            links += 1
    manifest = json.loads((PACKAGE / 'manifest.json').read_text())
    import hashlib
    for item in manifest['files']:
        path = ROOT / item['path']
        assert hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], path
    print(f'PASS: {count} local refs, 6 planned operations, {len(api["components"]["schemas"])} schemas, 8 request examples, '
          f'25 design cases, {links} links, {len(manifest["files"])} frozen files; no runtime verification')


if __name__ == '__main__':
    main()
