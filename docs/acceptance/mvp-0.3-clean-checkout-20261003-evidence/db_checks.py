import os, sys, subprocess, json, time
from pathlib import Path
ROOT=Path('/Users/apir/.codex/worktrees/mvp03-clean-checkout/EduMind_Agent')
OUT=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'scripts'),str(ROOT/'backend')]
from run_catalog_db_tests import test_environment
env=test_environment('edumind_catalog_clean_checks_20261003')
env['EDUMIND_PRODUCT_MODE']='catalog_only'
env['PYTHONPATH']=str(ROOT/'backend')
commands=[('migration',[sys.executable,'-m','alembic','upgrade','head']),('catalog-db',[sys.executable,str(OUT/'guarded_pytest.py')])]
for name,cmd in commands:
    started=time.monotonic()
    p=subprocess.run(cmd,cwd=ROOT/'backend',env=env,capture_output=True,text=True)
    (OUT/(name+'.log')).write_text(p.stdout+p.stderr)
    row={'name':name,'command':cmd,'cwd':'backend','database':'edumind_catalog_clean_checks_20261003','exit_code':p.returncode,'seconds':round(time.monotonic()-started,3),'log':name+'.log'}
    (OUT/(name+'.json')).write_text(json.dumps(row,indent=2)+'\n')
    print(json.dumps(row)); print((p.stdout+p.stderr)[-4000:],flush=True)
    if p.returncode: sys.exit(p.returncode)
