import os,subprocess,sys
from urllib.parse import quote
pw=subprocess.run(['docker','exec','edumind-phase1-t037-pg','printenv','POSTGRES_PASSWORD'],capture_output=True,text=True,check=True).stdout.strip()
env=dict(os.environ,EDUMIND_TEST_DATABASE_URL='postgresql+asyncpg://edumind_test:'+quote(pw,safe='')+'@127.0.0.1:15437/edumind_catalog_p15_t020_full_r04_offline')
sys.exit(subprocess.run(['backend/.venv/bin/python','-m','pytest','backend/tests/test_p15_full_diagnostic_r04.py','-q','--junitxml=/tmp/edumind-p15-full-r04-pg.xml'],env=env).returncode)
