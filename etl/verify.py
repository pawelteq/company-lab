"""Verify imported bytes, complete parsed payloads and promoted values against the archive."""
import csv
from pathlib import Path

import psycopg
from psycopg.types.json import set_json_loads

from etl.parsing import loads,dumps
from etl.storage import digest_file,source_path


def verify(url,batch_id,source=None):
    result={'batch_id':str(batch_id),'verified_files':0,'verified_raw_records':0,'source_verified':source is not None}
    with psycopg.connect(url) as conn:
        set_json_loads(loads,conn)
        batch=conn.execute('SELECT manifest_payload FROM raw.ingestion_batch WHERE id=%s',(batch_id,)).fetchone()
        if batch is None:
            raise ValueError('Unknown batch')
        latest=conn.execute('SELECT status FROM raw.ingestion_event WHERE batch_id=%s ORDER BY id DESC LIMIT 1',(batch_id,)).fetchone()
        if not latest or latest[0]!='completed':
            raise ValueError('Only a completed batch can pass verification')
        files=conn.execute('''SELECT c.id,c.original_path,o.storage_uri,o.sha256,o.byte_size
            FROM raw.capture c JOIN raw.object o ON o.sha256=c.object_sha WHERE c.batch_id=%s ORDER BY c.original_path''',(batch_id,)).fetchall()
        if len(files)!=len(batch[0]):
            raise ValueError('Manifest/capture count mismatch')
        expected={f['path']:(f['sha256'],f['bytes']) for f in batch[0]}
        for i,(capture,relative,stored,sha,size) in enumerate(files,start=1):
            path=Path(stored)
            if expected[relative]!=(sha,size) or digest_file(path)!=(sha,size):
                raise ValueError('Archived checksum mismatch')
            if source is not None and digest_file(source_path(source,relative))!=(sha,size):
                raise ValueError('Original source checksum mismatch')
            if relative.endswith('.json'):
                rows=conn.execute('SELECT locator,parse_status,parsed_payload FROM raw.record WHERE capture_id=%s',(capture,)).fetchall()
                if len(rows)!=1 or rows[0][0]!='':
                    raise ValueError('JSON record cardinality mismatch')
                if rows[0][1]=='parsed':
                    if loads(path.read_bytes())!=rows[0][2]:
                        raise ValueError('JSON payload differs from exact source parse')
                result['verified_raw_records']+=1
            elif relative.endswith('.csv'):
                csv.field_size_limit(100_000_000)
                with path.open(encoding='utf-8-sig',newline='') as f,conn.cursor(name='verify_csv') as cursor:
                    cursor.execute("SELECT locator,parsed_payload FROM raw.record WHERE capture_id=%s ORDER BY substring(locator from 9)::integer",(capture,))
                    for index,original in enumerate(csv.DictReader(f),start=2):
                        row=cursor.fetchone()
                        if row is None or row[0]!=f'csv-row:{index}' or row[1]!=original:
                            raise ValueError('CSV row differs from original')
                        result['verified_raw_records']+=1
                    if cursor.fetchone() is not None:
                        raise ValueError('Unexpected extra CSV records')
            result['verified_files']+=1
            if i%2000==0:
                print(f'Verified: {i}/{len(files)} source objects and full payloads',flush=True)
        result['financial_records']=conn.execute('''SELECT count(*) FROM staging.financial_record f
            JOIN raw.record r ON r.id=f.raw_record_id JOIN raw.capture c ON c.id=r.capture_id WHERE c.batch_id=%s''',(batch_id,)).fetchone()[0]
        result['promoted_value_mismatches']=conn.execute('''
            SELECT count(*) FROM staging.financial_record f
            JOIN raw.record r ON r.id=f.raw_record_id JOIN raw.capture c ON c.id=r.capture_id
            CROSS JOIN LATERAL jsonb_each(f.reported_metrics) kv
            WHERE c.batch_id=%s AND kv.value<>'null'::jsonb
            AND (kv.value::text)::numeric IS DISTINCT FROM
                ((r.parsed_payload #> string_to_array(trim(leading '/' from f.source_pointer),'/'))->>kv.key)::numeric
            ''',(batch_id,)).fetchone()[0]
        result['duplicate_company_year_groups']=conn.execute('SELECT count(*) FROM staging.company_year_conflicts WHERE batch_id=%s',(batch_id,)).fetchone()[0]
        result['issue_counts']={code:count for code,count in conn.execute('''SELECT q.code,count(*) FROM raw.quality_issue q
            JOIN raw.record r ON r.id=q.record_id JOIN raw.capture c ON c.id=r.capture_id
            WHERE c.batch_id=%s GROUP BY q.code ORDER BY q.code''',(batch_id,))}
        if result['promoted_value_mismatches']:
            raise ValueError('Promoted financial values differ from source')
        result['status']='passed'
    return result


def trace(url,record_id,field):
    from etl.parsing import METRICS
    if field not in METRICS:
        raise ValueError('Field is not a promoted staging metric')
    with psycopg.connect(url) as conn:
        set_json_loads(loads,conn)
        row=conn.execute('''SELECT f.source_pointer,f.reported_metrics,f.quality_codes,r.parsed_payload,
            c.original_path,o.storage_uri,o.sha256,c.batch_id
            FROM staging.financial_record f JOIN raw.record r ON r.id=f.raw_record_id
            JOIN raw.capture c ON c.id=r.capture_id JOIN raw.object o ON o.sha256=c.object_sha
            WHERE f.id=%s''',(record_id,)).fetchone()
        if row is None:
            raise ValueError('Unknown financial record')
        original=row[3]
        for part in row[0].strip('/').split('/'):
            original=original[int(part)] if isinstance(original,list) else original[part]
        return {'record_id':str(record_id),'field':field,'staged_value':row[1].get(field),'original_value':original.get(field),
            'source_pointer':row[0]+'/'+field,'original_path':row[4],'archive_path':row[5],
            'object_sha256':row[6],'batch_id':str(row[7]),'quality_codes':row[2],
            'meaning':'reported value; not a verified analytical feature'}
