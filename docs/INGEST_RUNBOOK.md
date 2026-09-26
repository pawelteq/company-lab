# Import RAW/staging — uruchomienie i obsługa

Implementacja etapu 2. PostgreSQL 17, Python 3.12+, Alembic, psycopg 3.
Importer przyjmuje wyłącznie lokalny eksport i manifest z audytu. Nie wysyła danych do dostawcy.

## Środowisko

Zależności bezpośrednie przypięte w `pyproject.toml`; pełny lock środowiska w `requirements.lock`.
Na tym komputerze `.venv/Scripts/python.exe`. Przy nowej instalacji utworzyć venv i zainstalować
`pip install -r requirements.lock`. Nie modyfikować pakietów środowiska systemowego.

Lokalne binaria PostgreSQL w `.local/postgresql/pgsql`, klaster `.local/pgdata`, port 55432,
nasłuch tylko 127.0.0.1. Nie zainstalowano usługi Windows i nie zmieniono globalnego PATH.
Binaria pochodzą z [EDB](https://www.enterprisedb.com/download-postgresql-binaries),
do którego odsyła [oficjalna strona PostgreSQL](https://www.postgresql.org/download/windows/).
Zachowane archiwum `.local/downloads/postgresql.zip`; lokalny hash nie zastępuje podpisu wydawcy.

```powershell
.venv/Scripts/python.exe scripts/local_postgres.py status
.venv/Scripts/python.exe scripts/local_postgres.py start
.venv/Scripts/python.exe scripts/local_postgres.py stop
```

Na nowym komputerze najpierw rozpakować binaria i wykonać `setup`. `setup` odmawia nadpisania
istniejącego klastra. Po przerwaniu między inicjalizacją a utworzeniem baz: `start`, potem `provision`.
Alternatywa Docker: `infra/compose.yaml` z hasłem w środowisku, a nie w repozytorium.
Nie uruchamiać obu wariantów jednocześnie na tym samym porcie.

Połączenia: `DATABASE_ADMIN_URL`, `DATABASE_URL`, `TEST_DATABASE_URL` w środowisku.
Lokalny helper zapisuje je w ignorowanym `.local/database.json`. Nie publikować tego pliku
ani `.local/` i `data/`. Rola `company_ingest` ma INSERT/SELECT; migracje odrębną rolą administracyjną.
Na zewnętrznym serwerze administrator tworzy rolę importera przed migracją lub nadaje jej
odpowiednie uprawnienia po migracji. Compose sam nie tworzy roli importera.

## Migracje i import

```powershell
.venv/Scripts/python.exe -m etl.cli migrate
.venv/Scripts/python.exe -m etl.cli ingest
.venv/Scripts/python.exe -m etl.cli status
```

Domyślnie wejście `firmy_b/`, manifest `data/audit/source_manifest.json`, magazyn
`data/raw/objects/<sha-prefix>/<sha256>`. Argumenty `--source`, `--manifest`, `--store`
pozwalają wskazać oddzielny eksport. Magazyn nie może być wewnątrz źródeł ani obejmować źródeł.
Manifest musi obejmować dokładnie wszystkie pliki źródłowe. Zmiana bajtów powoduje błąd,
nie cichy import pod starym manifestem. Nowy eksport wymaga nowego audytu/manifestu.

Batch ma deterministyczny identyfikator na podstawie manifestu i wersji parsera. Manifest
jest zapisywany również w DB. Import jednego pliku to jedna transakcja: capture, record,
staging i issue pojawiają się razem. Awaria pozostawia wcześniejsze pliki do wznowienia;
nieudany plik jest ponawiany. COPY przyspiesza zapis, CSV jest przetwarzany porcjami 1000 wierszy.
Nie pobieramy całego CSV do pamięci.

Ponowne `ingest` weryfikuje bajty źródeł oraz archiwum i pomija już zapisane capture.
Nowe zdarzenia resumed/completed są prawidłowym śladem operacji, nie duplikatami danych.
Jednoczesny import jest blokowany advisory lock. Status completed oznacza zakończenie importu,
nie zatwierdzenie danych do badań. Błędy jakości pozostają w `raw.quality_issue`.

Nieznane pliki są archiwizowane; nieznane pola JSON pozostają w pełnym parsed_payload.
Powtórzone klucze JSON są odrzucane jako niejednoznaczne parsowanie, a oryginalne bajty zachowane.
Finansowy staging zawiera 42 jawnie promowane liczby bez zmiany skali; wszystkie 310 pól
i zagnieżdżone pozycje pozostają w raw.record. Typ Decimal/NUMERIC zachowuje precyzję;
podczas odczytu JSONB używać `set_json_loads(etl.parsing.loads, conn)`, aby uniknąć float.

## Weryfikacja i pochodzenie

```powershell
.venv/Scripts/python.exe -m etl.cli verify --batch IDENTYFIKATOR --source firmy_b
.venv/Scripts/python.exe -m etl.cli trace --record IDENTYFIKATOR_REKORDU --field revenue_total
.venv/Scripts/python.exe -m etl.cli diagnose --batch IDENTYFIKATOR
.venv/Scripts/python.exe -m pytest -q --tb=short
```

`verify` porównuje SHA-256 archiwum i opcjonalnie oryginałów, pełny JSONB z parsowaniem
oryginalnych JSON-ów, każdy wiersz CSV i każdą niepustą promowaną liczbę z jej źródłem.
Nie ogranicza się do kilku kolumn audytu. Wynik domyślnie `data/ingest/verification.json`.
`trace` pokazuje źródłowy plik, skrót, JSON Pointer, oryginalną i zapisaną wartość oraz problemy.
`diagnose` rozdziela konflikty zakresów i okresów oraz generuje ocenę kandydatów rocznych;
nie wybiera automatycznie rocznego dokumentu. Kategorie są hierarchiczne, a pozostałe
flagi są dostępne przy każdym kandydacie.

Testy integracyjne tworzą osobną bazę `ci_test_<losowy_id>`, migrują ją i usuwają wyłącznie
tę bazę po teście. Korzystają z małego wycinka prawdziwych plików w folderze tymczasowym.
Testowe niepoprawne CSV i liczby są wyłącznie fixtures; nigdy nie trafiają do bazy company_lab.
Migracje produkcyjne są forward-only. `downgrade` jawnie odmawia kasowania RAW.

## Znane ograniczenia i kolejny etap

To staging, nie gotowy analytical dataset. Wszystkie sprawozdania są kandydatami;
`staging.company_year_conflicts` pokazuje konflikty osobno dla każdego batcha.
Nieprawidłowy start okresu jest NULL w polu typowanym i pozostaje niezmieniony w RAW z issue.
Nie zweryfikowano semantyki resolved dates/jednostek i mapowań wszystkich formularzy.
Nie spłaszczono grafu do historycznych relacji bez dat obowiązywania. Brak pełnej tabeli
statement_line jest świadomym etapowaniem; dane szczegółowe są już zachowane i dostępne.

Triggery blokują UPDATE/DELETE/TRUNCATE, a rola importera nie ma tych uprawnień.
Administrator DB i właściciel plików nadal technicznie mogą zmieniać dane: to nie magazyn WORM.
Przed wdrożeniem współdzielonym potrzebne są kopie zapasowe, retencja obiektów i test odtwarzania.
Lokalna kopia w tym samym dysku chroni przed nadpisaniem w ETL, nie przed awarią dysku.

Następny krok: wersjonowane mapowania, selekcja kandydatów, osobne core.statement i pełne
statement_value/statement_line, analytical dataset z lineage. Dopiero potem estymacje/API/UI.
