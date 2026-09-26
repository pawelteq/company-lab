# Model danych — projekt

Status: model docelowy, częściowo wdrożony, aktualizacja 12.09.2026. Migracje 0001/0002 realizują
`raw`, identyfikację KRS w `core` oraz `staging`. Migracja 0003 wdraża eksploracyjny
`analytics`; 0004 wdraża `research.run`. Pozostałe tabele research i property pozostają
projektem. Wszystkie czasy audytowe TIMESTAMPTZ UTC.

Migracja 0005 dodaje `research.diagnostic_run`: id, research_run_id FK, version_hash UNIQUE,
code_hash, protocol, results, artifact_manifest, created_at. Append-only, indeks na runie i dacie.
Wyniki zachowują wybór przypadków, odniesienia mianowników, źródła oraz osobne estymacje
wrażliwości. Nie nadpisują research.run ani analytics.company_year.

Wdrożony `research.run`: UUID, dataset_id FK, run_hash UNIQUE, code_hash, specification JSONB,
results JSONB, artifact_manifest JSONB, inference_class i created_at. Rekord niezmienny,
klasa wniosku ograniczona do exploratory_conditional_association. Dane wynikowe obejmują
przepływ próby, modele, współczynniki, błędy standardowe, CI, p, q BH, N, R², konfigurację
klastrów SE i skalowanie numeryczne. Pliki próbek mają hashe, poprzednie runy pozostają dostępne.

Wdrożony staging: `staging.financial_record` (pełne pochodzenie, daty, zakres, 42 wartości
reported_metrics, profil, quality_codes) oraz `staging.relationship_snapshot` (FK do
pełnego JSON grafu, liczebności, historyczna ważność nieznana). Szczegóły pozostają w RAW,
nie znikają przy promowaniu wybranych liczb. `staging.company_year_conflicts` grupuje
kandydatów osobno dla batcha. Brak selekcji rocznej na tym etapie.

Uproszczenie identyfikacji v1: `core.company` ma zweryfikowany format KRS z UNIQUE;
`core.company_snapshot` zachowuje metadane każdego źródła z FK. Wielorejestrowe
company_identifier/attribute i pozostałe tabele poniżej będą dodawane w kolejnych migracjach.
`raw.ingestion_event` rejestruje status bez aktualizacji immutable batcha.

## Warstwa źródłowa

### Rozszerzenie pełnych profili Compabase (2026-09-13)

Adapter przygotowuje `profile_snapshot` z company_id/KRS, FK do raw.record, JSON Pointer,
observed_at, provider_extracted_at i provider_state_date. NIP/REGON pozostają tekstem;
lokalizacja ma osobne city/region/country/full_address. Nie przypisujemy obserwacji profilu
do historycznego roku finansowego. Planowane tabele przy imporcie pełnego wsadu:

- `core.company_activity_snapshot`: profile_snapshot_id, code, classification_version
  (2007/2025/NULL), reported_version, is_primary (TRUE/FALSE/NULL), description, source_pointer.
- `raw.collection_membership`: capture/batch, collection_query_id, KRS, filtr i moment
  pobrania. Zachowuje przynależność do więcej niż jednej z czterech kohort.
- `core.company_location_snapshot`: profil, miejscowość, region, adres, pochodzenie;
  współrzędne wyłącznie gdy faktycznie dostępne i z metodą geokodowania.

Klucz PKD obejmuje kod i wersję. Deduplikacja firmy po KRS nie usuwa snapshotów ani
różnych członkostw kohort. Wersja nieznana pozostaje NULL; nie mapujemy 41.10.Z → 68.12.A
bez udokumentowanej reguły. Brak automatycznej klasyfikacji mieszkaniowego dewelopera.
Adapter i testy gotowe; tabele te nie są jeszcze migracją produkcyjną dla plików poglądowych.

| Tabela | Klucz i główne pola | Reguła |
|---|---|---|
| raw.ingestion_batch | id UUID PK, source, observed_at, manifest_hash, parser_version | Jeden spójny import |
| raw.object | sha256 TEXT PK, storage_uri, byte_size, media_type | Niezmienne bajty, SHA-256 weryfikowany przy zapisie/odczycie |
| raw.capture | id PK, batch_id FK, object_sha FK, original_path, source_endpoint, fetched_at nullable | Ta sama treść może być pobrana wielokrotnie; data pobrania nie jest datą publikacji |
| raw.record | id PK, capture_id FK, locator, parsed_payload JSONB, parse_status | UNIQUE(capture_id, locator); JSON Pointer lub numer logicznego wiersza CSV |
| raw.quality_issue | id PK, record_id FK, code, severity, field_path, detail | Pełny rejestr, bez kasowania źródła |

