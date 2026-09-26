import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DatabaseURL(str):
    def __repr__(self):
        return '<database URL redacted>'


def database_url(*, admin=False, test=False, api=False):
    key = 'API_DATABASE_URL' if api else ('TEST_DATABASE_URL' if test else ('DATABASE_ADMIN_URL' if admin else 'DATABASE_URL'))
    if value := os.environ.get(key):
        return DatabaseURL(value)
    local = ROOT/'.local'/'database.json'
    if local.exists():
        config=json.loads(local.read_text(encoding='utf-8'))
        return DatabaseURL(config[key])
    raise RuntimeError(f'Set {key} or run scripts/local_postgres.py setup. Credentials are never stored in tracked files.')
