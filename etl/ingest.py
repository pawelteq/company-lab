"""Transactional, resumable file ingestion. Staging never resolves company-year conflicts."""
import csv
import hashlib
from pathlib import Path
from uuid import UUID, uuid5

import psycopg
from psycopg.types.json import Jsonb

from etl.parsing import PARSER_VERSION,dumps,loads,krs_valid,text_value,stage_financial
from etl.storage import archive,source_path,digest_file

NAMESPACE=UUID('fc32cd9e-5a50-4eaf-918b-3160ad898ef3')


def uid(*parts):
    return uuid5(NAMESPACE,dumps([str(p) for p in parts]))


def js(value):
    return Jsonb(value,dumps=dumps)


def copy_rows(conn,table,columns,rows):
    # table/columns are internal constants, never user input.
    if rows:
        with conn.cursor().copy(f'COPY {table} ({columns}) FROM STDIN') as cp:
            for row in rows:
                cp.write_row(row)


def issue_row(record_id,code,path,detail,severity='warning'):
    return (uid(record_id,code,path),record_id,code,severity,path,js(detail))


def save_issues(conn,rows):
    copy_rows(conn,'raw.quality_issue','id,record_id,code,severity,field_path,detail',rows)


def company(conn,krs):
    ident=uid('company',krs)
    conn.execute('INSERT INTO core.company(company_id,krs) VALUES (%s,%s) ON CONFLICT (krs) DO NOTHING',(ident,krs))
    return ident


