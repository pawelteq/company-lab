"""Guard the selection boundary: missing evidence must not become a developer."""
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import app, connection
from etl.config import ROOT
from etl.developer_screening import classify, extract_summary
from scripts.import_profiles import public_profile


@pytest.mark.parametrize('name,summary,expected', [
    ('Acme', None, 'missing_summary'),
    ('Acme Development', 'Acme Development is based in Warsaw and publishes shareholder notices.', 'review'),
    ('Acme', 'Acme is a residential developer that builds apartments.', 'developer_candidate'),
    ('Acme', 'Acme builds and sells apartments and houses.', 'developer_candidate'),
    ('7R', '7R is a developer of logistics warehouses and industrial spaces.', 'developer_candidate'),
    ('Acme', 'Acme is a construction company that provides building services for developers.', 'other_activity'),
    ('Acme', 'Acme is a portal about construction. It publishes guides.', 'other_activity'),
    ('Acme', 'Different Brand is a residential developer that builds apartments.', 'review'),
    ('Acme', 'Acme is a real estate agency offering apartments for sale.', 'other_activity'),
    ('Acme', 'Acme is not a real estate developer. It sells apartments as an agent.', 'review'),
    ('Acme', 'Acme is a partner supporting investors in real estate development and residential projects.', 'review'),
    ('Acme', 'Acme is a consultancy. Beta is a developer of residential housing.', 'review'),
    ('Acme', 'Acme is a developer of software for residential real estate companies.', 'review'),
])
def test_screening_boundary(name, summary, expected):
    assert classify(name, summary)['status'] == expected


def test_summary_fallback_and_no_lookup_into_other_companies():
    assert extract_summary({'company': {}, 'companySummary': {'en': 'Example.'}}) == ('Example.', '/companySummary/en')
    assert extract_summary({'company': {}, 'similarCompanies': [{'company_summary': 'A developer'}]}) == (None, None)
    assert classify('Real Development SPV', None)['name_signal'] is True
    assert classify('Acme', None)['name_signal'] is False


def test_krs_conflict_and_real_awbud_case():
    assert classify('Acme', 'Acme is a residential developer. KRS: 0000000002.', '0000000001')['status'] == 'review'
    raw = json.loads((ROOT / 'firmy_b/raw/profiles/0000023958.json').read_bytes())
    selected = public_profile(raw, '0000023958', 'a'*64)
    assert selected['screening']['status'] == 'other_activity'
    assert selected['screening']['flags']
    assert 'portal' in selected['summary']
    assert 'people' not in selected and 'details' not in selected
    with pytest.raises(ValueError, match='identity'):
        public_profile(raw, '0000000001', 'a'*64)


def test_current_catalog_totals_default_filter_and_source_isolation():
    client = TestClient(app)
    response = client.get('/api/profiles/collections')
    assert response.status_code == 200
    collection = response.json()[0]
    cid = collection['id']
    counts = collection['summary']['counts']
    assert sum(counts.values()) == collection['summary']['profiles']
    selected = client.get('/api/profiles', params={'collection': cid}).json()
    assert selected['total'] == counts['developer_candidate']
    assert all(r['screening']['status'] == 'developer_candidate' for r in selected['items'])
    assert all('financials' not in r for r in selected['items'])
    assert client.get('/api/profiles', params={'collection': cid, 'status': 'all'}).json()['total'] == collection['summary']['profiles']
    assert client.get('/api/profiles', params={'collection': cid, 'q': '0000023958'}).json()['total'] == 0
    detail = client.get('/api/profiles/0000023958', params={'collection': cid}).json()
    assert detail['screening']['status'] == 'other_activity'
    assert len(detail['source_sha256']) == 64
    assert client.get('/api/profiles', params={'collection': cid, 'q': "' OR 1=1 --"}).json()['total'] == 0
    assert client.get('/api/profiles', params={'collection': cid, 'q': '%'}).json()['total'] < collection['summary']['profiles']
    assert client.get('/api/profiles', params={'collection': cid, 'status': 'invalid'}).status_code == 422
    assert client.get('/api/profiles', params={'collection': cid, 'limit': 101}).status_code == 422
    assert client.get('/api/profiles/0000000001', params={'collection': '00000000-0000-0000-0000-000000000000'}).status_code == 404
    with connection() as conn:
        assert not conn.execute("SELECT has_table_privilege(current_user,'core.profile_screening','INSERT') allowed").fetchone()['allowed']
        assert conn.execute('SELECT count(*) n FROM core.profile_screening WHERE collection_id=%s', (cid,)).fetchone()['n'] == collection['summary']['profiles']


def test_catalog_sort_and_filtered_csv_export():
    client = TestClient(app)
    collection = client.get('/api/profiles/collections').json()[0]['id']
    listed = client.get('/api/profiles', params={
        'collection': collection, 'status': 'developer_candidate',
        'sort': 'revenue', 'direction': 'desc', 'limit': 5,
    })
    assert listed.status_code == 200
    assert listed.json()['sort'] == 'revenue'
    assert listed.json()['direction'] == 'desc'
    export = client.get('/api/profiles/export.csv', params={
        'collection': collection, 'status': 'developer_candidate',
    })
    assert export.status_code == 200
    assert export.headers['content-type'].startswith('text/csv')
    assert 'attachment' in export.headers.get('content-disposition', '')
    assert export.content.startswith(b'\xef\xbb\xbfKRS,Nazwa')
