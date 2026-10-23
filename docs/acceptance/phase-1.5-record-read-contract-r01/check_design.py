"""Validate proposed read-only schemas/examples and frozen bytes, no HTTP/DB calls."""
import hashlib,json
from pathlib import Path
from jsonschema import Draft202012Validator,FormatChecker
ROOT=Path(__file__).resolve().parents[3]
folder=ROOT/'docs/acceptance/phase-1.5-record-read-contract-r01'
spec=json.loads((ROOT/'docs/api/phase-1.5-record-read.proposed.openapi.json').read_text())
assert len(spec['paths'])==2
for methods in spec['paths'].values():
    assert set(methods)=={'get'}
    op=methods['get'];assert op['x-status']=='planned' and op['security']==[{'session':[]}]
    assert op['responses']['200']['headers']['Cache-Control']['schema']=={'const':'no-store'}
    limit=next(p['schema'] for p in op['parameters'] if p['name']=='limit');assert limit=={'type':'integer','minimum':1,'maximum':50,'default':20}
for model in spec['components']['schemas'].values():Draft202012Validator.check_schema(model);assert model['additionalProperties'] is False
examples=json.loads((folder/'examples.json').read_text());assert examples['synthetic_design_only']
for sample in examples['valid']:
    schema={'$ref':'#/components/schemas/'+sample['schema'],'components':spec['components']}
    validator=Draft202012Validator(schema,format_checker=FormatChecker());validator.validate(sample['value'])
    bad={**sample['value'],'raw_provider_response':'forbidden'}
    assert not validator.is_valid(bad)
for entry in json.loads((folder/'manifest.json').read_text())['files']:
    assert hashlib.sha256((ROOT/entry['path']).read_bytes()).hexdigest()==entry['sha256'],entry['path']
print(f'PASS proposed GET schemas/no-store/session/limits; {len(examples["valid"])} synthetic examples; unknown fields rejected; manifest integrity. No API/PG/Provider executed.')
