"""Post-hoc tail/denominator review and bounded leave-one-company-out sensitivity."""
from functools import lru_cache
from pathlib import Path
import hashlib
import json
import platform
import tempfile

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
import pyarrow
import linearmodels
import scipy
import statsmodels
import psycopg
from linearmodels.panel.utility import AbsorbingEffectError

from analytics.lineage import feature_trace
from etl.config import ROOT
from etl.ingest import uid, js
from etl.storage import digest_file
from research.run import fit

PROTOCOL={'version':'tail-review-v1','companies_per_study':5,'tail_quantiles':[.01,.99],
          'selection':'maximum absolute median deviation / IQR across original X and Y; MAD/std fallback',
          'sensitivity':'omit one whole company at a time, firm/year FE, untrimmed, company clustered SE',
          'post_hoc':True,'automatic_exclusion':False,'global_influence_ranking':False}


def distribution(series):
    s=series.dropna()
    quantiles=s.quantile([0,.01,.25,.5,.75,.99,1])
    return {'n':len(s),'quantiles':{str(q):float(v) for q,v in quantiles.items()},
            'outside_p01_p99':int(((s<quantiles.loc[.01])|(s>quantiles.loc[.99])).sum())}


def select_candidates(sample,limit=5):
    distances=pd.DataFrame(index=sample.index)
    for name in sample:
        s=sample[name]
        median=float(s.median())
        scale=float(s.quantile(.75)-s.quantile(.25))
        if not scale:
            scale=float((s-median).abs().median()) or float(s.std())
        distances[name]=(s-median).abs()/scale if scale and np.isfinite(scale) else 0.0
    ranked=pd.DataFrame({'review_priority':distances.max(axis=1),'trigger_variable':distances.idxmax(axis=1)})
    return (ranked.reset_index().sort_values(['review_priority','company_id','year'],ascending=[False,True,True])
            .drop_duplicates('company_id').head(limit).to_dict('records'))


def denominator_dependencies(definitions,feature,offset=0,seen=frozenset()):
    """Walk the stored graph; ratio/growth denominator is always the last input."""
    if feature in seen:
        raise ValueError('Cyclic feature definition')
    definition=definitions[feature]
    found=[]
    if definition['op'] in ('ratio','growth','scaled_change'):
        dependency=definition['inputs'][-1]
        found.append((dependency['name'],offset+dependency['offset']))
    for dependency in definition['inputs']:
        found.extend(denominator_dependencies(definitions,dependency['name'],offset+dependency['offset'],seen|{feature}))
    return sorted(set(found))


def omit_company(sample,company):
    reduced=sample[sample.index.get_level_values('company_id')!=company]
    removed=len(sample)-len(reduced)
    before=len(reduced)
    while len(reduced):
        count=len(reduced)
        companies=reduced.groupby(level='company_id').outcome.transform('size')
        years=reduced.groupby(level='year').outcome.transform('size')
        reduced=reduced[(companies>=2)&(years>=2)]
        if len(reduced)==count:
            break
    return reduced,removed,before-len(reduced)


def verify_manifest(manifest):
    for item in manifest:
        if digest_file(Path(item['path']))!=(item['sha256'],item['bytes']):
            raise ValueError('Artifact checksum mismatch; diagnostics aborted')


def stripped_trace(value):
    if isinstance(value,dict):
        return {k:stripped_trace(v) for k,v in value.items() if k!='archive_path'}
    if isinstance(value,list):
        return [stripped_trace(v) for v in value]
    return value


