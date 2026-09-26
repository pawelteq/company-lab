"""Publish a complete exploratory snapshot with exact lineage and Parquet exports."""
from collections import Counter,defaultdict
from itertools import groupby
import gzip
import hashlib
import math
import platform
from pathlib import Path
import shutil
import tempfile

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import set_json_loads
import pyarrow as pa
import pyarrow.parquet as pq

from analytics.features import DEFINITIONS,FeatureEngine,choose,annual
from etl.config import ROOT
from etl.ingest import uid,js,copy_rows
from etl.parsing import dumps,loads
from etl.storage import digest_file

CONFIG={'selection':'unique_standalone_v1','feature_version':'reported_features_v1',
        'maturity':'exploratory_reported','research_ready':False,'cohorts':'available_distinct_years',
        'parquet_numbers':'float64; exact values in panel.jsonl.gz and PostgreSQL',
        'currency':'PLN; provider unit scale not independently verified','precision':28,
        'runtime':{'python':platform.python_version(),'pyarrow':pa.__version__}}


def fingerprint():
    files=[ROOT/'analytics/features.py',ROOT/'analytics/build.py']
    return hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest()


def companies(url,batch):
    with psycopg.connect(url,connect_timeout=10,row_factory=dict_row) as conn:
        set_json_loads(loads,conn)
        with conn.cursor(name='panel_source') as cur:
            cur.itersize=1000
            cur.execute('''SELECT f.*,co.krs FROM staging.financial_record f
                JOIN core.company co ON co.company_id=f.company_id
                JOIN raw.record r ON r.id=f.raw_record_id JOIN raw.capture c ON c.id=r.capture_id
                WHERE c.batch_id=%s ORDER BY f.company_id,f.fiscal_year,f.id''',(batch,))
            for cid,group in groupby(cur,key=lambda r:r['company_id']):
                yield cid,list(group)


def make_rows(cid,records):
    years=defaultdict(list)
    for r in records:
        if r['fiscal_year'] is None:
            raise ValueError('Missing fiscal year requires explicit policy, not silent omission')
        years[r['fiscal_year']].append(r)
    chosen={year:choose(rows) for year,rows in years.items()}
    selected={year:value[0] for year,value in chosen.items()}
    engine=FeatureEngine(selected)
    ny=len(years)
    ns=sum(v is not None for v in selected.values())
    na=sum(annual(v) for v in selected.values())
    for year in sorted(years):
        record,status=chosen[year]
        values,reasons=engine.row(year)
        yield {'company_id':str(cid),'krs':records[0]['krs'],'year':year,
            'selected_record_id':str(record['id']) if record else None,'selection_status':status,
            'candidates':[str(r['id']) for r in years[year]],'n_years':ny,'n_selected_years':ns,'n_annual_years':na,
            'panel_full':True,'panel_3plus':ny>=3,'panel_5plus':ny>=5,'panel_long':ny>=7,
            'features':values,'missing_reasons':reasons,
            'quality_codes':sorted(set((record['quality_codes'] if record else [])+['provider_mapping_unverified','retrospective_snapshot']))}


def parquet_schema():
    fields=[pa.field('company_id',pa.string()),pa.field('krs',pa.string()),pa.field('year',pa.int16()),
        pa.field('selected_record_id',pa.string()),pa.field('selection_status',pa.string()),
        *[pa.field(n,pa.int16()) for n in ['n_years','n_selected_years','n_annual_years']],
        *[pa.field(n,pa.bool_()) for n in ['panel_full','panel_3plus','panel_5plus','panel_long']],
        *[pa.field(n,pa.float64()) for n in DEFINITIONS],
        pa.field('missing_reasons',pa.string()),pa.field('quality_codes',pa.list_(pa.string()))]
    return pa.schema(fields,metadata={b'maturity':b'exploratory_reported',b'research_ready':b'false',
        b'numeric_precision':b'float64; exact values in database and panel.jsonl.gz'})


def flat(row):
    result={k:v for k,v in row.items() if k not in ['features','candidates']}
    result['missing_reasons']=dumps(row['missing_reasons'])
    for k,v in row['features'].items():
        numeric=float(v) if v is not None else None
        if numeric is not None and not math.isfinite(numeric):
            raise ValueError('Non-finite value cannot enter the analytical export')
        result[k]=numeric
    return result