def snapshot(conn,cid,rid,kind,obj):
    conn.execute('''INSERT INTO core.company_snapshot
        (id,company_id,raw_record_id,source_kind,name,legal_form,website,provider_entity_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',
        (uid('snapshot',cid,rid),cid,rid,kind,text_value(obj.get('name') or obj.get('company_name')),
         text_value(obj.get('legal_form')),text_value(obj.get('website')),text_value(obj.get('entity_id'))))


def ingest_json(conn,archived,relative,capture):
    rid=uid(capture,'')
    try:
        obj=loads(archived.read_bytes())
        if not isinstance(obj,dict):
            raise ValueError('Expected JSON object')
    except (ValueError,UnicodeError):
        conn.execute("INSERT INTO raw.record VALUES (%s,%s,'',NULL,'invalid')",(rid,capture))
        save_issues(conn,[issue_row(rid,'invalid_json','',{},'error')])
        return
    conn.execute("INSERT INTO raw.record VALUES (%s,%s,'',%s,'parsed')",(rid,capture,js(obj)))
    kind=Path(relative).parent.name
    krs=Path(relative).stem
    if kind not in ('financials','connections'):
        return  # Unknown JSON is preserved and registered, not silently discarded.
    if not krs_valid(krs):
        save_issues(conn,[issue_row(rid,'invalid_file_krs','',{},'error')])
        return
    cid=company(conn,krs)
    issues=[]
    if kind=='connections':
        if obj.get('registry_number')!=krs:
            save_issues(conn,[issue_row(rid,'identity_conflict','/registry_number',{},'error')])
            return
        snapshot(conn,cid,rid,kind,obj)
        graph=obj.get('graph') or {}
        conn.execute('''INSERT INTO staging.relationship_snapshot
            (id,company_id,raw_record_id,people_count,related_company_count,graph_node_count,graph_edge_count)
            VALUES (%s,%s,%s,%s,%s,%s,%s)''',
            (uid('relations',rid),cid,rid,len(obj.get('people') or []),len(obj.get('related_companies') or []),len(graph.get('nodes') or []),len(graph.get('edges') or [])))
        for i,person in enumerate(obj.get('people') or []):
            rels=person.get('relationships') or []
            if len({dumps(r) for r in rels})!=len(rels):
                issues.append(issue_row(rid,'duplicate_relationship',f'/people/{i}/relationships',{}))
    else:
        metrics=obj.get('metrics')
        if not isinstance(metrics,list):
            save_issues(conn,[issue_row(rid,'invalid_metrics','/metrics',{},'error')])
            return
        if not metrics:
            issues.append(issue_row(rid,'empty_metrics','/metrics',{},'info'))
        if (obj.get('pagination') or {}).get('hasMore'):
            issues.append(issue_row(rid,'incomplete_pagination','/pagination',{},'error'))
        staged=[]
        for i,r in enumerate(metrics):
            pointer=f'/metrics/{i}'
            if not isinstance(r,dict) or r.get('krs')!=krs:
                issues.append(issue_row(rid,'identity_conflict',pointer,{},'error'))
                continue
            row,problems=stage_financial(r)
            issues.extend(issue_row(rid,code,pointer+path,detail,severity) for code,path,detail,severity in problems)
            staged.append((uid(rid,pointer),cid,rid,pointer,r.get('id'),r.get('financial_document_id'),r.get('entity_id'),
                row['period_start'],row['period_end'],row['fiscal_year'],row['duration_days'],row['period_resolution_method'],
                row['consolidation_scope'],row['currency'],row['reported_unit_scale'],row['extracted_at'],
                js(row['reported_metrics']),js(row['statement_profile']),row['quality_codes']))
        copy_rows(conn,'staging.financial_record',
            'id,company_id,raw_record_id,source_pointer,provider_metric_id,provider_document_id,provider_entity_id,period_start,period_end,fiscal_year,duration_days,period_resolution_method,consolidation_scope,currency,reported_unit_scale,extracted_at,reported_metrics,statement_profile,quality_codes',staged)
    save_issues(conn,issues)


def ingest_csv(conn,archived,relative,capture):
    csv.field_size_limit(100_000_000)
    with archived.open(encoding='utf-8-sig',newline='') as f:
        reader=csv.DictReader(f)
        if reader.fieldnames is None or len(set(reader.fieldnames))!=len(reader.fieldnames):
            rid=uid(capture,'header')
            conn.execute("INSERT INTO raw.record VALUES (%s,%s,'header',NULL,'invalid')",(rid,capture))
            save_issues(conn,[issue_row(rid,'invalid_csv_header','',{},'error')])
            return
        buffer=[]
        for i,obj in enumerate(reader,start=2):
            rid=uid(capture,f'csv-row:{i}')
            if None in obj:
                raise ValueError(f'CSV row width mismatch in {relative}, row {i}')
            buffer.append((rid,obj,i))
            if len(buffer)==1000:
                flush_csv(conn,buffer,relative,capture)
                buffer=[]
        flush_csv(conn,buffer,relative,capture)


def flush_csv(conn,buffer,relative,capture):
    copy_rows(conn,'raw.record','id,capture_id,locator,parsed_payload,parse_status',
        [(rid,capture,f'csv-row:{i}',js(obj),'parsed') for rid,obj,i in buffer])
    for rid,obj,i in buffer:
        if relative=='firmy.csv':
            krs=obj.get('krs')
            if not krs_valid(krs):
                save_issues(conn,[issue_row(rid,'invalid_company_krs','/krs',{},'error')])
                continue
            cid=company(conn,krs)
            snapshot(conn,cid,rid,'company_csv',obj)


def run_ingest(url,source,manifest_path,store):
    source=source.resolve()
    store=store.resolve()
    if store==source or store.is_relative_to(source) or source.is_relative_to(store):
        raise ValueError('RAW archive and source must have separate directory trees')
    manifest=loads(manifest_path.read_bytes())
    if not isinstance(manifest,list) or not manifest:
        raise ValueError('Manifest must contain source files')
    paths=[f['path'] for f in manifest]
    if len(set(paths))!=len(paths):
        raise ValueError('Duplicate manifest paths')
    if set(paths)!={p.relative_to(source).as_posix() for p in source.rglob('*') if p.is_file()}:
        raise ValueError('Source file inventory differs from manifest')
    for entry in manifest:
        source_path(source,entry['path'])
        if len(entry['sha256'])!=64 or any(c not in '0123456789abcdef' for c in entry['sha256']) or entry['bytes']<0:
            raise ValueError('Invalid manifest entry')
    manifest=sorted(manifest,key=lambda f:f['path'])
    manifest_hash=hashlib.sha256(dumps(manifest).encode()).hexdigest()
    batch=uid(manifest_hash,PARSER_VERSION)
    with psycopg.connect(url,autocommit=True) as conn:
        if not conn.execute('SELECT pg_try_advisory_lock(73111517)').fetchone()[0]:
            raise RuntimeError('Another ingest is running')
        exists=conn.execute('SELECT 1 FROM raw.ingestion_batch WHERE id=%s',(batch,)).fetchone()
        with conn.transaction():
            if not exists:
                conn.execute('''INSERT INTO raw.ingestion_batch(id,source_name,source_root,manifest_hash,manifest_payload,parser_version)
                    VALUES (%s,%s,%s,%s,%s,%s)''',(batch,'Compabase export',str(source),manifest_hash,js(manifest),PARSER_VERSION))
            conn.execute('INSERT INTO raw.ingestion_event(batch_id,status) VALUES (%s,%s)',(batch,'resumed' if exists else 'started'))
        skipped=0
        try:
            for i,entry in enumerate(manifest,start=1):
                path=source_path(source,entry['path'])
                cid=uid(batch,entry['path'])
                previous=conn.execute('''SELECT o.storage_uri FROM raw.capture c JOIN raw.object o ON o.sha256=c.object_sha
                    WHERE c.id=%s''',(cid,)).fetchone()
                if previous:
                    if digest_file(path)!=(entry['sha256'],entry['bytes']) or digest_file(Path(previous[0]))!=(entry['sha256'],entry['bytes']):
                        raise ValueError('Source/archive checksum mismatch during resume')
                    skipped+=1
                else:
                    saved=archive(path,store,entry['sha256'],entry['bytes'])
                    with conn.transaction():
                        conn.execute('INSERT INTO raw.object(sha256,storage_uri,byte_size,media_type) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING',
                            (entry['sha256'],str(saved),entry['bytes'],'application/json' if path.suffix=='.json' else 'text/csv' if path.suffix=='.csv' else 'application/octet-stream'))
                        conn.execute('INSERT INTO raw.capture(id,batch_id,object_sha,original_path) VALUES (%s,%s,%s,%s)',(cid,batch,entry['sha256'],entry['path']))
                        if path.suffix=='.json':
                            ingest_json(conn,saved,entry['path'],cid)
                        elif path.suffix=='.csv':
                            ingest_csv(conn,saved,entry['path'],cid)
                        else:
                            conn.execute("INSERT INTO raw.record VALUES (%s,%s,'',NULL,'opaque')",(uid(cid,''),cid))
                if i%1000==0 or i==len(manifest):
                    print(f'Ingest: {i}/{len(manifest)} files; verified existing: {skipped}',flush=True)
            count=conn.execute('SELECT count(*) FROM raw.capture WHERE batch_id=%s',(batch,)).fetchone()[0]
            if count!=len(manifest):
                raise RuntimeError('Incomplete batch')
            conn.execute("INSERT INTO raw.ingestion_event(batch_id,status,detail) VALUES (%s,'completed',%s)",(batch,js({'files':count,'verified_existing':skipped})))
        except Exception as exc:
            conn.execute("INSERT INTO raw.ingestion_event(batch_id,status,detail) VALUES (%s,'failed',%s)",(batch,js({'error_type':type(exc).__name__})))
            raise
    return str(batch)
