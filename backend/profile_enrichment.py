"""Rebuildable classifications and identity-checked address corrections."""
import json
from collections import Counter
from etl.config import ROOT
from etl.business_classification import classify_profile

OVERRIDES = ROOT/'data/overrides/company_overrides.json'

def apply_override(p, overrides):
    correction = overrides.get(p['krs'])
    if not correction:
        return p
    info = p.get('company_info') or {}
    if str(info.get('nip') or '') != correction['expected_nip']:
        raise ValueError('NIP mismatch for override '+p['krs'])
    p.setdefault('original_address', {k:info.get(k) for k in correction['address']})
    info.update(correction['address'])
    p['company_info'] = info
    p.update(city=info['city'],region=info['region'],address_correction=correction)
    address = p.setdefault('profile_details',{}).setdefault('address',{})
    for src,dst in [('street','ulica'),('building_no','nrDomu'),('postal_code','kodPocztowy'),('city','miejscowosc'),('full_address','full')]:
        address[dst] = info[src]
    return p

def enrich_database(path=None, *, publish=True):
    from backend.local_profiles import connect, decompress_json, _compress, normalize_search
    overrides = json.loads(OVERRIDES.read_text(encoding='utf-8')) if OVERRIDES.exists() else {}
    counts, queue, batch = Counter(), [], []
    with connect(path,readonly=False) as writer:
        existing = {r['name'] for r in writer.execute('PRAGMA table_info(profile_screening)')}
        columns={'business_type':'TEXT','classification_json':'TEXT','annual_period':'TEXT','annual_revenue':'REAL','annual_profit':'REAL','is_active':'INTEGER'}
        for col,kind in columns.items():
            if col not in existing:
                writer.execute(f'ALTER TABLE profile_screening ADD COLUMN {col} {kind}')
        writer.commit()
        # Read each page before updating it; keep memory bounded and release read locks.
        last = ''
        while True:
            rows = writer.execute('SELECT collection_id,krs,profile_json_zlib,catalog_json_zlib FROM profile_screening WHERE krs>? ORDER BY krs LIMIT 150',(last,)).fetchall()
            if not rows: break
            for row in rows:
                p=decompress_json(row['profile_json_zlib'])
                cat=decompress_json(row['catalog_json_zlib'])
                p=apply_override(p,overrides)
                c=classify_profile(p)
                cat['classification']=c
                counts[c['business_type']]+=1
                if c['business_type']=='needs_web_grounding':
                    queue.append({'krs':p['krs'],'name':p.get('name'),'city':p.get('city'),'nip':(p.get('company_info') or {}).get('nip'),'query':c['grounding_query'],'status':'pending_provider'})
                if p['krs'] in overrides:
                    cat.update(city=p['city'],region=p['region'],address_correction=p['address_correction'])
                    writer.execute('UPDATE profile_screening SET city=?,region=?,search_text=?,profile_json_zlib=? WHERE collection_id=? AND krs=?',
                        (p['city'],p['region'],normalize_search(' '.join(str(p.get(k) or '') for k in ('krs','name','city','summary'))),_compress(p),row['collection_id'],p['krs']))
                writer.execute('UPDATE profile_screening SET business_type=?,classification_json=?,annual_period=?,annual_revenue=?,annual_profit=?,is_active=?,catalog_json_zlib=? WHERE collection_id=? AND krs=?',
                    (c['business_type'],json.dumps(c,ensure_ascii=False),c['annual_period'],c['annual_revenue'],c['annual_profit'],c['is_active'],_compress(cat),row['collection_id'],p['krs']))
            writer.commit()
            last=rows[-1]['krs']
            if sum(counts.values())%1500==0: print(dict(counts),flush=True)
        writer.execute('CREATE INDEX IF NOT EXISTS idx_business_financial ON profile_screening(collection_id,business_type,annual_revenue,annual_profit)')
        writer.commit()
    if not publish: return dict(counts)
    folder=ROOT/'data/classification'; folder.mkdir(parents=True,exist_ok=True)
    (folder/'web_grounding_queue.json').write_text(json.dumps(queue,ensure_ascii=False,indent=2),encoding='utf-8')
    (folder/'summary.json').write_text(json.dumps(dict(counts),ensure_ascii=False,indent=2),encoding='utf-8')
    return dict(counts)

if __name__=='__main__':
    print(enrich_database())
