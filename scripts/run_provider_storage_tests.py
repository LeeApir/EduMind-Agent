"""Run migration roundtrip and tests in a new dedicated Phase 1 PG database."""
import re
import subprocess
import sys
from pathlib import Path

from run_catalog_db_tests import test_environment

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    database = sys.argv[1]
    if not re.fullmatch(r'edumind_catalog_phase1_[a-z0-9_]{1,30}', database):
        raise ValueError('Dedicated Phase 1 test database required')
    env = test_environment(database)
    env = {k: v for k, v in env.items() if not k.startswith('EDUMIND_CREDENTIAL')}
    env['EDUMIND_PRODUCT_MODE'] = 'catalog_only'
    commands = [
        ['-m', 'alembic', 'upgrade', 'head'],
        ['-m', 'alembic', 'downgrade', '0017_catalog_immutability'],
        ['-m', 'alembic', 'upgrade', 'head'],
        ['-m', 'pytest', '-q', *(sys.argv[2:] or ['tests/test_provider_connections_persistence.py'])],
    ]
    for command in commands:
        subprocess.run([sys.executable, *command], cwd=ROOT / 'backend', env=env, check=True)
    print('Dedicated migration roundtrip and actual PostgreSQL tests passed; Provider requests 0')


if __name__ == '__main__':
    main()