`raw` append-only dla roli ETL; bez UPDATE/DELETE. Triggery i uprawnienia zabezpieczą tabele,
a magazyn obiektów wersjonowanie/retencja. JSONB nigdy nie zastąpi `raw.object`.
Brakujące oryginalne dokumenty XML/PDF nie są zastępowane wymyślonymi dokumentami.

## Podmioty i identyfikacja

| Tabela | Klucz i główne pola |
|---|---|
| core.company | company_id UUID PK, created_at |
| core.company_identifier | id PK, company_id FK, scheme (KRS/NIP/REGON/provider), value TEXT, valid_from/to nullable, record_id FK |
| core.company_attribute | id PK, company_id FK, name, value JSONB, valid_from/to nullable, observed_at, record_id FK, field_path |
| core.industry_assignment | id PK, company_id FK, scheme_version, code, primary_flag, valid_from/to, evidence_record_id FK |
| core.location | id PK, country, region, city, address, lat/lon nullable, geocode_method, confidence |
| core.company_location | company_id FK, location_id FK, valid_from/to, observed_at, evidence_record_id FK |

KRS ma 10 cyfr tekstowych; nie konwertujemy na liczbę. Rejestr konfliktów identyfikatorów;
unikalność aktualnego KRS wśród zweryfikowanych przypisań, bez łączenia po samej nazwie.
Zewnętrzne UUID Compabase są identyfikatorami dostawcy, a nie jedynym kluczem systemu.
PKD bez daty i wersji nie służy do historycznej segmentacji. Brak NIP/REGON w CSV może
być częściowo uzupełniany innym źródłem tylko z pochodzeniem i walidacją.

## Sprawozdania i pełne finanse

| Tabela | Klucz i główne pola | Reguła |
|---|---|---|
| core.statement | statement_id UUID PK, company_id FK, provider_document_id, provider_metric_id, raw_record_id FK, period_start/end, original_period_start/end, period_resolution_method, fiscal_year, duration_days, scope, currency, unit_scale, accounting_standard, layout, published_at, extracted_at, revision_of FK nullable | Każdy kandydat osobno; unknown odróżnione od standalone |
| core.metric_definition | metric_code PK, description, unit, denominator_policy, mapping_version | Słownik biznesowy |
| core.statement_value | id PK, statement_id FK, metric_code FK, value NUMERIC, original_value TEXT, source_path, mapping_version, quality_status | UNIQUE(statement_id, metric_code, mapping_version); nieznana liczba nie jest zerem |
| core.statement_line | id PK, statement_id FK, statement_kind, line_code, ordinal, parent_line_id FK, value NUMERIC nullable, original_value JSONB, source_path, layout_version | UNIQUE(statement_id, source_path); zachowane wszystkie szczegóły i kolejność |
| core.statement_selection | dataset_id FK, company_id FK, year SMALLINT, statement_id FK nullable, selection_rule_version, status, reason | UNIQUE(dataset_id, company_id, year); unresolved też ma zapis |

Kwoty NUMERIC bez narzuconego obcięcia do dwóch miejsc w źródłach, prezentacja dopiero w UI.
JSON liczbowy parsowany do Decimal przed normalizacją. Kontrole dat `end >= start`,
waluty/scale jawne; NULL dopuszczalny z flagą niewiadomej. Nie sumujemy jednostkowych
i skonsolidowanych sprawozdań. Główny panel standalone; consolidated osobny dataset.

Nie interpretujemy kodu `A` uniwersalnie: znaczenie zależy od bilansu/RZiS, wariantu,
profilu formularza i wersji mapowania. `esf_statement_lines` i `*_key_order` są zachowane.
Literówki dostawcy (np. `short_term_liilities_tax`) mają jawny alias; kolizja aliasu to problem jakości.

## Panel i pochodzenie cech

