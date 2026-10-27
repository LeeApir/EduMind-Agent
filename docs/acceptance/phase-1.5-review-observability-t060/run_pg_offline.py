import os, subprocess, sys
from urllib.parse import quote
container='edumind-phase1-t037-pg'
assert subprocess.run(['docker','inspect','--format','{{index .Config.Labels "edumind.test-only"}}',container],capture_output=True,text=True,check=True).stdout.strip()=='phase1-dsl'
task=sys.argv[1]; assert task in ('t060','t061')
database='edumind_catalog_p15_t020_'+task+'_offline'
exists=subprocess.run(['docker','exec',container,'psql','-U','edumind_test','-d','postgres','-tAc',"SELECT 1 FROM pg_database WHERE datname='"+database+"'"],capture_output=True,text=True,check=True)
if exists.stdout.strip()!='1': subprocess.run(['docker','exec',container,'createdb','-U','edumind_test',database],check=True)
pw=subprocess.run(['docker','exec',container,'printenv','POSTGRES_PASSWORD'],capture_output=True,text=True,check=True).stdout.strip()
env=dict(os.environ,EDUMIND_TEST_DATABASE_URL='postgresql+asyncpg://edumind_test:'+quote(pw,safe='')+'@127.0.0.1:15437/'+database)
files=sys.argv[2:]
sys.exit(subprocess.run(['backend/.venv/bin/python','-m','pytest',*files,'-q','--junitxml=/tmp/edumind-'+task+'-pg.xml'],env=env).returncode)