def diagnose(url,run_id):
    # Pin the estimator and graph resolver used for this diagnostic publication.
    paths=['research/diagnostics.py','research/run.py','analytics/lineage.py','etl/verify.py','docs/DIAGNOSTIC_PROTOCOL.md']
    code_hash=hashlib.sha256(b''.join((ROOT/p).read_bytes() for p in paths)).hexdigest()
    runtime={'python':platform.python_version(),'numpy':np.__version__,'pandas':pd.__version__,
             'pyarrow':pyarrow.__version__,'linearmodels':linearmodels.__version__,
             'scipy':scipy.__version__,'statsmodels':statsmodels.__version__}
    version_hash=hashlib.sha256(json.dumps({'run':str(run_id),'code':code_hash,'protocol':PROTOCOL,'runtime':runtime},sort_keys=True).encode()).hexdigest()
    ident=uid('diagnostic',version_hash)
    with psycopg.connect(url,autocommit=True,connect_timeout=10) as conn:
        if not conn.execute('SELECT pg_try_advisory_lock(73111520)').fetchone()[0]:
            raise ValueError('Another diagnostics job is active')
        previous=conn.execute('SELECT artifact_manifest FROM research.diagnostic_run WHERE id=%s',(ident,)).fetchone()
        if previous:
            verify_manifest(previous[0])
            print('Existing diagnostic verified: '+str(ident))
            return str(ident)
        meta=conn.execute('SELECT dataset_id,results,artifact_manifest,code_hash FROM research.run WHERE id=%s',(run_id,)).fetchone()
        if not meta:
            raise ValueError('Unknown research run')
        dataset,original,manifest,original_code_hash=meta
        expected=hashlib.sha256((ROOT/'research/run.py').read_bytes()+(ROOT/'research/specs/initial_studies.json').read_bytes()).hexdigest()
        if expected!=original_code_hash:
            raise ValueError('Current estimator differs from parent run; use its archived code before diagnosing')
        verify_manifest(manifest)
        dm=conn.execute('SELECT artifact_manifest FROM analytics.dataset WHERE id=%s',(dataset,)).fetchone()[0]
        verify_manifest(dm)
        definitions=dict(conn.execute('SELECT name,definition FROM analytics.feature_definition WHERE dataset_id=%s',(dataset,)))
        companies={str(c):(k,n) for c,k,n in conn.execute('''SELECT c.company_id,c.krs,s.name FROM core.company c
            LEFT JOIN LATERAL(SELECT name FROM core.company_snapshot WHERE company_id=c.company_id AND name IS NOT NULL
                ORDER BY observed_at DESC,id DESC LIMIT 1) s ON true''')}
        panel=pq.read_table(next(i['path'] for i in dm if i['path'].endswith('panel.parquet'))).to_pandas().set_index(['company_id','year']).sort_index()
        result={'id':str(ident),'research_run_id':str(run_id),'dataset_id':str(dataset),'protocol':PROTOCOL,
                'runtime':runtime,'maturity':'post_hoc_diagnostics','research_ready':False,'studies':[]}

        @lru_cache(maxsize=400)
        def lineage(krs,year,feature):
            return stripped_trace(feature_trace(url,dataset,krs,year,feature))

        for study in original['studies']:
            spec=study['specification']
            sample_path=next(i['path'] for i in manifest if Path(i['path']).name==spec['id']+'_sample.parquet')
            sample=pq.read_table(sample_path).to_pandas().set_index(['company_id','year']).sort_index()
            if sample.index.has_duplicates or not np.isfinite(sample.to_numpy()).all():
                raise ValueError('Invalid saved estimation sample')
            baseline=fit(sample,spec,'firm_and_year_fe','untrimmed')
            stored=next(e for e in study['estimates'] if e['model']=='firm_and_year_fe' and e['variant']=='untrimmed')
            if baseline['status']!='estimated' or stored['status']!='estimated':
                raise ValueError('Primary model must be estimated before sensitivity diagnosis')
            for term,c in baseline['coefficients'].items():
                if not np.isclose(c['coefficient'],stored['coefficients'][term]['coefficient'],rtol=1e-7,atol=1e-12):
                    raise ValueError('Baseline coefficients failed reproduction')
            item={'id':spec['id'],'title':spec['title'],'baseline':baseline,'baseline_reproduced':True,
                  'primary_term':spec['primary_term'],'distributions':{c:distribution(sample[c]) for c in sample},'cases':[]}
            candidates=select_candidates(sample,PROTOCOL['companies_per_study'])
            # Precompute denominator references in the EXACT model sample, with outcome offsets.
            references={}
            for variable in sample:
                feature=spec['outcome'] if variable=='outcome' else variable
                shift=original['protocol']['horizon'] if variable=='outcome' else 0
                for name,offset in denominator_dependencies(definitions,feature,shift):
                    key=(name,offset)
                    if key not in references:
                        idx=pd.MultiIndex.from_arrays([sample.index.get_level_values(0),sample.index.get_level_values(1)+offset],names=sample.index.names)
                        values=panel[name].reindex(idx)
                        references[key]=values[values>0].dropna().sort_values().to_numpy()
            for rank,candidate in enumerate(candidates,1):
                company=str(candidate['company_id']);year=int(candidate['year'])
                krs,name=companies[company]
                case={'rank':rank,'company_id':company,'krs':krs,'name':name,'origin_year':year,
                      'trigger_variable':candidate['trigger_variable'],'review_priority':float(candidate['review_priority']),
                      'status':'requires_source_review','variables':[]}
                for variable,value in sample.loc[(company,year)].items():
                    feature=spec['outcome'] if variable=='outcome' else variable
                    feature_year=year+(original['protocol']['horizon'] if variable=='outcome' else 0)
                    entry={'variable':variable,'feature':feature,'year':feature_year,'value':float(value),
                           'lineage':lineage(krs,feature_year,feature),'denominators':[]}
                    for denom,offset in denominator_dependencies(definitions,feature,feature_year-year):
                        observed=panel.at[(company,year+offset),denom]
                        reference=references[(denom,offset)]
                        positive=bool(np.isfinite(observed) and observed>0)
                        threshold=float(np.quantile(reference,.01)) if len(reference) else None
                        entry['denominators'].append({'feature':denom,'year':year+offset,'value':float(observed) if np.isfinite(observed) else None,
                            'reference_n':len(reference),'p01':threshold,
                            'percentile_weak':float(np.searchsorted(reference,observed,side='right')/len(reference)) if positive and len(reference) else None,
                            'small_denominator_flag':bool(positive and threshold is not None and observed<=threshold)})
                    case['variables'].append(entry)
                reduced,removed,singletons=omit_company(sample,company)
                try:
                    sensitivity=fit(reduced,spec,'firm_and_year_fe','untrimmed')
                except (ValueError,np.linalg.LinAlgError,ZeroDivisionError,AbsorbingEffectError) as exc:
                    sensitivity={'status':'failed','error':str(exc)}
                case['sensitivity']={'removed_company_rows':removed,'additional_singletons':singletons,'estimate':sensitivity}
                if sensitivity['status']=='estimated':
                    base=baseline['coefficients'][spec['primary_term']]
                    new=sensitivity['coefficients'][spec['primary_term']]
                    change=new['coefficient']-base['coefficient']
                    case['sensitivity'].update({'coefficient_change':change,'change_in_baseline_se':change/base['standard_error'] if base['standard_error'] and base['standard_error']>0 else None})
                item['cases'].append(case)
                print(f"{spec['id']} review {rank}/{len(candidates)}: KRS {krs}, origin {year}",flush=True)
            result['studies'].append(item)
        final=ROOT/'data/research'/str(dataset)/str(run_id)/'diagnostics'/str(ident)
        final.parent.mkdir(parents=True,exist_ok=True)
        folder=Path(tempfile.mkdtemp(prefix='.diagnostic-',dir=final.parent))
        # Exact lineage Decimal values are encoded as strings; statistical floats remain numbers.
        (folder/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2,default=str,allow_nan=False),encoding='utf-8')
        report=render_report(result)
        (folder/'report.md').write_text(report,encoding='utf-8')
        artifacts=[{'path':str(final/p.name),'sha256':digest_file(p)[0],'bytes':p.stat().st_size} for p in sorted(folder.iterdir())]
        if final.exists():
            verify_manifest(artifacts)
        else:
            folder.rename(final)
        # Use serialized payload to preserve Decimal strings identically in artifact and DB.
        payload=json.loads((final/'results.json').read_text(encoding='utf-8'))
        conn.execute('''INSERT INTO research.diagnostic_run(id,research_run_id,version_hash,code_hash,protocol,results,artifact_manifest)
            VALUES(%s,%s,%s,%s,%s,%s,%s)''',(ident,run_id,version_hash,code_hash,js(PROTOCOL),js(payload),js(artifacts)))
        (ROOT/'docs/MODEL_DIAGNOSTICS.md').write_text(report,encoding='utf-8')
    print('Diagnostic run: '+str(ident))
    return str(ident)


