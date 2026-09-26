"""Panel associations with exact-year outcomes, disclosed exclusions and sensitivity."""
from pathlib import Path
import hashlib
import json
import math
import warnings
import tempfile
import platform

import numpy as np
import pandas as pd
import psycopg
import pyarrow.parquet as pq
import linearmodels
import scipy
import statsmodels
import pyarrow
from linearmodels import PanelOLS,PooledOLS
from linearmodels.panel.utility import AbsorbingEffectError
from statsmodels.stats.multitest import multipletests

from etl.config import ROOT
from etl.ingest import uid,js
from etl.storage import digest_file


def prepare(frame,spec,protocol):
    if frame.duplicated(['company_id','year']).any():
        raise ValueError('Panel keys must be unique')
    columns=[spec['exposure'],*spec['controls']]
    panel=frame.set_index(['company_id','year']).sort_index()
    future=panel[[spec['outcome']]].rename(columns={spec['outcome']:'outcome'})
    future.index=pd.MultiIndex.from_arrays([future.index.get_level_values(0),future.index.get_level_values(1)-protocol['horizon']],names=panel.index.names)
    data=panel[columns].join(future,how='left')
    flow={'all_panel_rows':len(data)}
    years=data.index.get_level_values('year')
    data=data[(years>=protocol['year_from'])&(years<=protocol['year_to'])]
    flow['in_origin_year_range']=len(data)
    data=data.replace([np.inf,-np.inf],np.nan)
    flow['outcome_available']=int(data.outcome.notna().sum())
    flow['missing_by_variable']={c:int(data[c].isna().sum()) for c in data}
    data=data.dropna()
    flow['complete_cases']=len(data)
    # Same 2-core sample for pooled and FE; one-observation entities carry no within information.
    while len(data):
        before=len(data)
        counts=data.groupby(level='company_id').outcome.transform('size')
        year_counts=data.groupby(level='year').outcome.transform('size')
        data=data[(counts>=2)&(year_counts>=2)]
        if len(data)==before:
            break
    flow['after_singletons']=len(data)
    flow['removed_singletons']=flow['complete_cases']-len(data)
    flow['companies']=data.index.get_level_values('company_id').nunique()
    return data,flow


def fit(data,spec,model,variant):
    if len(data)<30 or data.index.get_level_values(0).nunique()<10:
        return {'status':'insufficient_data','model':model,'variant':variant}
    work=data.copy()
    clipping={}
    if variant=='winsor_01_99':
        for col in work:
            lo,hi=work[col].quantile([.01,.99])
            clipping[col]={'lower':float(lo),'upper':float(hi),'affected':int(((work[col]<lo)|(work[col]>hi)).sum())}
            work[col]=work[col].clip(lo,hi)
    x=work.drop(columns='outcome')
    if spec['quadratic']:
        x=x.assign(**{spec['exposure']+'_squared':x[spec['exposure']]**2})
    x=x.assign(const=1.0)
    if model=='pooled_year_effects':
        years=pd.get_dummies(pd.Series(x.index.get_level_values('year'),index=x.index),prefix='year',drop_first=True,dtype=float)
        x=pd.concat([x,years],axis=1)
    # Pure numerical reparameterization; preserve the original model and map estimates back.
    scales=np.sqrt((x*x).mean()).replace(0,1)
    outcome_scale=float(np.sqrt((work.outcome*work.outcome).mean())) or 1.0
    normalized_x=x/scales
    normalized_y=work.outcome/outcome_scale
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter('always')
        estimator=PanelOLS(normalized_y,normalized_x,entity_effects=True,time_effects=True,check_rank=True,drop_absorbed=False) if model=='firm_and_year_fe' else PooledOLS(normalized_y,normalized_x,check_rank=True)
        fitted=estimator.fit(cov_type='clustered',cluster_entity=True,debiased=True)
    ci=fitted.conf_int(level=.95)
    finite=lambda v:float(v) if np.isfinite(v) else None
    coefficients={name:{'coefficient':finite(fitted.params[name]*outcome_scale/scales[name]),'standard_error':finite(fitted.std_errors[name]*outcome_scale/scales[name]),
        'ci95_low':finite(ci.loc[name].iloc[0]*outcome_scale/scales[name]),'ci95_high':finite(ci.loc[name].iloc[1]*outcome_scale/scales[name]),'p_value':finite(fitted.pvalues[name])} for name in fitted.params.index}
    return {'status':'estimated','model':model,'variant':variant,'n_observations':int(fitted.nobs),
        'n_companies':int(work.index.get_level_values(0).nunique()),'years':sorted(map(int,work.index.get_level_values(1).unique())),
        'coefficients':coefficients,'r_squared':finite(fitted.rsquared),'within_r_squared':finite(fitted.rsquared_within),
        'covariance':'clustered_by_company','effects':['company','year'] if model=='firm_and_year_fe' else ['year'],
        'warnings':[str(w.message) for w in captured],'clipping':clipping,
        'numerical_scaling':{'method':'RMS reparameterization; coefficients restored to original units','outcome_scale':outcome_scale,'regressor_scales':{n:float(v) for n,v in scales.items()}},
        'turning_point':None,'turning_point_note':'Not established; a quadratic coefficient alone does not establish an optimum.',
        'p_values_note':'Coefficient p-values unadjusted. BH correction is reported separately for four prespecified primary tests.'}


