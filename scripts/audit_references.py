"""Audit illustrative exports without adding them to the production research population."""
from collections import Counter,defaultdict
from pathlib import Path
import hashlib
import json
from etl.config import ROOT
from etl.parsing import loads,METRICS
from etl.storage import archive,digest_file
from etl.compabase_payloads import kind,profile,financial_candidates,numeric_comparison,collection_requests


def audit(source=None):
    source=source or ROOT/'referencja'
    report={'purpose':'reference_only','provider':'Compabase API',
        'provider_documentation':'https://github.com/ContentWriterco/Compabase-API',
        'files':[],'profiles':[],'financial_representations':0,'comparisons':[],
        'collection_requests':collection_requests()}
    by_id=defaultdict(list)
    for p in sorted(source.glob('*.json')):
        digest,size=digest_file(p)
        stored=archive(p,ROOT/'data/raw/reference_objects',digest,size)
        raw=loads(p.read_bytes())
        candidates=list(financial_candidates(raw))
        pr=profile(raw)
        if pr:
            report['profiles'].append(pr)
        preferred=[c for c in candidates if c.preferred_container]
        years=[str(c.payload.get('period_to_resolved') or c.payload.get('sf_period_to') or '')[:4] for c in preferred]
        report['files'].append({'name':p.name,'sha256':digest,'bytes':size,'archive':str(stored),
            'kind':kind(raw),'root_keys':list(raw),'financial_representations':len(candidates),
            'preferred_financial_records':len(preferred),'years':sorted(set(years)),
            'multiple_records_in_year':{y:n for y,n in Counter(years).items() if n>1}})
        report['financial_representations']+=len(candidates)
        for c in candidates:
            if c.payload.get('id'):
                by_id[c.payload['id']].append((p.name,c))
    for ident,representations in sorted(by_id.items()):
        first_name,first=representations[0]
        for name,other in representations[1:]:
            report['comparisons'].append({'provider_record_id':ident,'left':first_name+first.pointer,
                'right':name+other.pointer,**numeric_comparison(first.payload,other.payload,METRICS)})
    report['distinct_provider_financial_ids']=len(by_id)
    report['profile_companies']=len({p['krs'] for p in report['profiles']})
    identity=hashlib.sha256(json.dumps([f['sha256'] for f in report['files']]).encode()).hexdigest()
    folder=ROOT/'data/audit/references'/identity
    folder.mkdir(parents=True,exist_ok=True)
    content=json.dumps(report,ensure_ascii=False,indent=2,default=str)
    target=folder/'audit.json'
    if target.exists() and target.read_text(encoding='utf8')!=content:
        raise ValueError('Reference audit differs; refusing to overwrite')
    if not target.exists():
        target.write_text(content,encoding='utf8')
    lines=['# Audyt nowych plików referencyjnych','',
        'Projekt korzysta z **Compabase API**: https://github.com/ContentWriterco/Compabase-API.',
        'Źródło wskazane przez użytkownika. Pliki w `referencja/` mają charakter poglądowy; nie zwiększają populacji badań.',
        '', '| Plik | Typ | Preferowane rekordy finansowe | Lata |','|---|---|---:|---|']
    for f in report['files']:
        lines.append(f"| {f['name']} | {f['kind']} | {f['preferred_financial_records']} | {', '.join(f['years']) or '—'} |")
    lines+=['',f"Liczba firm w pełnych profilach: {report['profile_companies']}. Różne ID rekordów finansowych: {len(by_id)}.",
        f"Reprezentacje finansowe we wszystkich kontenerach: {report['financial_representations']}; nie wolno sumować ich jako różnych obserwacji.",
        'Rok 2020 zawiera dwa odrębne okresy. Adapter zachowuje obydwa; nie skleja automatycznie bilansów.','',
        '## Nowe informacje','',
        'NIP, REGON, adres i lokalizacja, pełna lista PKD z wersją klasyfikacji i statusem głównej działalności.',
        'Profil zawiera też sekcje rejestrowe, historię zmian, benchmarki dostawcy i opisy generowane; pozostają w RAW.',
        'Bieżący profil nie jest historycznym PKD firmy. Benchmarki/similarCompanies dostawcy nie zastępują naszego modelu peer group.','',
        '## Zgodność reprezentacji finansów','']
    differences=sum(bool(c['different']) for c in report['comparisons'])
    lines+=[f"Porównania wspólnych niepustych wartości promowanych: {len(report['comparisons'])}; z różnicami liczbowymi: {differences}.",
        'Tekstowe liczby porównano jako Decimal; NULL i nieobecne pola nie zastępują wartości z innego kontenera.',
        'Pełny wykaz różnic/ubytków i SHA-256 zapisany w artefakcie audytu.','',
        '## Zakres zbierania','',
        '41.10.Z i 41.20.Z — PKD 2007; 68.11.Z i 68.12.A — PKD 2025. Osobne zapytania po kodzie i primary_only=true.',
        'Łączenie wyników po KRS przy zachowaniu przynależności do każdego zapytania. Nie sumować liczebności czterech eksportów.',
        'Nie ograniczać zbierania do firm aktywnych lub z dodatnim przychodem bez osobnego uzasadnienia badawczego.','',
        'Żaden z tych kodów sam nie jest dowodem prowadzenia mieszkaniowej działalności deweloperskiej.',
        f"Artefakt: `{target.relative_to(ROOT).as_posix()}`.",'']
    (ROOT/'docs/REFERENCE_DATA_AUDIT.md').write_text('\n'.join(lines),encoding='utf8')
    print(json.dumps({'files':len(report['files']),'companies':report['profile_companies'],'financial_ids':len(by_id),
                      'representations':report['financial_representations'],'numeric_conflicts':differences,'audit':str(target)},indent=2))
    return report


if __name__=='__main__':
    audit()
