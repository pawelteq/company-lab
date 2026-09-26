"""Manage a loopback-only project PostgreSQL cluster; never installs a Windows service."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
from urllib.parse import quote, urlparse, unquote

ROOT=Path(__file__).resolve().parents[1]
LOCAL=ROOT/'.local'
BIN=LOCAL/'postgresql'/'pgsql'/'bin'
CLUSTER=LOCAL/'pgdata'
PORT=55432


def run(*args):
    subprocess.run([str(x) for x in args],check=True,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))


def main(action):
    if action=='setup':
        if CLUSTER.exists():
            raise RuntimeError('Cluster already exists; use start/status. Setup never overwrites a database.')
        LOCAL.mkdir(exist_ok=True)
        password=secrets.token_urlsafe(32)
        ingest_password=secrets.token_urlsafe(32)
        pw=LOCAL/'init-password.tmp'
        pw.write_text(password,encoding='utf-8')
        try:
            run(BIN/'initdb.exe','-D',CLUSTER,'-U','company_admin','--pwfile',pw,'--auth=scram-sha-256','--encoding=UTF8','--locale=C')
        finally:
            pw.unlink(missing_ok=True)
        with (CLUSTER/'postgresql.conf').open('a',encoding='utf-8') as f:
            f.write(f"\nlisten_addresses = '127.0.0.1'\nport = {PORT}\nshared_buffers = '128MB'\n")
        config={
            'DATABASE_ADMIN_URL':f'postgresql://company_admin:{quote(password)}@127.0.0.1:{PORT}/company_lab',
            'DATABASE_URL':f'postgresql://company_ingest:{quote(ingest_password)}@127.0.0.1:{PORT}/company_lab',
            'TEST_DATABASE_URL':f'postgresql://company_admin:{quote(password)}@127.0.0.1:{PORT}/company_lab_test',
        }
        (LOCAL/'database.json').write_text(json.dumps(config,indent=2),encoding='utf-8')
        run(BIN/'pg_ctl.exe','-D',CLUSTER,'-l',LOCAL/'postgres.log','-w','start')
        provision()
    elif action=='start':
        run(BIN/'pg_ctl.exe','-D',CLUSTER,'-l',LOCAL/'postgres.log','-w','start')
    elif action=='stop':
        run(BIN/'pg_ctl.exe','-D',CLUSTER,'-m','fast','-w','stop')
    elif action=='status':
        run(BIN/'pg_ctl.exe','-D',CLUSTER,'status')
    elif action=='provision':
        provision()
    elif action=='rotate-passwords':
        rotate_passwords()


def rotate_passwords():
    import psycopg
    from psycopg import sql
    path=LOCAL/'database.json'
    config=json.loads(path.read_text(encoding='utf-8'))
    updated=dict(config)
    roles=['company_admin','company_ingest']+(['company_api'] if 'API_DATABASE_URL' in config else [])
    passwords={role:secrets.token_urlsafe(32) for role in roles}
    for key,url in config.items():
        parsed=urlparse(url)
        updated[key]=f'{parsed.scheme}://{parsed.username}:{quote(passwords[parsed.username])}@{parsed.hostname}:{parsed.port}{parsed.path}'
    pending=LOCAL/'database.pending.json'
    pending.write_text(json.dumps(updated,indent=2),encoding='utf-8')
    with psycopg.connect(config['DATABASE_ADMIN_URL']) as conn:
        for role,password in passwords.items():
            conn.execute(sql.SQL('ALTER ROLE {} PASSWORD {}').format(sql.Identifier(role),sql.Literal(password)))
    pending.replace(path)
    print('Local database passwords rotated; configuration updated without displaying credentials.')


def provision():
    import psycopg
    from psycopg import sql
    config=json.loads((LOCAL/'database.json').read_text(encoding='utf-8'))
    password=unquote(urlparse(config['DATABASE_URL']).password)
    with psycopg.connect(config['DATABASE_ADMIN_URL'].rsplit('/',1)[0]+'/postgres',autocommit=True) as conn:
        if not conn.execute("SELECT 1 FROM pg_roles WHERE rolname='company_ingest'").fetchone():
            conn.execute(sql.SQL('CREATE ROLE company_ingest LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE').format(sql.Literal(password)))
        for name in ['company_lab','company_lab_test']:
            if not conn.execute('SELECT 1 FROM pg_database WHERE datname=%s',(name,)).fetchone():
                conn.execute(sql.SQL('CREATE DATABASE {} OWNER company_admin').format(sql.Identifier(name)))
    print('Local application/test databases ready on 127.0.0.1:55432. Credentials remain in .local/database.json (ignored).')


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=['setup','start','stop','status','provision','rotate-passwords'])
    main(parser.parse_args().action)
