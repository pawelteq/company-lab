import csv
import io

from fastapi.testclient import TestClient

from backend.app import app
from backend import geography, local_profiles
from tests.test_local_profiles import build_sample


def test_location_filter_matches_city_and_region_and_export(tmp_path, monkeypatch):
    collection, database, _ = build_sample(tmp_path, monkeypatch)
    with local_profiles.connect(database, readonly=False) as conn:
        conn.execute("UPDATE profile_screening SET city='Nowa Wieś', region='Mazowieckie' WHERE krs='0000000001'")
        conn.execute("UPDATE profile_screening SET city='Nowa Wieś', region='Łódzkie' WHERE krs='0000000002'")
        conn.commit()
    client = TestClient(app)
    params = {'collection': collection, 'status': 'all', 'city': 'nowa wies', 'region': 'lodzkie'}
    response = client.get('/api/profiles', params=params)
    assert response.status_code == 200
    assert response.json()['total'] == 1
    assert response.json()['items'][0]['krs'] == '0000000002'
    exported = client.get('/api/profiles/export.csv', params=params)
    rows = list(csv.reader(io.StringIO(exported.content.decode('utf-8-sig'))))
    assert len(rows) == 2
    assert rows[1][0] == '0000000002'
    params['status'] = 'developer_candidate'
    assert client.get('/api/profiles', params=params).json()['total'] == 0
    params.update(status='all', city="' OR 1=1 --")
    assert client.get('/api/profiles', params=params).json()['total'] == 0


def test_location_facets_respect_other_filters_and_preserve_unmapped(tmp_path, monkeypatch):
    collection, _, _ = build_sample(tmp_path, monkeypatch)
    monkeypatch.setattr(geography, 'ROOT', tmp_path)
    client = TestClient(app)
    params = {'collection':collection, 'status':'all'}
    result = client.get('/api/profiles/locations', params=params)
    assert result.status_code == 200
    assert result.json()['total'] == 2
    assert result.json()['mapped'] == 0
    assert not result.json()['gazetteer_available']
    assert sum(p['count'] for p in result.json()['items']) == 2
    params['q'] = 'Development'
    assert client.get('/api/profiles/locations', params=params).json()['total'] == 1
    params['collection'] = '00000000-0000-0000-0000-000000000000'
    assert client.get('/api/profiles/locations', params=params).status_code == 404
