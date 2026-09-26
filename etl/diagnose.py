"""Assess candidate conflicts without selecting analytical observations."""
from collections import Counter,defaultdict
from datetime import timedelta
import psycopg


def diagnose(url,batch_id):
    groups=defaultdict(list)
    with psycopg.connect(url) as conn:
        state=conn.execute('SELECT status FROM raw.ingestion_event WHERE batch_id=%s ORDER BY id DESC LIMIT 1',(batch_id,)).fetchone()
        if not state or state[0]!='completed':
            raise ValueError('Diagnostics require a completed import batch')
        for row in conn.execute('''SELECT co.krs,f.id,f.fiscal_year,f.period_start,f.period_end,f.consolidation_scope,f.quality_codes,f.source_pointer,c.original_path
            FROM staging.financial_record f JOIN core.company co ON co.company_id=f.company_id
            JOIN raw.record r ON r.id=f.raw_record_id JOIN raw.capture c ON c.id=r.capture_id
            WHERE c.batch_id=%s ORDER BY co.krs,f.fiscal_year,f.period_start''',(batch_id,)):
            krs,rid,year,start,end,scope,quality,pointer,path=row
            groups[krs,year].append({'id':str(rid),'start':start,'end':end,'scope':scope,
                'quality_codes':quality,'source_pointer':pointer,'original_path':path})
    totals=Counter()
    conflicts=[]
    for (krs,year),rows in groups.items():
        standalone=[r for r in rows if r['scope']=='standalone']
        if not standalone:
            status='no_standalone_candidate'
        elif len(standalone)>1:
            ordered=sorted(standalone,key=lambda r:str(r['start'] or r['end'] or ''))
            if all(r['start'] and r['end'] for r in ordered) and all(a['end']+timedelta(days=1)==b['start'] for a,b in zip(ordered,ordered[1:])):
                status='multiple_adjacent_periods'
            elif len({(r['start'],r['end']) for r in standalone})==1:
                status='multiple_same_period'
            else:
                status='multiple_overlapping_or_gapped_periods'
        else:
            codes=set(standalone[0]['quality_codes'])
            if codes & {'invalid_period','incomplete_period','invalid_date','period_start_conflict','period_end_conflict'}:
                status='invalid_or_conflicting_period'
            elif 'non_annual_period' in codes:
                status='non_annual_single_candidate'
            elif 'balance_mismatch' in codes:
                status='annual_candidate_balance_issue'
            elif 'extraction_not_ok' in codes:
                status='annual_candidate_extraction_issue'
            else:
                status='annual_candidate_mapping_review_required'
        totals[status]+=1
        if len(rows)>1:
            conflicts.append({'krs':krs,'year':year,'classification':status,'candidates':rows})
    return {'batch_id':str(batch_id),'company_year_groups':len(groups),'classifications':dict(totals),
        'analytical_dataset_published':False,'note':'Candidate assessment only; a unique annual candidate still needs mapping/unit validation.',
        'conflicts':conflicts}
