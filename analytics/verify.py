import gzip
from pathlib import Path
import psycopg
from psycopg.types.json import set_json_loads
import pyarrow.parquet as pq
from etl.parsing import loads
from etl.storage import digest_file


def verify_panel(url,dataset):
    with psycopg.connect(url,connect_timeout=10) as conn:
        set_json_loads(loads,conn)
        manifest=conn.execute('SELECT artifact_manifest FROM analytics.dataset WHERE id=%s',(dataset,)).fetchone()
        if manifest is None:
            raise ValueError('Unknown dataset')
        for item in manifest[0]:
            if digest_file(Path(item['path']))!=(item['sha256'],item['bytes']):
                raise ValueError('Artifact checksum mismatch')
        folder=Path(manifest[0][0]['path']).parent
        summary=loads((folder/'summary.json').read_bytes())
        defs=dict(conn.execute('SELECT name,definition FROM analytics.feature_definition WHERE dataset_id=%s',(dataset,)).fetchall())
        if defs!=loads((folder/'feature_definitions.json').read_bytes()):
            raise ValueError('Stored feature definitions mismatch')
        count=0
        with gzip.open(folder/'panel.jsonl.gz','rt',encoding='utf-8') as exact,conn.cursor(name='verify_panel') as cur:
            cur.itersize=500
            cur.execute('''SELECT company_id,year,selected_record_id,selection_status,n_years,n_selected_years,n_annual_years,
                panel_full,panel_3plus,panel_5plus,panel_long,features,missing_reasons,quality_codes
                FROM analytics.company_year WHERE dataset_id=%s ORDER BY company_id,year''',(dataset,))
            for line in exact:
                row=loads(line)
                db=cur.fetchone()
                if db is None:
                    raise ValueError('Missing database row')
                expected=(row['company_id'],row['year'],row['selected_record_id'],row['selection_status'],
                    row['n_years'],row['n_selected_years'],row['n_annual_years'],row['panel_full'],row['panel_3plus'],row['panel_5plus'],row['panel_long'],
                    row['features'],row['missing_reasons'],row['quality_codes'])
                actual=(str(db[0]),db[1],str(db[2]) if db[2] else None,*db[3:])
                if expected!=actual:
                    raise ValueError('Exact panel export differs from database')
                count+=1
            if cur.fetchone() is not None:
                raise ValueError('Extra database row')
        parquet=pq.ParquetFile(folder/'panel.parquet')
        if count!=summary['counts']['company_years'] or count!=parquet.metadata.num_rows:
            raise ValueError('Panel cardinality mismatch')
        bad=conn.execute('''SELECT count(*) FROM analytics.selection_candidate c
            JOIN staging.financial_record f ON f.id=c.financial_record_id
            WHERE c.dataset_id=%s AND (c.company_id<>f.company_id OR c.year<>f.fiscal_year)''',(dataset,)).fetchone()[0]
        if bad:
            raise ValueError('Candidate identity/year mismatch')
        result={'dataset_id':str(dataset),'status':'passed','verified_company_years':count,
            'features':len(defs),'candidate_identity_mismatches':bad,'research_ready':False}
        return result
