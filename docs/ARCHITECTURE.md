# Architektura Company Intelligence + Research Lab

Status: lokalne etapy 1–6, 12.09.2026. Audyt poprzedził implementację. Wdrożono PostgreSQL,
migracje 0001–0005, importer RAW/staging i eksploracyjny panel firma–rok, raport R00,
badania OLS/FE R01–R04, API i React. Modele predykcyjne i rekomendacje nie są wdrożone.
Instrukcje: [INGEST_RUNBOOK.md](INGEST_RUNBOOK.md), [APP_RUNBOOK.md](APP_RUNBOOK.md).
Historyczny DATA_AUDIT opisuje etap 1; aktualny zakres w IMPLEMENTATION_STATUS.

Diagnostyka post hoc jest osobnym `research.diagnostic_run` z FK do niezmiennego runu.
Weryfikuje hashe źródeł analitycznych i odtwarza bazowy model przed analizą wrażliwości.
Nie modyfikuje datasetu i nie zmienia klasy wniosku. API rozdziela lekki przegląd od
pełnej lineage pojedynczego przypadku; frontend pobiera szczegóły dopiero po wyborze KRS.

## Decyzje

Aktualizacja 2026-09-13: użytkownik potwierdził korzystanie z
[Compabase API](https://github.com/ContentWriterco/Compabase-API) oraz zbieranie głównych
PKD 41.10.Z, 41.20.Z, 68.11.Z i 68.12.A. Kontrakt opisany w COMPABASE_API.md.
Adapter pełnych profili działa obok starego eksportu. Rozpoznaje lustrzane kontenery
finansów i zachowuje `pkd_source` osobno dla każdej działalności. Nie modyfikuje
historycznego panelu na podstawie bieżącego profilu. Pliki referencyjne są archiwizowane
osobno i nie zwiększają populacji produkcyjnej; rzeczywisty nowy wsad wymaga własnego batcha.

1. **Monolit modułowy**: React + TypeScript + Vite, Python + FastAPI, PostgreSQL.
   Jeden backend i osobny proces obliczeniowy wystarczą dla tej skali; nie ma podstaw do mikroserwisów.
2. **Źródło prawdy to niezmienne bajty** eksportu. Obecny `firmy_b/` pozostaje na miejscu.
   Manifest SHA-256 identyfikuje każdy plik. Docelowy ingest zapisuje nowe obiekty pod adresem
   zależnym od skrótu, nigdy pod nadpisywanym KRS.json. Kopia JSONB służy wyszukiwaniu,
   a nie zastępuje oryginału: [PostgreSQL opisuje różnice JSON/JSONB](https://www.postgresql.org/docs/16/datatype-json.html).
3. **Rozdzielenie RAW → staging → canonical → analytical → research**. Snapshot danych,
   wersja mapowania i kodu wyznaczają wynik. CSV finansowy jest eksportem pomocniczym,
   nie niezależnym potwierdzeniem JSON. Każdy atrybut analityczny ma pochodzenie.
4. **Firma i sprawozdanie to różne jednostki**. Nie narzucamy unikalności firma–rok przy imporcie.
   Najpierw przechowujemy wszystkie dokumenty, okresy, warianty i rewizje. Dopiero wersjonowana
   selekcja tworzy jeden wiersz firma–rok w konkretnym zbiorze analitycznym.
5. **Bieżące dane relacyjne nie są historią**. Data pobrania i data obowiązywania to osobne pola.
   Bez dowodu historycznego nie przypisujemy obecnego zarządu ani właściciela do dawnych lat.
6. **Obliczenia po stronie serwera**. Początkowo powtarzalne zadania CLI; z API osobny worker
   Celery i broker Redis, z trwałym stanem jobów w PostgreSQL. Zadania idempotentne, limity
   czasu/pamięci, anulowanie, kontrolowane ponowienia. FastAPI służy do zlecania i odczytu:
   [dokumentacja odsyła ciężkie obliczenia do odrębnych narzędzi](https://fastapi.tiangolo.com/tutorial/background-tasks/).
7. **Nie każdy model ma być od razu dostępny**. Pierwszy pakiet: opis danych, pooled OLS,
   FE firmy + roku. `linearmodels` dla panelu, `statsmodels` dla diagnostyki/OLS;
   pandas/numpy do transformacji, scikit-learn później dla predykcji i podobieństwa.
   GMM, survival, przyczynowe event studies i modele przestrzenne wymagają osobnych protokołów.
8. **Bez arbitralnego score** jakości wzrostu i bez niekalibrowanego ryzyka. Decision Lab
   zwraca status `insufficient_data` z powodami do czasu walidacji modelu i danych projektu.

## Docelowa struktura

```text
frontend/                   React/TS/Vite; dopiero po pierwszych wynikach API
backend/app/                API, autoryzacja, kontrakty, usługi
backend/migrations/         Alembic, wersjonowane migracje PostgreSQL
etl/                        ingest, parsery, mapowania, wybór sprawozdań, walidacja
analytics/                  cechy, kohorty, badania, peers, walidacja czasowa
research/specs/             deklaratywne wersjonowane specyfikacje badań
scripts/                    uruchamianie audytu i zadań lokalnych
data/audit/                 raporty maszynowe, manifest i diagnostyka
data/analytical/<version>/   niemutowalne Parquet, słownik, lineage, raport wykluczeń
firmy_b/                    istniejący eksport źródłowy, bez modyfikacji
docs/                       audyt, model danych, architektura, plan badań
tests/                      parsery, kalendarz, finanse, kontrakty, integracja DB
infra/                      lokalny PostgreSQL/Redis i konfiguracja uruchomienia
```

To struktura docelowa. Działają audyt, migracje i ETL; pozostałe komponenty powstaną
w kolejnych etapach. Nie tworzymy pustych atrap ekranów.

## Doprecyzowania wdrożenia etapu 2

- Dodany schemat `staging`: kandydaci finansowi i snapshoty relacji. Żaden konflikt
  firma–rok nie jest jeszcze rozstrzygany. Core.statement i znormalizowane szczegóły są następnym etapem.
- RAW JSON zapisany jako pełny rekord korzenia. Rekord finansowy wskazuje FK do tego
  korzenia oraz `/metrics/<index>`; nie duplikujemy całego JSON-a dla każdej metryki.
- CSV finansowe archiwizowane i zapisane wierszowo, ale nie tworzą drugiej kopii
  finansowego stagingu. Firma bez KRS pozostaje w RAW z issue.
- Append-only obejmuje triggery UPDATE/DELETE/TRUNCATE i ograniczoną rolę importera.
  Migracje forward-only, bez kasującego downgrade; odtworzenie wymaga jawnego backupu.
- Osobny `raw.ingestion_event` przechowuje rozpoczęcie, wznowienie, zakończenie i awarię,
  dzięki czemu nie aktualizujemy rekordów źródłowych. Transakcja obejmuje jeden cały plik.
- Lokalny PostgreSQL z pakietu binarnego w folderze projektu (brak Dockera na komputerze),
  port wyłącznie loopback; Docker Compose pozostaje dostępną alternatywą.

## Panel v1 — wdrożenie etapu 3

`analytics.dataset`, `feature_definition`, `selection_candidate`, `company_year` realizują
wersjonowany panel eksploracyjny na podstawie reported metrics. Protokołem jest
[DATASET_SPEC.md](DATASET_SPEC.md). Status research_ready=false blokuje traktowanie go jako
zatwierdzonego wejścia modeli decyzyjnych. Nie maskujemy niepewności mapowań dostawcy.

Dokładne cechy i powody braków w JSONB numeric oraz JSONL.GZ; Parquet float64 służy
obliczeniom statystycznym. Wybrany rekord staging i wersjonowana definicja zależności
tworzą pochodzenie każdej cechy, również przez lata; `trace-feature` rozwija je do RAW.
Nie potrzebujemy powielania milionów bazowych pól do nowej tabeli przed ich semantyczną walidacją.
Pełne canonical statement_value/line pozostają kolejnym rozszerzeniem normalizacji.

Wiersze konfliktowe pozostają w panel_full z NULL i statusem. Publikacja w jednej transakcji
DB, artefakty niemutowalne i chronione sumami kontrolnymi. To rozdziela dostępność obserwacji
od kwalifikacji do konkretnego badania. R00: [R00_PANEL_REPORT.md](R00_PANEL_REPORT.md).

## ETL i warunki publikacji zbioru

1. Spis wszystkich plików, SHA-256, rozmiar, źródło, chwila zaobserwowania. Nie utożsamiamy
   mtime z datą publikacji sprawozdania. Przy kolejnym uruchomieniu weryfikacja manifestu.
2. Parsowanie JSON/CSV w UTF-8, KRS/NIP/REGON jako tekst. Walidacja składni i typów.
   Nie używamy `eval` do zagnieżdżonych struktur zapisanych w CSV jako reprezentacja Pythona.
3. Staging zachowuje wszystkie rekordy, pola i dokładne ścieżki JSON Pointer / wiersze CSV.
   Pola nieznane trafiają do rejestru schematu, a nie do kosza.
4. Rozpoznanie podmiotu, zakresu konsolidacji, wariantu bilansu/RZiS, waluty, jednostki kwot
   i okresu. Surowe oraz `*_resolved` daty zachowujemy oddzielnie, z metodą rozstrzygnięcia.
5. Dedup exact hash; rozstrzyganie rewizji tylko w selekcji, nigdy usunięcie źródła.
   Sprzeczne kandydatury bez wiarygodnej kolejności → kwarantanna wyboru. Sam czas ekstrakcji
   nie dowodzi, że wersja sprawozdania jest późniejsza.
6. Normalizacja kwot Decimal/NUMERIC; przeliczenia walut wyłącznie z jawnym kursem, datą
   i regułą dla strumieni vs stanów. PLN jako pierwszy wariant badawczy po weryfikacji jednostek.
   Wskaźniki przeliczane z kwot; oryginalne wskaźniki zachowane jako `reported_*`.
7. Testy bilansu, braków, skali, znaków, okresów, duplikatów, zgodności CSV/JSON. Błąd blokuje
   dotkniętą obserwację/cechę, nie usuwa całej historii firmy. Zero nie oznacza braku.
8. Budowa panelu i cech przez złączenie po dokładnym roku; osobne powody braku każdej cechy.
   Flagi jakości i ścieżka od cechy przez składniki do RAW są częścią zbioru.
9. Zapis nowej wersji datasetu, definicji cech i selekcji, liczebności na każdym kroku;
   publikacja atomowa dopiero po testach. Ponowne wykonanie daje ten sam wynik dla tego samego wejścia.

## API, wydajność i bezpieczeństwo

Wdrożone kontrakty v0.3 opisuje APP_RUNBOOK: `/api/companies` (offset, limit ≤100,
filtrowanie na serwerze), historia pojedynczej firmy, lineage, dataset summary oraz odczyt
runów. API używa osobnej roli SELECT-only i transakcji read-only. Cache LRU agregatów
per niezmienny dataset, statement timeout 10 s. React pobiera 25 firm na stronę, pojedynczą
historię lub wybrany run. W UI nie są obliczane modele. Widok Modele pokazuje istniejące
estymacje; własne specyfikacje i kolejka wymagają osobnego etapu.

Projekt przyszłych kontraktów: `GET /companies` (cursor, limit ≤100, filtrowanie na serwerze),
`GET /companies/{id}`, `/financials`, `/relations`, `/peers`, `GET /datasets/{id}/quality`,
`POST /research/runs`, `GET /research/runs/{id}`, `GET /models/{id}`.
Docelowo wszystkie wyniki zawierają `dataset_version`, jednostki, status jakości i metodologię.
Źródła finansów pobierane oddzielnie, z paginacją szczegółów; wykresy otrzymują tylko potrzebne szeregi.
Obliczenia modelu przyjmują dozwolone nazwy zmiennych i specyfikację, nigdy dowolny kod/SQL.

Indeksy opisane w DATA_MODEL. Agregaty/materialized views per rok i dostępny segment;
cache kluczowany wersją danych i filtrami. Parquet dla batch analytics, PostgreSQL dla obsługi aplikacji.
Nie kopiujemy całej populacji do przeglądarki. Benchmark p95 i plan zapytań mierzymy na rzeczywistym panelu.
RAW nie trafia do publicznego katalogu frontendu. Dostęp do osób i danych źródłowych wymaga
uprawnień; logi nie zawierają pełnych danych osób. Kopie zapasowe plus test odtwarzania.

## Kolejność dostarczenia

Etap 1: kompletny audyt i projekty → etap 2: migracja oraz ingest i zweryfikowane mapowania →
etap 3: analytical dataset i testy → etap 4: pierwsze badania i raporty → etap 5: API →
etap 6: React i połączenie wyników. Warstwa nieruchomości dopiero po pozyskaniu danych.
Testy odbiorowe: brak utraty bajtów/pól, poprawne rewizje i zakresy, brak lagów przez luki,
nieujemna kontrola dzielników, brak leakage, kompletna lineage i odtwarzalność wyników.
