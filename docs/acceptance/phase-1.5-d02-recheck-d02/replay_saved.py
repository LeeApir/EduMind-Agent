"""Offline engineering replay of original d01 bytes; never changes original ledger or truth."""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT/'backend'),str(ROOT/'scripts')]
from isolated_diagnostics import p15_review_turn_metadata as proposed
from isolated_diagnostics import p15_review_observability as original

out=Path('/tmp/edumind-p15-d02-recheck-d01')
db=sqlite3.connect((out/'ledger.sqlite').as_uri()+'?mode=ro',uri=True)
try:
    calls=[json.loads(r[0]) for r in db.execute("SELECT body FROM receipts WHERE kind='live_dispatch_reserved' ORDER BY seq")]
    call=next(c for c in calls if c['provider']=='review');ticket=call['ticket']
    req_raw=(out/(ticket+'-request.json')).read_bytes();res_raw=(out/(ticket+'-response.json')).read_bytes()
    assert hashlib.sha256(req_raw).hexdigest()==call['request_sha256']
    req,res=json.loads(req_raw),json.loads(res_raw);payload=json.loads(req['input'][-1]['content'])
    before=hashlib.sha256(res_raw).hexdigest()
    try: original.ReviewObservationAdapter.validate_scene(req,res,payload)
    except ValueError as exc:old_error=str(exc)
    else:raise AssertionError('Original rejection missing')
    checked=proposed.ReviewObservationAdapter.validate_scene(req,res,payload)
    assert hashlib.sha256((out/(ticket+'-response.json')).read_bytes()).hexdigest()==before
    assert db.execute("SELECT state,reason FROM batches").fetchone()==('stopped','UNKNOWN_SEND')
    result=dict(original_request_sha256=hashlib.sha256(req_raw).hexdigest(),original_response_sha256=before,
        original_rejection=old_error,proposed_engineering_replay_accepted=True,
        raw_unchanged=True,old_batch_unchanged=True,old_unknown_released=False,
        raw_opinion_not_retroactively_admitted=True,independent_quality_pass=False,
        reasoning_turn_metadata_quarantined=checked['reasoning_turn_metadata_quarantined'],
        turn_metadata_identity_verified=checked['turn_metadata_identity_verified'],real_requests=0)
    (Path(__file__).parent/'replay.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(result,ensure_ascii=False))
finally:db.close()
