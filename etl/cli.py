import argparse
import json
import os
from pathlib import Path

from etl.config import ROOT,database_url


def migrate(test=False):
    from alembic import command
    from alembic.config import Config
    import psycopg
    target=database_url(test=True) if test else database_url(admin=True)
    before=os.environ.get('DATABASE_ADMIN_URL')
    try:
        os.environ['DATABASE_ADMIN_URL']=target
        command.upgrade(Config(str(ROOT/'alembic.ini')),'head')
    finally:
        if before is None:
            os.environ.pop('DATABASE_ADMIN_URL',None)
        else:
            os.environ['DATABASE_ADMIN_URL']=before
    with psycopg.connect(target) as conn:
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='company_ingest'").fetchone():
            conn.execute('GRANT USAGE ON SCHEMA raw,core,staging TO company_ingest')
            conn.execute('GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA raw,core,staging TO company_ingest')
            conn.execute('GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA raw TO company_ingest')
            if conn.execute("SELECT 1 FROM pg_namespace WHERE nspname='analytics'").fetchone():
                conn.execute('GRANT USAGE ON SCHEMA analytics TO company_ingest')
                conn.execute('GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA analytics TO company_ingest')
            if conn.execute("SELECT 1 FROM pg_namespace WHERE nspname='research'").fetchone():
                conn.execute('GRANT USAGE ON SCHEMA research TO company_ingest')
                conn.execute('GRANT SELECT,INSERT ON ALL TABLES IN SCHEMA research TO company_ingest')
        if conn.execute("SELECT 1 FROM pg_roles WHERE rolname='company_api'").fetchone():
            conn.execute('GRANT SELECT ON ALL TABLES IN SCHEMA raw,core,staging,analytics,research TO company_api')
    print('Migrations applied to '+('test' if test else 'application')+' database.')


def status():
    import psycopg
    with psycopg.connect(database_url()) as conn:
        conn.isolation_level=psycopg.IsolationLevel.REPEATABLE_READ
        result={table:conn.execute('SELECT count(*) FROM '+table).fetchone()[0] for table in
            ['raw.object','raw.capture','raw.record','raw.quality_issue','core.company','core.company_snapshot','staging.financial_record','staging.relationship_snapshot','staging.company_year_conflicts']}
        result['batches']=[{'id':str(r[0]),'status':r[1]} for r in conn.execute('''
            SELECT DISTINCT ON (b.id) b.id,e.status FROM raw.ingestion_batch b
            JOIN raw.ingestion_event e ON e.batch_id=b.id ORDER BY b.id,e.id DESC''').fetchall()]
    print(json.dumps(result,indent=2))


def main():
    parser=argparse.ArgumentParser()
    sub=parser.add_subparsers(dest='command',required=True)
    m=sub.add_parser('migrate')
    m.add_argument('--test',action='store_true')
    ing=sub.add_parser('ingest')
    ing.add_argument('--source',type=Path,default=ROOT/'firmy_b')
    ing.add_argument('--manifest',type=Path,default=ROOT/'data/audit/source_manifest.json')
    ing.add_argument('--store',type=Path,default=ROOT/'data/raw/objects')
    sub.add_parser('status')
    v=sub.add_parser('verify')
    v.add_argument('--batch',required=True)
    v.add_argument('--source',type=Path)
    v.add_argument('--output',type=Path,default=ROOT/'data/ingest/verification.json')
    t=sub.add_parser('trace')
    t.add_argument('--record',required=True)
    t.add_argument('--field',required=True)
    d=sub.add_parser('diagnose')
    d.add_argument('--batch',required=True)
    d.add_argument('--output',type=Path,default=ROOT/'data/ingest/candidate_diagnostics.json')
    b=sub.add_parser('build-panel')
    b.add_argument('--batch',required=True)
    b.add_argument('--output',type=Path,default=ROOT/'data/analytical')
    report=sub.add_parser('report-panel')
    report.add_argument('--dataset',required=True)
    vp=sub.add_parser('verify-panel')
    vp.add_argument('--dataset',required=True)
    lineage=sub.add_parser('trace-feature')
    lineage.add_argument('--dataset',required=True)
    lineage.add_argument('--krs',required=True)
    lineage.add_argument('--year',type=int,required=True)
    lineage.add_argument('--feature',required=True)
    research=sub.add_parser('run-research')
    research.add_argument('--dataset',required=True)
    research.add_argument('--allow-provisional',action='store_true')
    rr=sub.add_parser('report-research')
    rr.add_argument('--run',required=True)
    diagnostics=sub.add_parser('diagnose-research')
    diagnostics.add_argument('--run',required=True)
    args=parser.parse_args()
    if args.command=='migrate':
        migrate(args.test)
    elif args.command=='ingest':
        from etl.ingest import run_ingest
        print('Batch: '+run_ingest(database_url(),args.source,args.manifest,args.store))
    elif args.command=='verify':
        from etl.verify import verify
        from etl.parsing import dumps
        result=verify(database_url(),args.batch,args.source)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(dumps(result),encoding='utf-8')
        print(json.dumps(result,indent=2))
    elif args.command=='trace':
        from etl.verify import trace
        from etl.parsing import dumps
        print(dumps(trace(database_url(),args.record,args.field)))
    elif args.command=='diagnose':
        from etl.diagnose import diagnose
        result=diagnose(database_url(),args.batch)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2,default=str,ensure_ascii=False),encoding='utf-8')
        print(json.dumps({k:v for k,v in result.items() if k!='conflicts'},indent=2))
    elif args.command=='build-panel':
        from analytics.build import build
        print('Dataset: '+build(database_url(),args.batch,args.output))
    elif args.command=='report-panel':
        from analytics.report import report
        report(database_url(),args.dataset)
    elif args.command=='verify-panel':
        from analytics.verify import verify_panel
        result=verify_panel(database_url(),args.dataset)
        path=ROOT/'data/research'/args.dataset
        path.mkdir(parents=True,exist_ok=True)
        (path/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    elif args.command=='trace-feature':
        from analytics.lineage import feature_trace
        from etl.parsing import dumps
        print(dumps(feature_trace(database_url(),args.dataset,args.krs,args.year,args.feature)))
    elif args.command=='run-research':
        from research.run import run
        run(database_url(),args.dataset,args.allow_provisional)
    elif args.command=='report-research':
        from research.report import render
        render(database_url(),args.run)
    elif args.command=='diagnose-research':
        from research.diagnostics import diagnose
        diagnose(database_url(),args.run)
    else:
        status()


if __name__=='__main__':
    main()
