from pathlib import Path
import os,sys,subprocess,json,time
ROOT=Path('/Users/apir/.codex/worktrees/mvp03-main-review/EduMind_Agent')
OUT=Path(__file__).resolve().parent
name,directory,*cmd=sys.argv[1:]
env={k:v for k,v in os.environ.items() if not k.startswith(('EDUMIND_PROVIDER','EDUMIND_REVIEW_CANDIDATE')) and k not in ('EDUMIND_DATABASE_URL','EDUMIND_TEST_DATABASE_URL','EDUMIND_DOCKER_TESTS')}
env['EDUMIND_PRODUCT_MODE']='catalog_only'
started=time.monotonic();p=subprocess.run(cmd,cwd=ROOT/directory,env=env,capture_output=True,text=True)
(OUT/(name+'.txt')).write_text(p.stdout+p.stderr)
row={'command':cmd,'cwd':directory,'exit_code':p.returncode,'seconds':round(time.monotonic()-started,3),'raw_log':name+'.txt'}
(OUT/(name+'.json')).write_text(json.dumps(row,indent=2)+'\n');print(json.dumps(row));print((p.stdout+p.stderr)[-4500:]);raise SystemExit(p.returncode)
