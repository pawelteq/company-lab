"""Locality coordinates joined to live catalogue facets, without external requests."""
import json
from functools import lru_cache
from etl.config import ROOT


@lru_cache(maxsize=2)
def _gazetteer(path, stamp):
    return json.loads(path.read_text(encoding='utf-8'))['places']


def locations(collection, *, q='', status='all', segment='all', county='', municipality='', **filters):
    from backend.local_profiles import connect, filter_clauses
    clauses, params = filter_clauses(collection, q=q, status=status, segment=segment, county=county, municipality=municipality, **filters)
    path = ROOT / 'data/geography/places.json'
    gazetteer = _gazetteer(path, path.stat().st_mtime_ns) if path.exists() else {}
    with connect() as conn:
        if not conn.execute('SELECT 1 FROM profile_collection WHERE id=?', (collection,)).fetchone():
            raise KeyError(collection)
        rows = conn.execute('''SELECT geo_norm(city) city_key, geo_norm(region) region_key,
            min(city) city, min(region) region, min(county) county, min(municipality) municipality, count(*) count FROM profile_screening WHERE '''
            + ' AND '.join(clauses) + ' GROUP BY geo_norm(city),geo_norm(region) ORDER BY count DESC, city_key', params).fetchall()

        powiaty_rows = conn.execute('''SELECT geo_norm(county) county_key, min(county) county,
            geo_norm(region) region_key, min(region) region, count(*) count
            FROM profile_screening WHERE county IS NOT NULL AND county != '' AND '''
            + ' AND '.join(clauses) + ' GROUP BY geo_norm(county), geo_norm(region) ORDER BY count DESC', params).fetchall()

        gminy_rows = conn.execute('''SELECT geo_norm(municipality) muni_key, min(municipality) municipality,
            geo_norm(county) county_key, min(county) county,
            geo_norm(region) region_key, min(region) region, count(*) count
            FROM profile_screening WHERE municipality IS NOT NULL AND municipality != '' AND '''
            + ' AND '.join(clauses) + ' GROUP BY geo_norm(municipality), geo_norm(county), geo_norm(region) ORDER BY count DESC', params).fetchall()

    items = []
    for row in rows:
        item = dict(row)
        match = gazetteer.get(item['city_key']+'|'+item['region_key'], {'status':'unmatched'})
        items.append({**item, **match})
    return {
        'collection_id': collection,
        'items': items,
        'powiaty': [dict(r) for r in powiaty_rows],
        'gminy': [dict(r) for r in gminy_rows],
        'total': sum(x['count'] for x in items),
        'mapped': sum(x['count'] for x in items if x['status']=='matched'),
        'gazetteer_available': bool(gazetteer)
    }