def render_report(result):
    def fmt(v):
        return 'brak' if v is None else f'{v:.6g}'
    lines=['# Diagnostyka modeli R01–R04','',f"Diagnostyka: `{result['id']}`. Run: `{result['research_run_id']}`.",'',
           '**Analiza post hoc, wyłącznie diagnostyczna. Źródła i podstawowe wyniki nie zostały zmienione.**','',
           'Pięć firm na badanie wybrano według skrajności X/Y (odległość od mediany / IQR).',
           'Nie jest to pełny ranking wpływu ani ocena firmy. Pominięcie firmy dotyczy wyłącznie osobnej estymacji wrażliwości.',
           'Mały mianownik oznacza dolny 1% odpowiedniego składnika w próbie modelu. Nie dowodzi błędu.',
           'Wartości kwotowe mają niezweryfikowaną skalę dostawcy; nie przypisujemy im potwierdzonej jednostki PLN.','']
    for study in result['studies']:
        base=study['baseline']['coefficients'][study['primary_term']]
        lines += [f"## {study['id']} — {study['title']}",'',
            f"Bazowy parametr `{study['primary_term']}`: {fmt(base['coefficient'])}; SE {fmt(base['standard_error'])}. Odtworzenie współczynników: OK.",'',
            '| KRS | Rok X | Zmienna skrajna | Małe mianowniki | β po pominięciu firmy | Zmiana / bazowy SE |',
            '|---|---:|---|---:|---:|---:|']
        for case in study['cases']:
            s=case['sensitivity'];est=s['estimate']
            coefficient=est.get('coefficients',{}).get(study['primary_term'],{}).get('coefficient')
            small=sum(d['small_denominator_flag'] for v in case['variables'] for d in v['denominators'])
            lines.append(f"| {case['krs']} | {case['origin_year']} | {case['trigger_variable']} | {small} | {fmt(coefficient)} | {fmt(s.get('change_in_baseline_se'))} |")
        lines+=['','### Rozkłady w dokładnej próbie modelu','',
                '| Zmienna | N | Min | p1 | Mediana | p99 | Max |','|---|---:|---:|---:|---:|---:|---:|']
        for variable,d in study['distributions'].items():
            q=d['quantiles'];lines.append(f"| {variable} | {d['n']} | "+' | '.join(fmt(q[k]) for k in ['0.0','0.01','0.5','0.99','1.0'])+' |')
        for case in study['cases']:
            lines += ['',f"### Do przeglądu: {case['name']} — KRS {case['krs']}, rok X {case['origin_year']}",'',
                      f"Powód wyboru: `{case['trigger_variable']}`. Status: wymaga weryfikacji źródłowej."]
            for v in case['variables']:
                lines.append(f"- `{v['feature']}` ({v['year']}): {fmt(v['value'])}.")
                for d in v['denominators']:
                    lines.append(f"  - Mianownik `{d['feature']}` ({d['year']}): {fmt(d['value'])}; p1 próby={fmt(d['p01'])}; flaga małego mianownika={d['small_denominator_flag']}.")
                def sources(node):
                    if node.get('source'):
                        yield node['source']
                    for child in node.get('inputs',[]):
                        yield from sources(child)
                for source in sources(v['lineage']['lineage']):
                    lines.append(f"  - Źródło: `{source['original_path']}` → `{source['source_pointer']}`; SHA-256 `{source['object_sha256']}`.")
    lines += ['','## Dalsza kwalifikacja','',
              'Każdy przypadek wymaga sprawdzenia sprawozdania/mapowania. Nie usuwamy obserwacji z powodu samej skrajności.',
              'Priorytetem jest potwierdzenie jednostek i ekonomicznego znaczenia małych mianowników oraz rozbieżności w źródłach.',
              'Pełne wyniki i lineage w results.json diagnostyki oraz API. Protokół: docs/DIAGNOSTIC_PROTOCOL.md.','']
    return '\n'.join(lines)
