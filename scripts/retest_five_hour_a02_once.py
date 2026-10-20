"""One exact-wire replay of the stopped A02 unit review; no generation or retry."""
# ruff: noqa: E402
import asyncio
from dataclasses import asdict
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'scripts'), str(ROOT / 'backend')]
import run_five_hour_remaining as previous
from jsonschema import Draft202012Validator
from acceptance_support.five_hour_runtime import RunLedger, private_directory, read_json, require, write_once
from acceptance_support.qwen_review_budget import canonical, sha
from app.core.config import ProviderSettings
from app.core.provider_target import ProviderTargetGuard, TargetPolicy
from app.services.deepseek_responses import DeepSeekResponsesAdapter

P = previous.parent
PUBLIC = ROOT / 'docs/acceptance/phase-1-five-hour-a02-retest-r01'
PRIVATE = ROOT / 'local-materials/phase-1-five-hour-a02-retest-r01'
OLD = previous.PRIVATE / 'A02'

class SingleLedger(RunLedger):
    def reserve(self, name, request_hash):
        require(not self.snapshot()['calls'], 'SINGLE_REQUEST_EXHAUSTED')
        return super().reserve(name, request_hash)

async def run():
    _, _, original = previous.authorize()
    manifest = read_json(PUBLIC / 'manifest.json')
    for name, digest in manifest['files'].items():
        require(sha((ROOT / name).read_bytes()) == digest, 'RETEST_FREEZE_CHANGED')
    terminal = read_json(previous.PACKAGE / 'terminal.json')
    require(sha((previous.PRIVATE / 'run.sqlite').read_bytes()) == terminal['ledger_sha256'], 'OLD_LEDGER_CHANGED')
    require(manifest['source_user_message'] == '重测一次A02' and manifest['max_requests'] == 1, 'EXPLICIT_ONE_CALL_REQUIRED')
    request = read_json(OLD / '18-request.json')
    require(sha(canonical(request)) == manifest['original_request_sha256'], 'ORIGINAL_REQUEST_CHANGED')
    body = json.loads(bytes.fromhex(request['wire_hex']))
    require(body['reasoning'] == {'effort':'high'} and body['max_output_tokens'] == 8192, 'CONFIG_CHANGED')
    keys = P.load_keys(original['env_metadata'])
    private_directory(PRIVATE)
    require(not (PRIVATE / 'run.sqlite').exists(), 'NO_REPLAY')
    previous.kernel.ORDER = ['A02']
    ledger = SingleLedger(PRIVATE / 'run.sqlite', sha(canonical(manifest)), t0=original['preparation_t0_epoch'])
    ledger.start_case('A02')
    directory = private_directory(PRIVATE / 'A02')
    private_directory(PRIVATE / 'requests')
    write_once(PRIVATE / 'requests/A02-plan.json', request)
    # AuditTransport's first-wire guard checks this immutable replay wire, not a new plan.
    P.BASE = PRIVATE
    context = dict(case='A02', ledger=ledger, directory=directory, keys=keys, call_ids=[], completed=[], logical_input_sha256=request['logical_input_sha256'], business_schema=request['business_schema'])
    target = await asyncio.to_thread(ProviderTargetGuard(P.CONFIG.review_base, TargetPolicy()).approve_base)
    transport = P.AuditTransport(context, P.CONFIG.review_base, P.CONFIG.review_model, 'high', target)
    adapter = DeepSeekResponsesAdapter(ProviderSettings(P.CONFIG.review_base, keys[1], P.CONFIG.review_model), SimpleNamespace(approve_base=lambda:target), transport=transport, reasoning_effort='high')
    try:
        async with asyncio.timeout(60):
            text = await adapter._response(body)
        value = json.loads(text.text)
        Draft202012Validator(request['business_schema']).validate(value)
        require(text.model_id == P.CONFIG.review_model, 'RETURNED_MODEL_CHANGED')
        parsed = dict(model=text.model_id, value=value, usage=asdict(text.usage) if text.usage else None, transport_audit=asdict(text.transport_audit))
        write_once(directory / '01-parsed.json', parsed)
        old = read_json(OLD / 'result.json')
        review = next(r for r in old['reviews'] if r['result']['scope']=='unit')
        review = dict(review, review_id=str(uuid4()), result=value, response_digest=text.transport_audit.response_digest)
        review['local_routing'] = dict(review['local_routing'], verdict=value['verdict'], reason_codes=[])
        path = directory / ('review-'+review['review_id']+'.json')
        write_once(path, review)
        result = dict(case_id='A02', actual_call_count=1, call_ids=[1], course_state=None, original_course_state=old['course_state'], reviews=[review], review_artifact_paths=[str(path.relative_to(ROOT))], resources=old['resources'], plans=old['plans'], production_publish_performed=False, new_code_executed=False, scope='exact old unit-review wire replay; no generation, database write, correction or publication')
        result['artifact_hashes']={str(p.relative_to(ROOT)):sha(p.read_bytes()) for p in directory.iterdir() if p.is_file()}
        digest=write_once(directory/'result.json',result)
        ledger.finish_case('A02',digest)
        print(json.dumps(dict(verdict=value['verdict'], calls=1, state='awaiting_gpt', usage=parsed['usage'])))
    finally:
        ledger.stop('SINGLE_RETEST_FINISHED_NO_FURTHER_CALLS')
        await transport.aclose()

if __name__ == '__main__':
    asyncio.run(run())
