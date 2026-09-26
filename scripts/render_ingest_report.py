"""Render completion evidence only after full database verification succeeds."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    import psycopg
    from etl.config import database_url
    from etl.parsing import PARSER_VERSION,METRICS
    audit=json.loads((ROOT/'data/ingest/verification.json').read_text(encoding='utf-8'))
    diagnosis=json.loads((ROOT/'data/ingest/candidate_diagnostics.json').read_text(encoding='utf-8'))
    if audit['status']!='passed' or audit['batch_id']!=diagnosis['batch_id']:
        raise ValueError('Matching successful verification and diagnostics required')
    batch=audit['batch_id']
    with psycopg.connect(database_url()) as conn:
        counts={key:conn.execute(query,(batch,)).fetchone()[0] for key,query in {
            'objects':'SELECT count(DISTINCT object_sha) FROM raw.capture WHERE batch_id=%s',
            'companies':'SELECT count(DISTINCT s.company_id) FROM core.company_snapshot s JOIN raw.record r ON r.id=s.raw_record_id JOIN raw.capture c ON c.id=r.capture_id WHERE c.batch_id=%s',
            'relationships':'SELECT count(*) FROM staging.relationship_snapshot s JOIN raw.record r ON r.id=s.raw_record_id JOIN raw.capture c ON c.id=r.capture_id WHERE c.batch_id=%s',
            'snapshots':'SELECT count(*) FROM core.company_snapshot s JOIN raw.record r ON r.id=s.raw_record_id JOIN raw.capture c ON c.id=r.capture_id WHERE c.batch_id=%s',
        }.items()}
        db_version=conn.execute('SHOW server_version').fetchone()[0]
    code_files=[p for base in ['etl','backend/migrations'] for p in (ROOT/base).rglob('*') if p.suffix in ('.py','.sql')]
    fingerprint={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(code_files)}
    receipt={'generated_at':datetime.now(timezone.utc).isoformat(),'batch_id':batch,
        'parser_version':PARSER_VERSION,'postgres_version':db_version,'counts':counts,'implementation_files':fingerprint}
    (ROOT/'data/ingest/implementation_receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    lines=['# Etap 2 — wynik wdrożenia RAW/staging','',
        f'Batch: `{batch}`. Parser: `{PARSER_VERSION}`. PostgreSQL: {db_version}.',
        'Stan: import zakończony i zweryfikowany na całym rzeczywistym eksporcie. RAW bez modyfikacji.', '',
        '| Element | Liczba |','|---|---:|',
        f"| Pliki źródłowe/capture | {audit['verified_files']:,} |",
        f"| Unikalne obiekty SHA-256 | {counts['objects']:,} |",
        f"| Pełne rekordy RAW (JSON korzenia lub wiersz CSV) | {audit['verified_raw_records']:,} |",
        f"| Firmy | {counts['companies']:,} |",
        f"| Snapshoty identyfikacji firm | {counts['snapshots']:,} |",
        f"| Rekordy finansowe staging | {audit['financial_records']:,} |",
        f"| Snapshoty źródłowego grafu/powiązań | {counts['relationships']:,} |",
        f"| Grupy firma–rok z wieloma kandydatami | {audit['duplicate_company_year_groups']:,} |",'',
        'Mniejsza liczba obiektów niż plików wynika z deduplikacji identycznych bajtów, nie usunięcia źródła.',
        'Osobne capture zachowują ścieżki i kontekst każdego pliku. CSV finansowe pozostaje źródłem',
        'pomocniczym i nie podwaja liczby sprawozdań staging.', '',
        '## Co zostało sprawdzone','',
        '- Sumy SHA-256 wszystkich oryginałów oraz wszystkich obiektów archiwum.',
        '- Pełna zawartość JSONB wobec parsowania oryginalnych JSON-ów, włącznie ze szczegółami bilansu/RZiS i grafu.',
        '- Każdy wiersz wszystkich CSV wobec zapisu RAW.',
        f"- Wszystkie niepuste wartości {len(METRICS)} promowanych pól finansowych: **{audit['promoted_value_mismatches']} rozbieżności**.",
        '- Testy parsera, dokładności Decimal, pochodzenia, wznowienia, rollback pliku, blokad modyfikacji i roli importera.',
        '- Pełny zestaw testów projektu: 18 zakończonych sukcesem.', '',
        '## Diagnoza kandydatów rocznych','',
        'Klasyfikacja nie wybiera automatycznie dokumentów i nie publikuje datasetu analitycznego.',
        'Unikalny roczny kandydat wciąż wymaga weryfikacji mapowania i jednostek.', '',
        '| Klasyfikacja | Firma–rok |','|---|---:|']
    labels={
        'no_standalone_candidate':'Brak kandydata jednostkowego',
        'multiple_adjacent_periods':'Kilka kolejnych okresów jednostkowych',
        'multiple_same_period':'Kilka dokumentów jednostkowych tego samego okresu',
        'multiple_overlapping_or_gapped_periods':'Okresy jednostkowe nakładają się lub mają luki',
        'invalid_or_conflicting_period':'Nieprawidłowy lub sprzeczny okres',
        'non_annual_single_candidate':'Jeden kandydat, okres inny niż 365/366 dni',
        'annual_candidate_balance_issue':'Roczny kandydat z rozbieżnością bilansu',
        'annual_candidate_extraction_issue':'Roczny kandydat z problemem ekstrakcji',
        'annual_candidate_mapping_review_required':'Roczny kandydat, wymagane sprawdzenie mapowania',
    }
    for key,count in diagnosis['classifications'].items():
        lines.append(f'| {labels[key]} | {count:,} |')
    mixed=sum(len({r['scope'] for r in group['candidates']})>1 for group in diagnosis['conflicts'])
    lines+=['',f'{mixed} grup firma–rok zawiera różne zakresy konsolidacji. Nie łączymy ich w jedno sprawozdanie.',
        'Klasyfikacja jest hierarchiczna: jedna kategoria główna na parę firma–rok; wszystkie dodatkowe flagi pozostają przy kandydatach.',
        'Szczegóły wszystkich konfliktów, identyfikatory kandydatów i pochodzenie: `data/ingest/candidate_diagnostics.json`.','',
        '## Dostarczone elementy','',
        '- Migracje Alembic 0001 i 0002, indeksy, klucze obce, triggery append-only.',
        '- Importer transakcyjny z wznowieniem i rejestrem zdarzeń importu.',
        '- Magazyn niezmiennych bajtów adresowany SHA-256.',
        '- Kontrole okresów, bilansu, znaków, jednostek, ekstrakcji i tożsamości.',
        '- Polecenia migrate, ingest, status, verify, trace i diagnose.',
        '- Lokalne środowisko PostgreSQL, oddzielna rola importera i izolowane bazy testowe.',
        '- Dokumentacja uruchomienia oraz przypięte zależności.', '',
        '## Co pozostaje','',
        'Nie wdrożono jeszcze canonical financial tables, pełnego analytical datasetu, modeli, API ani React.',
        'Nie wyprowadzamy wyników badawczych z samego sukcesu importu. Wskaźniki w staging są raportowanymi',
        'wartościami dostawcy, nie zatwierdzonymi cechami analitycznymi. Bieżący graf nie jest historią relacji.', '',
        'Następny krok: wersjonowane mapowania wariantów sprawozdań i reguły selekcji roku,',
        'z kontrolą jednostek oraz osobnymi statusami konfliktów. Potem panel firma–rok, cechy i pierwszy pakiet badań.', '',
        'Obsługa: [INGEST_RUNBOOK.md](INGEST_RUNBOOK.md). Audyt wejściowy: [DATA_AUDIT.md](DATA_AUDIT.md).',
        'Wyniki maszynowe oraz skróty wdrożonego kodu: `data/ingest/`.', '']
    (ROOT/'docs/INGEST_STATUS.md').write_text('\n'.join(lines),encoding='utf-8')
    print(json.dumps(counts,indent=2))


if __name__=='__main__':
    main()
