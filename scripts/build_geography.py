"""Build a local gazetteer and simplified administrative map from public downloads."""
import json
import zipfile
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import urllib.request

from backend.local_profiles import normalize_search
from etl.config import ROOT

REGIONS = dict(zip(
    ['72','73','74','75','76','77','78','79','80','81','82','83','84','85','86','87'],
    ['Dolnośląskie','Kujawsko-Pomorskie','Łódzkie','Lubelskie','Lubuskie','Małopolskie',
     'Mazowieckie','Opolskie','Podkarpackie','Podlaskie','Pomorskie','Śląskie',
     'Świętokrzyskie','Warmińsko-Mazurskie','Wielkopolskie','Zachodniopomorskie']))
SOURCES = {
    'PL-places.zip': 'https://download.geonames.org/export/dump/PL.zip',
    'PL.zip': 'https://download.geonames.org/export/zip/PL.zip',
    'nuts.geojson': 'https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_20M_2024_4326_LEVL_2.geojson',
    'nuts1.geojson': 'https://gisco-services.ec.europa.eu/distribution/v2/nuts/geojson/NUTS_RG_20M_2024_4326_LEVL_1.geojson',
    'powiaty.geojson': 'https://raw.githubusercontent.com/jusuff/PolandGeoJson/master/data/poland.counties.json',
    'gminy.geojson': 'https://raw.githubusercontent.com/jusuff/PolandGeoJson/master/data/poland.municipalities.json',
}


def round_coords(coords, precision=3):
    if isinstance(coords[0], (int, float)):
        return [round(coords[0], precision), round(coords[1], precision)]
    return [round_coords(c, precision) for c in coords]


def key(city, region):
    return normalize_search(city).strip() + '|' + normalize_search(region).strip()


def run():
    folder = ROOT / 'data/geography'
    folder.mkdir(parents=True, exist_ok=True)
    for name, url in SOURCES.items():
        if not (folder / name).exists():
            urllib.request.urlretrieve(url, folder / name)
    candidates = defaultdict(lambda: defaultdict(set))
    with zipfile.ZipFile(folder / 'PL.zip') as archive:
        for line in archive.read('PL.txt').decode('utf-8').splitlines():
            row = line.split('\t')
            region = REGIONS.get(row[4])
            if not region:
                continue
            candidates[key(row[2], region)][row[8] or row[6]].add((float(row[9]), float(row[10])))
    places = {}
    for place, municipalities in candidates.items():
        # Repeated postal rows in one municipality are consolidated. Homonyms
        # across municipalities remain unresolved, never sent to the largest town.
        coords = set().union(*municipalities.values())
        if len(municipalities) != 1 or max(x[0] for x in coords)-min(x[0] for x in coords) > .25 or max(x[1] for x in coords)-min(x[1] for x in coords) > .4:
            places[place] = {'status': 'ambiguous'}
        else:
            places[place] = {'status': 'matched', 'lat': round(sum(x[0] for x in coords)/len(coords), 5),
                             'lon': round(sum(x[1] for x in coords)/len(coords), 5)}
    named = defaultdict(dict)
    with zipfile.ZipFile(folder / 'PL-places.zip') as archive:
        for line in archive.read('PL.txt').decode('utf-8').splitlines():
            row = line.split('\t')
            region = REGIONS.get(row[10])
            if not region or row[6] != 'P' or row[7] not in ('PPL','PPLC','PPLA','PPLA2','PPLA3','PPLA4'):
                continue
            for name in {row[1], row[2], *row[3].split(',')} - {''}:
                named[key(name, region)][row[0]] = {'status':'matched', 'lat':float(row[4]), 'lon':float(row[5]), 'geoname_id':row[0]}
    for place, matches in named.items():
        places[place] = next(iter(matches.values())) if len(matches)==1 else {'status':'ambiguous'}
    output = {'generated_at': datetime.now(timezone.utc).isoformat(), 'sources': SOURCES,
              'precision': 'approximate locality centre, not company street address', 'places': places}
    (folder / 'places.json').write_text(json.dumps(output, ensure_ascii=False), encoding='utf-8')
    features = [f for f in json.loads((folder / 'nuts.geojson').read_text(encoding='utf-8'))['features']
                if f['properties']['CNTR_CODE']=='PL' and f['properties']['NUTS_ID'] not in ('PL91','PL92')]
    features += [f for f in json.loads((folder / 'nuts1.geojson').read_text(encoding='utf-8'))['features'] if f['properties']['NUTS_ID']=='PL9']
    for f in features:
        name = 'Mazowieckie' if f['properties']['NUTS_ID']=='PL9' else f['properties']['NUTS_NAME']
        f['properties'] = {'name': name, 'key': normalize_search(name)}
    assert len(features)==16
    public = ROOT / 'frontend/public/maps'
    public.mkdir(parents=True, exist_ok=True)
    (public / 'poland.json').write_text(json.dumps({'type':'FeatureCollection','features':features}, ensure_ascii=False), encoding='utf-8')

    powiaty_raw = json.loads((folder / 'powiaty.geojson').read_text(encoding='utf-8'))['features']
    powiaty_features = []
    for f in powiaty_raw:
        powiaty_features.append({
            'type': 'Feature',
            'geometry': {
                'type': f['geometry']['type'],
                'coordinates': round_coords(f['geometry']['coordinates'], 3)
            },
            'properties': {
                'name': f['properties'].get('name', ''),
                'code': f['properties'].get('terc', '')
            }
        })
    (public / 'powiaty.json').write_text(json.dumps({'type':'FeatureCollection','features':powiaty_features}, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')

    gminy_raw = json.loads((folder / 'gminy.geojson').read_text(encoding='utf-8'))['features']
    gminy_features = []
    for f in gminy_raw:
        gminy_features.append({
            'type': 'Feature',
            'geometry': {
                'type': f['geometry']['type'],
                'coordinates': round_coords(f['geometry']['coordinates'], 3)
            },
            'properties': {
                'name': f['properties'].get('name', ''),
                'code': f['properties'].get('terc', '')
            }
        })
    (public / 'gminy.json').write_text(json.dumps({'type':'FeatureCollection','features':gminy_features}, separators=(',', ':'), ensure_ascii=False), encoding='utf-8')

    print(json.dumps({'localities':len(places),'voivodeships':len(features),'powiaty':len(powiaty_features),'gminy':len(gminy_features)}))


if __name__ == '__main__':
    run()
