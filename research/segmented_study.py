"""Separate developer/SPV and contractor panels, exact calendar-year lags."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from statsmodels.stats.multitest import multipletests
from backend.local_profiles import connect, decompress_json, apply_verification_override
from etl.config import ROOT
from etl.business_classification import VERSION, RULES
from research.leverage_study import build, estimate

PROTOCOL = {'version':'segmented-point-lags-v1','classification_version':VERSION,'minimum_years':3,
    'selection':'Saved human/Gemini decisions override automatic labels. Otherwise all classified active developers/SPV/contractors with ≥3 complete annual standalone PLN periods; no minimum revenue. Unresolved and unknown activity excluded.',
    'periods':'Full calendar years; positive assets; profit, revenue, equity and liabilities observed; balance within 2%; conflicting duplicate years excluded.',
    'outcomes':'ROA = profit / average assets(t-1,t); ROE = profit / average equity(t-1,t), only positive equity in both years.',
    'exposures':['liabilities_assets','debt_equity'],
    'debt_note':'liabilities_assets includes provisions, trade payables and other non-interest liabilities; it is not loans alone. D/E uses observed interest-bearing debt; missing components are never zero-filled.',
    'lags':{'developer':[3,4],'contractor':[1,2]},'timing':'Outcome at exactly t+h, not a future average; calendar gaps remain missing.',
    'controls':['log_assets'],'model':'Company and year fixed effects; company-clustered standard errors; at least 2 usable pairs per firm and year, ≥20 firms and ≥50 pairs.',
    'variants':['raw','winsor_01_99'],'alpha':.10,'confidence_level':.90,'multiple_testing':'Benjamini-Hochberg across all successfully estimated reported exposure coefficients.',
    'causal':False,'limitation':'Current classification and active-company selection may cause misclassification and survivorship bias. Stable-turnover classification uses full observed history; results are exploratory, not out-of-sample forecasts.'}

def run():
    with connect() as conn:
        collection=conn.execute('SELECT id FROM profile_collection ORDER BY created_at DESC LIMIT 1').fetchone()[0]
        def profiles():
            for r in conn.execute('''SELECT p.profile_json_zlib,p.classification_json,v.status verification_status
                FROM profile_screening p LEFT JOIN company_verification v ON v.krs=p.krs
                WHERE p.collection_id=? ORDER BY p.krs''',(collection,)):
                classification=json.loads(r['classification_json']) if r['classification_json'] else {}
                yield apply_verification_override(decompress_json(r['profile_json_zlib']),r['verification_status'],classification)
        frame,selected,audit,exclusions,coverage=build(profiles(),expanded=True,minimum_years=3)
    frame['debt_equity']=frame.debt/frame.equity.where(frame.equity>0)
    models=[]; panels=[]
    for group,kinds,lags in [('developer',['developer','spv'],[3,4]),('contractor',['contractor'],[1,2])]:
        data=frame[frame.business_type.isin(kinds)]
        panels.append({'group':group,'companies':data.index.get_level_values(0).nunique(),'company_years':len(data)})
        for lag in lags:
            for exposure in ['liabilities_assets','debt_equity']:
                for outcome in ['roa','roe']:
                    for variant in ['raw','winsor_01_99']:
                        print(group,lag,exposure,outcome,variant,flush=True)
                        models.append({'group':group,**estimate(data,lag,exposure,outcome=outcome,variant=variant,controls=['log_assets'],point_lag=True)})
    valid=[m for m in models if m.get('status')=='estimated' and m['exposure'] in m.get('coefficients',{})]
    if valid:
        for m,q in zip(valid,multipletests([m['coefficients'][m['exposure']]['p'] for m in valid],method='fdr_bh')[1]):
            m['q']=float(q)
    ident=hashlib.sha256((collection+json.dumps(PROTOCOL,sort_keys=True)+json.dumps(RULES,sort_keys=True)+Path(__file__).read_text(encoding='utf-8')+(ROOT/'etl/business_classification.py').read_text(encoding='utf-8')+(ROOT/'research/leverage_study.py').read_text(encoding='utf-8')).encode()).hexdigest()[:16]
    report={'id':ident,'collection_id':collection,'created_at':datetime.now(timezone.utc).isoformat(),'protocol':PROTOCOL,'audit':audit,'exclusions':exclusions,'coverage':coverage,'panels':panels,'models':models}
    folder=ROOT/'data/research/segmented'/ident;folder.mkdir(parents=True,exist_ok=True)
    def clean(v):
        if isinstance(v,dict): return {k:clean(x) for k,x in v.items()}
        if isinstance(v,list): return [clean(x) for x in v]
        if isinstance(v,float) and not np.isfinite(v): return None
        if isinstance(v,np.integer): return int(v)
        return v
    output=json.dumps(clean(report),ensure_ascii=False,indent=2,allow_nan=False)
    (folder/'report.json').write_text(output,encoding='utf-8')
    (folder/'selected.json').write_text(json.dumps(selected,ensure_ascii=False,indent=2),encoding='utf-8')
    frame.to_csv(folder/'panel.csv')
    temporary=folder.parent/'latest.tmp';temporary.write_text(output,encoding='utf-8');temporary.replace(folder.parent/'latest.json')
    print(json.dumps({'panels':panels,'audit':audit,'path':str(folder)},default=int),flush=True)

if __name__=='__main__': run()