def run(url,dataset,allow_provisional=False):
    specification_path=ROOT/'research/specs/initial_studies.json'
    protocol=json.loads(specification_path.read_text(encoding='utf-8'))
    code_hash=hashlib.sha256(Path(__file__).read_bytes()+specification_path.read_bytes()).hexdigest()
    runtime={'linearmodels':linearmodels.__version__,'numpy':np.__version__,'pandas':pd.__version__,
        'scipy':scipy.__version__,'statsmodels':statsmodels.__version__,'pyarrow':pyarrow.__version__,'python':platform.python_version()}
    run_hash=hashlib.sha256(json.dumps({'dataset':str(dataset),'code_hash':code_hash,'runtime':runtime},sort_keys=True).encode()).hexdigest()
    ident=uid('research',run_hash)
    final=ROOT/'data/research'/str(dataset)/str(ident)
    with psycopg.connect(url,autocommit=True,connect_timeout=10) as conn:
        if not conn.execute('SELECT pg_try_advisory_lock(73111519)').fetchone()[0]:
            raise ValueError('Another research run is active')
        meta=conn.execute('SELECT artifact_manifest,research_ready FROM analytics.dataset WHERE id=%s',(dataset,)).fetchone()
        if meta is None:
            raise ValueError('Unknown dataset')
        if not meta[1] and not allow_provisional:
            raise ValueError('Provisional dataset: explicit --allow-provisional required for exploratory associations only')
        existing=conn.execute('SELECT artifact_manifest FROM research.run WHERE id=%s',(ident,)).fetchone()
        if existing:
            for item in existing[0]:
                if digest_file(Path(item['path']))!=(item['sha256'],item['bytes']):
                    raise ValueError('Research artifact checksum mismatch')
            print('Existing research run verified: '+str(ident))
            return str(ident)
        for item in meta[0]:
            if digest_file(Path(item['path']))!=(item['sha256'],item['bytes']):
                raise ValueError('Dataset checksum mismatch')
        path=next(Path(i['path']) for i in meta[0] if i['path'].endswith('panel.parquet'))
        frame=pq.read_table(path).to_pandas()
        final.parent.mkdir(parents=True,exist_ok=True)
        folder=Path(tempfile.mkdtemp(prefix='.research-',dir=final.parent))
        results={'run_id':str(ident),'dataset_id':str(dataset),'runtime':runtime,'protocol':protocol,
            'inference_class':'exploratory_conditional_association','provisional_dataset':not meta[1],
            'causal':False,'out_of_sample_validated':False,'studies':[]}
        for spec in protocol['studies']:
            sample,flow=prepare(frame,spec,protocol)
            sample.reset_index().to_parquet(folder/(spec['id']+'_sample.parquet'),index=False)
            study={'specification':spec,'sample_flow':flow,'estimates':[]}
            for variant in protocol['sensitivity']:
                for model in protocol['models']:
                    try:
                        estimate=fit(sample,spec,model,variant)
                    except (ValueError,np.linalg.LinAlgError,ZeroDivisionError,AbsorbingEffectError) as exc:
                        estimate={'status':'failed','model':model,'variant':variant,'error':str(exc)}
                    study['estimates'].append(estimate)
            if spec['id']=='R01':
                reduced=dict(spec,controls=[c for c in spec['controls'] if c!='current_ratio'])
                expanded,expanded_flow=prepare(frame,reduced,protocol)
                expanded.reset_index().to_parquet(folder/'R01_without_liquidity_expanded_sample.parquet',index=False)
                study['liquidity_sensitivity']={'expanded_sample_flow':expanded_flow,
                    'same_sample':fit(sample.drop(columns='current_ratio'),reduced,'firm_and_year_fe','untrimmed'),
                    'expanded_sample':fit(expanded,reduced,'firm_and_year_fe','untrimmed')}
            results['studies'].append(study)
            print(f"{spec['id']}: {flow['after_singletons']} observations, {flow['companies']} companies",flush=True)
        primary=[]
        for study in results['studies']:
            estimate=next(e for e in study['estimates'] if e['model']=='firm_and_year_fe' and e['variant']=='untrimmed')
            term=study['specification']['primary_term']
            if estimate['status']=='estimated' and estimate['coefficients'][term]['p_value'] is not None:
                primary.append((study,estimate['coefficients'][term]['p_value']))
        # Planned family size stays four, even when one test cannot be estimated.
        p_values=[p for _,p in primary]+[1.0]*(len(protocol['studies'])-len(primary))
        adjusted=multipletests(p_values,method='fdr_bh')[1]
        for (study,p),q in zip(primary,adjusted):
            study['primary_test']={'term':study['specification']['primary_term'],'p_value':p,'bh_q_value':float(q),'family_size':4}
        result_path=folder/'results.json'
        result_path.write_text(json.dumps(results,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
        manifest=[{'path':str(final/p.name),'sha256':digest_file(p)[0],'bytes':p.stat().st_size} for p in sorted(folder.iterdir())]
        if final.exists():
            for item in manifest:
                if digest_file(Path(item['path']))!=(item['sha256'],item['bytes']):
                    raise ValueError('Orphaned research artifacts differ; refusing to overwrite')
        else:
            folder.rename(final)
        conn.execute('''INSERT INTO research.run(id,dataset_id,run_hash,code_hash,specification,results,artifact_manifest,inference_class)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)''',(ident,dataset,run_hash,code_hash,js(protocol),js(results),js(manifest),'exploratory_conditional_association'))
    print('Research run: '+str(ident))
    return str(ident)
