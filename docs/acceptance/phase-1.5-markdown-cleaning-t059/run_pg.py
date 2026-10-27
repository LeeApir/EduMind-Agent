import os,subprocess,sys
from urllib.parse import quote
cases={'new':('edumind_catalog_p15_t020_markdown_t059','backend/tests/test_free_scene_markdown_pg.py'),'old':('edumind_catalog_p15_t011_markdown_t059','backend/tests/test_free_scene_validation.py'),'ready':('edumind_catalog_p15_t013_markdown_t059','backend/tests/test_free_scene_availability.py')}
role='edumind_test'
pw=subprocess.run(['docker','exec','edumind-phase1-t037-pg','printenv','POSTGRES_PASSWORD'],capture_output=True,text=True,check=True).stdout.strip()
case=sys.argv[1];database,test=cases[case]
if len(sys.argv)>2 and sys.argv[2]=='create':
 sys.exit(subprocess.run(['docker','exec','edumind-phase1-t037-pg','createdb','-U',role,database]).returncode)
env=dict(os.environ,EDUMIND_TEST_DATABASE_URL='postgresql+asyncpg://'+role+':'+quote(pw,safe='')+'@127.0.0.1:15437/'+database)
sys.exit(subprocess.run(['backend/.venv/bin/python','-m','pytest',test,'-q','--junitxml=/tmp/edumind-p15-t059-'+case+'.xml'],env=env).returncode)