Wariant wdrożony v1: `analytics.dataset(id,batch_id,version_hash,code_hash,config,maturity,
research_ready,artifact_manifest)`, `feature_definition(dataset_id,name,definition)`,
`selection_candidate(dataset_id,company_id,year,financial_record_id)` i
`company_year(dataset_id,company_id,year,selected_record_id,selection_status,n_years,
n_selected_years,n_annual_years,panel_*,features JSONB,missing_reasons JSONB,quality_codes)`.
PK firma–rok zawiera dataset_id. FK wyboru prowadzi do kandydata w tej samej firmie/roku/datasetcie.
Dokładne liczby w JSONB; trace rozwija zapisane definicje operatorów, wejść i offsetów do RAW.
Tabela poniżej opisuje dalszy docelowy wariant z osobną tabelą każdej wartości i wejścia;
nie należy utożsamiać jej z już wdrożonym SQL.

| Tabela | Klucz i główne pola |
|---|---|
| analytics.dataset | dataset_id PK, manifest_hash, code_version, config JSONB, mapping_version, created_at, status, artifact_uri, artifact_hash |
| analytics.company_year | dataset_id FK, company_id FK, year, statement_id FK, n_years, panel_full, panel_3plus, panel_5plus, panel_long, monetary columns, ratio columns, flags | 
| analytics.feature_definition | feature_id PK, name, version, formula, units, prerequisites JSONB, missing_rules, temporal_alignment |
| analytics.feature_value | id PK, dataset_id FK, company_id FK, year, feature_id FK, value NUMERIC nullable, status, reason |
| analytics.feature_input | feature_value_id FK, input_statement_value_id FK nullable, input_feature_value_id FK nullable, input_role |

PK panelu: `(dataset_id, company_id, year)`; UNIQUE cechy:
`(dataset_id, company_id, year, feature_id)`. Dokładnie jeden rodzaj wejścia w każdym
wierszu feature_input (CHECK XOR). Zależności cech muszą tworzyć DAG, sprawdzany przy buildzie.
Każda cecha prowadzi przez wejścia i sprawozdanie do record/capture/object i ścieżki w źródle.
Szeroka tabela jest widokiem/materializacją zatwierdzonych cech, a nie drugim źródłem prawdy.

### Definicje cech v1

Wszystkie ilorazy analityczne są ułamkami (0.15 = 15%), zmiany ilorazów różnicą ułamków;
UI może mnożyć je przez 100 i podpisywać punktami procentowymi. Wszystkie składniki
tej samej firmy, zakresu, waluty i porównywalnego okresu.

| Cechy | Definicja i dziedzina |
|---|---|
| revenue/profit/asset/equity_growth | `x_t / x_(t-1) - 1` tylko dodatnia baza; przy zerowej/ujemnej bazie NULL z powodem; zmiana znaku i delta osobno |
| profit_change_scaled | `(profit_t-profit_(t-1))/assets_(t-1)` przy dodatnich aktywach; również dla strat |
| log_revenue/assets/equity | ln(x) tylko x>0, bez przesuwania stałą |
| liabilities_to_assets/equity | liabilities_and_provisions / dodatnie assets lub equity; to szerokie zobowiązania z rezerwami, nie wyłącznie dług odsetkowy |
| interest_bearing_debt_to_assets | tylko po weryfikacji mapowania kredytów/pożyczek/obligacji/leasingu; bez sumowania pokrywających się pól |
| short/long_term_liabilities_to_assets | odpowiednia pozycja / dodatnie assets |
| current_ratio, cash_ratio | current_assets lub cash / dodatnie short_term_liabilities |
| cash_to_assets, equity_to_assets | cash lub equity / dodatnie assets; ujemny kapitał zachowany |
| roa_end, roe_end | profit_net / dodatnie assets lub equity na koniec okresu |
| roa_avg, roe_avg | profit_net / dodatnią średnią z początku i końca; wymaga ciągłych, porównywalnych okresów; osobna analiza wrażliwości |
| net_margin, ebitda_margin | profit_net lub ebitda / dodatnie revenue_total; definicja revenue_total wymaga walidacji wariantu |
| asset_turnover | revenue_total / dodatnie assets; wersja avg osobno |
| receivables_to_assets/revenue | short_term_receivables / dodatni mianownik |
| cash_to_revenue | cash / dodatnie revenue_total |
| inventories_to_assets, current_assets_to_assets | odpowiednia pozycja / dodatnie assets |
| delta_leverage/liquidity/roa/margin | różnica odpowiedniego wskaźnika r/r |
| delta_cash/receivables/assets/equity | zmiana kwoty; dodatkowo jawne `*_to_assets_change` dla różnicy udziałów |
| debt_growth, cash_growth, receivables_growth | dodatnia baza, identyczna zasada jak growth powyżej |
| debt_lag1/2/3 | alias liabilities_to_assets z roku t−k; nazwa/etykieta wskazuje szerokie zobowiązania |
| liquidity_lag1, roa_lag1, size_lag1 | current_ratio, roa_end, log_assets z dokładnego roku t−1 |
| forward_y_h1/h2/h3 | outcome z dokładnego t+h; przyszła informacja tylko jako Y, nigdy jako X w t |
| rolling_3y | trzy kolejne lata, jawne min_periods=3; kończy się w t dla cech w t |