def build(url,batch,output_root):
    output_root=output_root.resolve()
    output_root.mkdir(parents=True,exist_ok=True)
    code_hash=fingerprint()
    version_hash=hashlib.sha256(dumps({'batch':str(batch),'code':code_hash,'config':CONFIG,'definitions':DEFINITIONS}).encode()).hexdigest()
    dataset=uid('dataset',version_hash)
    final=output_root/str(dataset)
    with psycopg.connect(url,autocommit=True,connect_timeout=10) as conn:
        if not conn.execute('SELECT pg_try_advisory_lock(73111518)').fetchone()[0]:
            raise RuntimeError('Another panel build is running')
        existing=conn.execute('SELECT artifact_manifest FROM analytics.dataset WHERE id=%s',(dataset,)).fetchone()
        if existing:
            for item in existing[0]:
                if digest_file(Path(item['path']))!=(item['sha256'],item['bytes']):
                    raise ValueError('Existing dataset artifact is missing or changed')
            print('Existing immutable dataset verified: '+str(dataset))
            return str(dataset)
        state=conn.execute('SELECT status FROM raw.ingestion_event WHERE batch_id=%s ORDER BY id DESC LIMIT 1',(batch,)).fetchone()
        if not state or state[0]!='completed':
            raise ValueError('A completed source import is required')
        work=Path(tempfile.mkdtemp(prefix='.build-',dir=output_root))
        counts=Counter()
        missing=Counter()
        coverage=Counter()
        selection=Counter()
        schema=parquet_schema()
        buffer=[]
        try:
            with gzip.GzipFile(filename=str(work/'panel.jsonl.gz'),mode='wb',mtime=0) as exact,pq.ParquetWriter(work/'panel.parquet',schema,compression='zstd') as writer:
                for index,(cid,records) in enumerate(companies(url,batch),start=1):
                    counts['companies']+=1
                    for row in make_rows(cid,records):
                        exact.write((dumps(row)+'\n').encode('utf-8'))
                        buffer.append(flat(row))
                        counts['company_years']+=1
                        counts['candidates']+=len(row['candidates'])
                        selection[row['selection_status']]+=1
                        for label in ['panel_full','panel_3plus','panel_5plus','panel_long']:
                            counts[label+'_observations']+=row[label]
                        for name,value in row['features'].items():
                            coverage[name]+=value is not None
                        missing.update(row['missing_reasons'].values())
                        if len(buffer)>=1000:
                            writer.write_table(pa.Table.from_pylist(buffer,schema=schema))
                            buffer=[]
                    ny=len({r['fiscal_year'] for r in records})
                    for threshold,label in [(1,'panel_full'),(3,'panel_3plus'),(5,'panel_5plus'),(7,'panel_long')]:
                        counts[label+'_companies']+=ny>=threshold
                    if index%1000==0:
                        print(f'Panel: {index} companies, {counts["company_years"]} company-years',flush=True)
                if buffer:
                    writer.write_table(pa.Table.from_pylist(buffer,schema=schema))
            expected=conn.execute('''SELECT count(*),count(DISTINCT (f.company_id,f.fiscal_year)) FROM staging.financial_record f
                JOIN raw.record r ON r.id=f.raw_record_id JOIN raw.capture c ON c.id=r.capture_id WHERE c.batch_id=%s''',(batch,)).fetchone()
            if (counts['candidates'],counts['company_years'])!=expected:
                raise ValueError('Panel does not reconcile to all source candidates')
            summary={'dataset_id':str(dataset),'batch_id':str(batch),'code_hash':code_hash,'config':CONFIG,
                'counts':dict(counts),'selection':dict(selection),'coverage':dict(coverage),'missing_reasons':dict(missing)}
            (work/'summary.json').write_text(dumps(summary),encoding='utf-8')
            (work/'feature_definitions.json').write_text(dumps(DEFINITIONS),encoding='utf-8')
            manifest=[{'path':str(final/p.name),'sha256':digest_file(p)[0],'bytes':p.stat().st_size} for p in sorted(work.iterdir())]
            if final.exists():
                # A previous process may have published files just before its DB transaction failed.
                for item in manifest:
                    if digest_file(Path(item['path']))!=(item['sha256'],item['bytes']):
                        raise ValueError('Existing orphan dataset differs; refusing to overwrite')
            else:
                work.rename(final)
            with conn.transaction():
                conn.execute('INSERT INTO analytics.dataset(id,batch_id,version_hash,code_hash,config,maturity,research_ready,artifact_manifest) VALUES (%s,%s,%s,%s,%s,%s,false,%s)',
                    (dataset,batch,version_hash,code_hash,js(CONFIG),'exploratory_reported',js(manifest)))
                copy_rows(conn,'analytics.feature_definition','dataset_id,name,definition',[(dataset,n,js(d)) for n,d in DEFINITIONS.items()])
                with gzip.open(final/'panel.jsonl.gz','rt',encoding='utf-8') as exact:
                    pending=[]
                    for line in exact:
                        pending.append(loads(line))
                        if len(pending)==1000:
                            persist(conn,dataset,pending)
                            pending=[]
                    persist(conn,dataset,pending)
                actual=conn.execute('SELECT count(*) FROM analytics.company_year WHERE dataset_id=%s',(dataset,)).fetchone()[0]
                if actual!=counts['company_years']:
                    raise ValueError('Database publication cardinality mismatch')
            print(dumps(summary))
        finally:
            # Delete only our own temporary build directory, never a source or published directory.
            if work.exists() and not work.is_symlink() and work.resolve().parent==output_root and work.name.startswith('.build-'):
                shutil.rmtree(work)
    return str(dataset)


def persist(conn,dataset,rows):
    copy_rows(conn,'analytics.selection_candidate','dataset_id,company_id,year,financial_record_id',
        [(dataset,r['company_id'],r['year'],c) for r in rows for c in r['candidates']])
    copy_rows(conn,'analytics.company_year',
        'dataset_id,company_id,year,selected_record_id,selection_status,n_years,n_selected_years,n_annual_years,panel_full,panel_3plus,panel_5plus,panel_long,features,missing_reasons,quality_codes',
        [(dataset,r['company_id'],r['year'],r['selected_record_id'],r['selection_status'],r['n_years'],r['n_selected_years'],r['n_annual_years'],
          r['panel_full'],r['panel_3plus'],r['panel_5plus'],r['panel_long'],js(r['features']),js(r['missing_reasons']),r['quality_codes']) for r in rows])
