import json
import numpy as np
import pandas as pd
from fastapi.testclient import TestClient
from backend.app import app
from backend import local_profiles
from backend.profile_enrichment import apply_override
from etl.business_classification import classify_profile, annual_financials
from research.leverage_study import build, estimate, shifted
from tests.test_leverage_study import profile

def company(name,pkd='',revenue=None):
    p=profile('0000000001',4)
    p.update(name=name,primary_pkd={'code':pkd})
    if revenue is not None:
        for f,v in zip(p['financials'],revenue): f['revenue_total']=v
    return p

def test_strong_signals_override_exclusions_but_not_legal_inactivity():
    p=company('Beton-Stal Development w likwidacji')
    c=classify_profile(p)
    assert c['business_type']=='developer' and c['is_active'] is False
    p=company('Projekt 123 Etap IV','41.10.Z',[0,0,0,0])
    c=classify_profile(p)
    assert c['business_type']=='spv' and c['is_active'] is True

def test_pkd_priority_exception_and_neutral_bud():
    assert classify_profile(company('Pro-Bud','68.12.A'))['business_type']=='developer'
    p=company('Biuro Projektowe Dom','68.12.A');p['screening']['segment']='residential'
    assert classify_profile(p)['business_type']=='other'
    assert classify_profile(company('Usługi Remontowe Bem-Bud'))['business_type']=='contractor'
    assert classify_profile(company('Bem-Bud',revenue=[6e6]*4))['business_type']=='needs_web_grounding'
    assert classify_profile(company('Bem-Bud',revenue=[0,1e6,3e6,0]))['business_type']=='review'
    assert classify_profile(company('Sandomierz',revenue=[0,1e6,3e6,0]))['business_type']=='review'

def test_stability_requires_consecutive_years_and_known_positive_revenue():
    p=company('ABC',revenue=[2e6,2.1e6,1.9e6,2e6])
    assert classify_profile(p)['business_type']=='contractor'
    p['financials'][1]['period_to_resolved']='2028-12-31'
    assert not classify_profile(p)['revenue_stable']
    p=company('ABC');p['financials'].append({**p['financials'][-1],'profit_net':999})
    assert annual_financials(p)[-1]['profit'] is None

def test_wrong_company_address_override_is_rejected():
    import pytest
    with pytest.raises(ValueError,match='NIP mismatch'):
        apply_override({'krs':'1','company_info':{'nip':'wrong'}},{'1':{'expected_nip':'correct','address':{}}})

def test_expanded_panel_keeps_zero_revenue_spv_and_three_years():
    p=company('Projekt 1',revenue=[0,0,0,0]);p['financials']=p['financials'][:3]
    p['classification']=classify_profile(p)
    _,selected,_,_,_=build([p],expanded=True,minimum_years=3)
    assert len(selected)==1 and selected[0]['latest_revenue']==0

def test_point_lag_uses_exact_year_not_next_available_or_average():
    rows=[]
    rng=np.random.default_rng(4)
    for i in range(30):
        debt=rng.uniform(.1,.8,10)
        for j,year in enumerate(range(2010,2020)):
            rows.append(dict(company_id=str(i),year=year,debt_assets=debt[j],log_assets=rng.normal(15,1),roa=.37*debt[j-3]+i*.001+year*.0001 if j>=3 else np.nan))
    frame=pd.DataFrame(rows).set_index(['company_id','year'])
    result=estimate(frame,3,'debt_assets',controls=['log_assets'],point_lag=True)
    assert abs(result['coefficients']['debt_assets']['value']-.37)<1e-8
    small=frame.loc[[('0',2010),('0',2014)]]
    assert np.isnan(shifted(small[['roa']],3).reindex(small.index).loc[('0',2010),'roa'])

def test_range_filters_match_map_and_export(tmp_path,monkeypatch):
    collection=tmp_path/'11111111-1111-1111-1111-111111111111';collection.mkdir()
    profiles=[company('Projekt 1',revenue=[0]*4),company('Test Development',revenue=[6e6]*4)]
    profiles[1]['krs']='0000000002'
    for p in profiles:p.update(city='Warszawa',region='mazowieckie')
    (collection/'summary.json').write_text(json.dumps({'profiles':2}))
    (collection/'screening.json').write_text(json.dumps(profiles))
    db=tmp_path/'test.sqlite3';local_profiles.build_database(collection,db);monkeypatch.setenv('LOCAL_SQLITE_PATH',str(db))
    client=TestClient(app)
    params={'collection':collection.name,'status':'all','revenue_min':0,'revenue_max':0,'profit_min':10000}
    page=client.get('/api/profiles',params=params).json()
    assert page['total']==1 and page['items'][0]['classification']['business_type']=='spv'
    assert client.get('/api/profiles/locations',params=params).json()['total']==1
    csv=client.get('/api/profiles/export.csv',params=params).text
    assert '0000000001' in csv and '0000000002' not in csv
    assert client.get('/api/profiles',params={**params,'revenue_min':1}).status_code==422
