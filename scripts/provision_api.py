"""Create a dedicated SELECT-only local API login. No credentials in output."""
import json
import secrets
from urllib.parse import urlparse, quote
import psycopg
from psycopg import sql
from etl.config import ROOT, database_url


def provision():
    path=ROOT/'.local/database.json'
    config=json.loads(path.read_text(encoding='utf-8'))
    password=secrets.token_urlsafe(32)
    parsed=urlparse(database_url(admin=True))
    with psycopg.connect(database_url(admin=True)) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='company_api'").fetchone():
            conn.execute('CREATE ROLE company_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE')
        conn.execute(sql.SQL('ALTER ROLE company_api PASSWORD {}').format(sql.Literal(password)))
        conn.execute('ALTER ROLE company_api SET default_transaction_read_only = on')
        conn.execute('GRANT USAGE ON SCHEMA raw,core,staging,analytics,research TO company_api')
        conn.execute('GRANT SELECT ON ALL TABLES IN SCHEMA raw,core,staging,analytics,research TO company_api')
    config['API_DATABASE_URL']=f'postgresql://company_api:{quote(password)}@{parsed.hostname}:{parsed.port}{parsed.path}'
    pending=path.with_suffix('.api.pending.json')
    pending.write_text(json.dumps(config,indent=2),encoding='utf-8')
    pending.replace(path)
    print('SELECT-only API role configured. Credentials stored locally; no source data changed.')


if __name__=='__main__':
    provision()
