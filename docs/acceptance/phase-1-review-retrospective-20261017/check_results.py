import json,re,sqlite3,hashlib,subprocess,sys
from pathlib import Path
base=Path(__file__).resolve().parent
root=base.parents[2]
e=json.loads((base/'evidence.json').read_text());legacy=json.loads((base/'legacy-results.json').read_text());p=json.loads((base/'planning-assumptions.json').read_text())
rows=e['attempts'];s=e['summary']
assert len(rows)==s['reservation_attempts']==27 and len(e['configuration_results'])==s['run_count']==18
assert sum(r['confirmed_sends'] or 0 for r in rows)==25
assert sum(r['confirmed_sends'] is None for r in rows)==1 and sum(r['confirmed_sends']==0 for r in rows)==1
assert sum(r['role']=='generation' for r in rows)==1
assert sum(r['role']=='review' and r['wire_schema_complete']=='pass' for r in rows)==20
assert sum(r['role']=='review' and r['business_protocol']=='pass' for r in rows)==18
known=[r for r in rows if r['input_tokens'] is not None and r['output_tokens'] is not None]
assert len(known)==23 and sum(r['input_tokens']+r['output_tokens'] for r in known)==333398
assert sum(x['real_requests'] for x in legacy['rounds'])==16
for item in e['ledger_snapshots'] + e['legacy_ledger_snapshots']:
 c=sqlite3.connect((root/'local-materials'/item['run']/'budget.sqlite').resolve().as_uri()+'?mode=ro',uri=True)
 assert [list(x) for x in c.execute('select number,slot,stage,target,request_sha256,cost_micro,state,input_tokens,output_tokens,error_code,input_bound,output_bound from attempts order by number')]==item['rows']
 assert c.execute('select halted from run where id=1').fetchone()[0]==item['halted'];c.close()
for item in legacy['rounds']:
 assert hashlib.sha256((root/item['evidence']).read_bytes()).hexdigest()==item['evidence_sha256']
for item in e['configuration_results']:assert (root/item['evidence']).is_file()
w=p['workload'];f=w['opinion_formula']
for key in ['fact_example','mixed_example']:
 example=w[key];mins=[]
 for i in [0,1]:mins.append(f['context_range'][i]+example['assertions_assumed']*f['minutes_per_assertion_range'][i]+example['citation_instances']*f['minutes_per_citation_instance_range'][i]+f['decision_range'][i])
 assert all(abs(a-b)<1e-9 for a,b in zip(mins,example['minutes_exact']))
x=p['optional_future_envelope'];assert x['screen_requests_max']+x['new_material_requests_max']==x['all_requests_max']==12
assert x['reservation_max_micro_CNY_each']==x['input_price_micro_CNY_per_token']*(x['input_budget_overhead_tokens']+x['raw_request_wire_bytes_max'])+x['output_price_micro_CNY_per_token']*x['total_output_reserved']
assert x['reservation_max_micro_CNY_all']==12*x['reservation_max_micro_CNY_each']<=x['hard_cost_micro_CNY']==164000000
assert not x['approved'] and not p['measured_human_times_available'] and p['recommendation_now']['provider_requests']==0
assert sum(w['calibration_proposed'][k] for k in ['summary_minutes'])+w['calibration_proposed']['existing_cases']*w['calibration_proposed']['max_minutes_each']==240
local_links=[]
for target in re.findall(r'\]\(([^)]+)\)',(base/'README.md').read_text()):
 if target.startswith(('https://','http://','#')):continue
 assert (base/target.split('#')[0]).resolve().is_file(),target
 local_links.append(target)
prior=subprocess.check_output(['git','ls-tree','-r','--name-only','14bba23','--','docs/acceptance'],cwd=root,text=True).splitlines()
for name in prior:assert (root/name).read_bytes()==subprocess.check_output(['git','show','14bba23:'+name],cwd=root)
sys.path[:0]=[str(root/'scripts'),str(root/'backend')]
import run_qwen_continuation as r
frozen,approval=r.load(root,stop_only=True)
snap=r.gate_for(frozen,approval,root).snapshot();assert snap['halted']=='INVALID_OUTPUT' and len(snap['attempts'])==2
meta=(root/'.env').stat();assert all(getattr(meta,k)==v for k,v in frozen['credential_file_metadata'].items())
result={'passed':True,'current_provider_calls':0,'configuration_rows':18,'ledger_attempts':27,'confirmed_sends':25,'unknown_send_attempts':1,'zero_send_preflight':1,'known_tokens':333398,'legacy_rounds':11,'legacy_real_requests':16,'linked_local_references_checked':len(local_links),'prior_acceptance_files_equal':len(prior),'historical_ledger_snapshots_unchanged':20,'runtime_frozen_sources_verified':len(frozen['sources']),'latest_halt':snap['halted'],'workload_formula_and_budget_arithmetic':'passed','credential_metadata_unchanged':True,'semantic_guarantee_not_inferred':True}
print(json.dumps(result))
(base/'checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
