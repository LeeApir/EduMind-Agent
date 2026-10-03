"""Offline OpenAPI integrity and secret/consent example validation."""
import json
from copy import deepcopy
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]


def check_contract() -> dict[str, int]:
    doc = json.loads((ROOT / 'docs/api/openapi.yaml').read_text())
    operation_ids: set[str] = set()
    refs = 0

    def walk(value: object) -> None:
        nonlocal refs
        if isinstance(value, dict):
            for key, item in value.items():
                if key == '$ref':
                    assert isinstance(item, str) and item.startswith('#/'), item
                    resolved: object = doc
                    for part in item[2:].split('/'):
                        assert isinstance(resolved, dict)
                        resolved = resolved[part.replace('~1', '/').replace('~0', '~')]
                    refs += 1
                else:
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)

    walk(doc)
    schema_doc = {'$schema': 'https://json-schema.org/draft/2020-12/schema', **doc}
    registry = Registry().with_resource('urn:edumind:contract', Resource.from_contents(schema_doc))
    examples = 0
    for path, methods in doc['paths'].items():
        for method, operation in methods.items():
            if method not in {'get', 'post', 'put', 'patch', 'delete'}:
                continue
            oid = operation['operationId']
            assert oid not in operation_ids, oid
            operation_ids.add(oid)
            if 'x-implementation-task' not in operation:
                continue
            assert operation['x-runtime-status'] == 'planned'
            assert operation['security'] == [{'sessionCookie': []}]
            if method != 'get':
                assert any(p.get('$ref', '').endswith('/CsrfToken') for p in operation['parameters'])
            if method in {'patch', 'delete'}:
                assert any(p.get('name') == 'If-Match' for p in operation['parameters'])
            for container in [operation.get('requestBody', {}), *operation['responses'].values()]:
                for content in container.get('content', {}).values():
                    if 'example' not in content:
                        continue
                    schema = content['schema']
                    if '$ref' in schema:
                        schema = {'$ref': 'urn:edumind:contract' + schema['$ref']}
                    Draft202012Validator(schema, registry=registry).validate(content['example'])
                    examples += 1
    schemas = doc['components']['schemas']
    for name, schema in schemas.items():
        if name.startswith(('Provider', 'TemporaryCredential', 'ModelPreference')):
            Draft202012Validator.check_schema(schema)
    create = doc['paths']['/api/providers/connections']['post']['requestBody']['content']['application/json']['example']
    validator = Draft202012Validator({'$ref': 'urn:edumind:contract#/components/schemas/ProviderConnectionCreate'}, registry=registry)
    invalid = deepcopy(create)
    invalid['user_id'] = 'someone-else'
    assert not validator.is_valid(invalid)
    invalid = deepcopy(create)
    del invalid['secret']
    assert not validator.is_valid(invalid)
    invalid = deepcopy(create)
    invalid['credential_mode'] = 'temporary'
    assert not validator.is_valid(invalid)
    del invalid['secret']
    assert validator.is_valid(invalid)
    invalid['is_local'] = True
    assert not validator.is_valid(invalid)
    consent = Draft202012Validator({'$ref': 'urn:edumind:contract#/components/schemas/ProviderDataConsent'}, registry=registry)
    assert not consent.is_valid({'accepted': False, 'config_version': 1, 'model_id': 'test', 'data_categories': ['probe']})
    view = schemas['ProviderConnection']['properties']
    assert not {'secret', 'api_key', 'encrypted_api_key', 'user_id', 'originating_session_hash'} & set(view)
    assert schemas['ProviderConnection']['additionalProperties'] is False
    assert schemas['ProviderSecret']['writeOnly'] is True
    for key in schemas['ProviderCapability']['properties']:
        if key not in {'source', 'version'}:
            assert schemas['ProviderCapability']['properties'][key]['type'] == ['boolean', 'null']
    assert 'get' not in doc['paths']['/api/providers/connections/{connection_id}/models/refresh']
    return {'references': refs, 'unique_operations': len(operation_ids), 'validated_examples': examples}


if __name__ == '__main__':
    print(json.dumps(check_contract()))