Nie używamy `groupby.shift` bez kontroli lat. Do dynamik bazowych wymagamy sąsiadujących
pełnych okresów; nie rocznimy automatycznie skróconego roku. Małe dodatnie mianowniki
oznaczamy; progi stabilności i warianty winsoryzacji wersjonujemy, nigdy nie zmieniamy RAW.
Brakujące cechy nie powodują skasowania obserwacji z panel_full.
Klasy panelu liczone z unikalnych wybranych lat, nie liczby dokumentów; kwalifikacja do
badania dodatkowo zależy od kompletności jego zmiennych. Dla predykcji `n_years` i klasa
historyczna są liczone wyłącznie z historii dostępnej w chwili predykcji.

## Powiązania

`core.party(party_id PK, type, company_id nullable)`;
`core.person_identifier(id PK, party_id FK, provider, external_id, evidence_record_id FK)`;
`core.relationship(id PK, source_party_id FK, target_party_id FK, kind, role,
holding_percent NUMERIC, holding_value NUMERIC, currency, valid_from/to nullable,
observed_at, evidence_record_id FK, source_path, confidence)`.
Procent udziałów kontrolowany 0–100; nieprawidłowe wartości zachowane w RAW/issue.
Kierunek ownership/subsidiary weryfikowany względem źródła, bez zgadywania z nazwy.
Oddzielamy relację osobową, beneficjenta i udział kapitałowy; nie sumujemy wielokrotnych
reprezentacji tej samej relacji z people/related_companies/graph. Snapshot grafu ma datę obserwacji.

## Badania i przyszła warstwa nieruchomości

`research.study` — pytanie, protokół, hipotezy, horyzont, korekta wielokrotności;
`research.run` — dataset FK, spec JSONB, hash, seed, runtime versions, status, próba i wykluczenia;
`research.result` — współczynnik, SE, CI, p, rodzaj R2, N firm/wierszy, efekty, diagnostyka,
klasa wniosku i artefakty; `research.model_version` — trening, test czasowy, kalibracja, domena
zastosowania; `research.event_definition/event_occurrence` — próg, data i dowody zdarzenia.

Docelowo `property.developer_classification` (A–E, dowody, reviewer, data),
`project`, `project_company_role` (SPV/wykonawca/inwestor, daty, udziały), `unit`,
`price_observation` (cena ofertowa/transakcyjna, waluta, VAT, powierzchnia, data),
`market_benchmark` (obszar/segment/okres, liczebność, metoda, wyłączenie własnego projektu),
`sales_observation` (dostępność i cenzorowanie), `project_cashflow`, `scenario`.
Każda obserwacja z FK do źródła. Brak tabel projektowych w dzisiejszych danych nie jest
uzupełniany domniemaniami z PKD ani z finansów spółki.

## Indeksy i migracje

B-tree identyfikatorów `(scheme,value)`, sprawozdań `(company_id,period_end,scope)`,
panelu `(dataset_id,year)` i `(dataset_id,company_id,year)`, obu końców relacji,
jobów `(status,created_at)`; indeksy filtrów branża/region dopiero po ich uzupełnieniu.
GIN tylko dla faktycznie wyszukiwanych JSONB, nie dla każdej dużej struktury.
Wykonane migracje Alembic: 0001 raw/identity, 0002 staging/provenance/diagnostics,
0003 panel/feature definitions/selection, 0004 research runs, 0005 diagnostics.
Następne: zwalidowane canonical statements, rozszerzenia research, normalized relations;
property później. Migracje sprawdzane na osobnej pustej testowej DB; kasujący downgrade
odmawia wykonania, aby nie usuwać źródeł. Dalsze zmiany przez nowe migracje.
