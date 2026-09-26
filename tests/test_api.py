"""Read-only integration checks against the published real panel; no fake production rows."""
import pytest
from fastapi.testclient import TestClient
from backend.app import app, connection

client=TestClient(app)


@pytest.fixture(scope='module')
def dataset():
    response=client.get('/api/datasets')
    assert response.status_code==200
    data=response.json()
    if not data:
        pytest.skip('No published dataset')
    return data[0]['id']


def test_input_limits_and_unknown_dataset():
    unknown='00000000-0000-0000-0000-000000000000'
    assert client.get('/api/companies',params={'dataset':unknown,'limit':101}).status_code==422
    assert client.get('/api/companies',params={'dataset':unknown,'offset':-1}).status_code==422
    assert client.get('/api/companies',params={'dataset':unknown,'cohort':'x; DROP TABLE core.company'}).status_code==422
    assert client.get('/api/companies',params={'dataset':unknown}).status_code==404
    assert client.get('/api/research/'+unknown).status_code==404


def test_pagination_and_search(dataset):
    params={'dataset':dataset,'limit':3}
    first=client.get('/api/companies',params=params).json()
    second=client.get('/api/companies',params={**params,'offset':3}).json()
    assert len(first['items'])==len(second['items'])==3
    assert not {x['krs'] for x in first['items']} & {x['krs'] for x in second['items']}
    krs=first['items'][0]['krs']
    found=client.get('/api/companies',params={**params,'q':krs}).json()
    assert found['total']==1 and found['items'][0]['krs']==krs
    assert client.get('/api/companies',params={**params,'q':"' OR 1=1 --"}).json()['total']==0
    assert client.get('/api/companies',params={**params,'offset':99999}).json()['total']==first['total']


def test_company_values_match_database_and_lineage(dataset):
    krs='0000000746'
    result=client.get('/api/companies/'+krs,params={'dataset':dataset})
    assert result.status_code==200
    years=result.json()['years']
    assert [r['year'] for r in years]==sorted({r['year'] for r in years})
    with connection() as conn:
        rows=conn.execute('''SELECT year,features,missing_reasons FROM analytics.company_year p
            JOIN core.company c USING(company_id) WHERE dataset_id=%s AND krs=%s ORDER BY year''',(dataset,krs)).fetchall()
    assert len(rows)==len(years)
    for db,api in zip(rows,years):
        for key,value in db['features'].items():
            assert api['features'][key] == (None if value is None else float(value))
        assert db['missing_reasons']==api['missing_reasons']
    trace=client.get('/api/companies/'+krs+'/lineage',params={'dataset':dataset,'year':2025,'feature':'revenue_growth'})
    assert trace.status_code==200
    assert 'object_sha256' in trace.text and 'source_pointer' in trace.text
    assert 'archive_path' not in trace.text and 'password' not in trace.text


def test_research_and_summary(dataset):
    summary=client.get('/api/datasets/'+dataset+'/summary').json()
    assert sum(x['observations'] for x in summary['years'])==summary['observations']
    runs=client.get('/api/research',params={'dataset':dataset}).json()
    assert runs
    result=client.get('/api/research/'+runs[0]['id']).json()
    assert result['causal'] is False and result['out_of_sample_validated'] is False
    assert result['provisional_dataset'] is True
    assert len(result['studies'])==4
    assert all(len(s['estimates'])==4 for s in result['studies'])


def test_api_database_role_is_read_only_and_raw_not_served():
    with connection() as conn:
        result=conn.execute("SELECT current_user name,current_setting('transaction_read_only') readonly,has_table_privilege(current_user,'raw.record','INSERT') can_insert,has_table_privilege(current_user,'analytics.company_year','UPDATE') can_update").fetchone()
    assert result['name']=='company_api'
    assert result['readonly']=='on' and not result['can_insert'] and not result['can_update']
    assert client.get('/data/audit/source_manifest.json').status_code==404
    assert client.get('/.local/database.json').status_code==404
    assert client.post('/api/companies').status_code==405


def test_diagnostics_summary_and_lazy_case_sources(dataset):
    from etl.storage import digest_file
    from pathlib import Path
    from etl.parsing import loads
    run=client.get('/api/research',params={'dataset':dataset}).json()[0]['id']
    versions=client.get('/api/research/'+run+'/diagnostics').json()
    assert versions
    ident=versions[0]['id']
    summary=client.get('/api/diagnostics/'+ident)
    assert summary.status_code==200
    assert 'lineage' not in summary.text and 'archive_path' not in summary.text
    result=summary.json()
    assert result['protocol']['post_hoc'] is True
    assert result['research_ready'] is False
    assert len(result['studies'])==4
    assert all(len(s['cases'])==5 for s in result['studies'])
    study=result['studies'][0]
    case=client.get(f"/api/diagnostics/{ident}/cases/{study['id']}/{study['cases'][0]['krs']}")
    assert case.status_code==200 and 'source_pointer' in case.text
    assert 'archive_path' not in case.text
    assert case.json()['sensitivity']['estimate']['status']=='estimated'
    assert client.get(f'/api/diagnostics/{ident}/cases/R99/0000000000').status_code==404
    with connection() as conn:
        persisted=conn.execute('SELECT results,artifact_manifest FROM research.diagnostic_run WHERE id=%s',(ident,)).fetchone()
    for item in persisted['artifact_manifest']:
        assert digest_file(Path(item['path']))==(item['sha256'],item['bytes'])
        if item['path'].endswith('results.json'):
            assert loads(Path(item['path']).read_text(encoding='utf8'))==persisted['results']
    assert all(s['baseline_reproduced'] for s in persisted['results']['studies'])
