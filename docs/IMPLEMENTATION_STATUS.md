# Stan realizacji — 2026-09-12

## Aktualizacja bieżącego widoku — 2026-09-13 wieczorem

Domyślnie aplikacja pokazuje 3 992 profile z aktualnego eksportu, zamiast starego panelu
11 515 firm. Migracja 0006, wersjonowany import i filtr działalności na podstawie
company_summary: 124 kandydatów deweloperskich, 67 opisów innej działalności, 237 do
sprawdzenia, 3 564 bez opisu. Każdy profil ma uzasadnienie, opis, PKD, lokalizację i
pochodzenie; kandydaci mają widok finansów aktualnego profilu. Stare badania pozostają
archiwalne. Dla kolejki 41 firm uruchomiono przekrojową analizę ekonometryczną dla
jednego roku bazowego (2024). Wynik jest eksploracyjny i nie kwalifikuje automatycznie
żadnej firmy jako dewelopera.
Szczegóły, ograniczenia heurystyki i ponowienie importu: [DEVELOPER_SCREENING.md](DEVELOPER_SCREENING.md).

Raport: `data/research/profile_cross_section/3c8d2f80261469ee/report.md`.

## Działa na rzeczywistych danych

- Audyt 23 037 plików źródłowych, 11 517 zidentyfikowanych firm. Surowe źródła zachowane.
- PostgreSQL, migracje 0001–0005, import wznawialny, append-only i pełna weryfikacja źródeł.
- Dataset `3da6dff4-9af8-5652-bb59-b63cb7ccfc07`: 11 515 firm z finansami, 57 866 par firma–rok,
  96 cech, 268 lat bez jednoznacznej selekcji. Dwie firmy mają puste metrics i nie tworzą panelu.
- R00 i cztery badania R01–R04. Run `2ddf2719-26c6-5cc5-86fe-f386b1dbb77d`: 16 podstawowych
  estymacji oraz dwie dodatkowe analizy wrażliwości R01, wszystkie oszacowane.
- FastAPI: paginacja, filtry, historia firmy, lineage, metadane panelu, wyniki modeli.
- React/TypeScript/Vite: przegląd pokrycia, katalog, profil/finanse, źródła wskaźników,
  wybór zapisanej wersji obliczeń, modelu OLS/FE i wariantu bez przycinania/winsoryzacji.
- Osobny login API tylko do odczytu, brak serwowania źródeł i konfiguracji z dysku.
- Diagnostyka `61a348bb-d9b9-5edb-a3f5-820e04d1c344`: 20 przypadków (14 firm),
  rozkłady, małe mianowniki, pełna lineage i 20 estymacji po pominięciu firmy.
  Widok diagnostyki w Badaniach ładuje źródła pojedynczego przypadku na żądanie.

## Wyniki badań i ich granice

Główne cztery testy FE bez przycinania mają q BH ≈ 0,9351. Nie dają podstaw do odrzucenia
hipotez zerowych na poziomie 5%; to nie jest dowód braku związku. Przedziały są szerokie,
a wyniki części wariantów zmieniają się po winsoryzacji. Pełne współczynniki, CI, p, N i
przepływy próby w RESEARCH_RESULTS. Nie wnioskujemy o przyczynowości ani optimum strategii.

Dataset pozostaje `exploratory_reported`, `research_ready=false`. Skala/waluta/mapowanie
większości źródeł nie zostały niezależnie zwalidowane. Nie ma dat historycznej dostępności
informacji, pełnej branży/regionu ani danych projektowych. Obecne snapshoty osób i firm
nie stanowią poprawnej historii zmian właścicielskich.

## Zweryfikowano

- Wcześniej pełny zestaw 27 testów audytu/importu/panelu; osobno testy estymatora.
- Po dodaniu API: 15 testów API/cech/modeli przeszło (read-only na rzeczywistym panelu).
- TypeScript strict i produkcyjny build Vite przeszły; JS ok. 77 kB gzip.
- Test przeglądarkowy: wyszukanie KRS, profil, wykres, lineage, przełączenie OLS/FE i
  wariantu estymacji, widok mobilny, brak błędów JavaScript. Zrzuty wizualnie sprawdzone.
- Konto company_api nie ma uprawnień INSERT/UPDATE; transakcje read-only.
- Po dodaniu diagnostyki: 9 testów API/diagnostyki przeszło; zgodność manifestu i całego
  JSON wyniku z DB, odtworzenie czterech bazowych modeli, poprawność lat mianowników.
  Migracja 0005 przeszła również na bazie testowej. Ponowny run zweryfikował istniejące
  artefakty bez utworzenia duplikatu. Test przeglądarkowy obejmuje teraz także diagnostykę.

## Jeszcze nie zaimplementowano

Samodzielne uruchamianie dowolnych modeli z UI/kolejka zadań; RE/GMM/event studies;
peer group, clustering, early warning, historyczny graf; nieruchomości i Decision Lab.
Zakładki przyszłych modułów jawnie pokazują brak danych/modelu. Widok Modele przegląda
zapisane estymacje, nie jest jeszcze edytorem nowych specyfikacji. Finanse używa widoku firmy.
Brak logowania/uprawnień użytkowników i publicznego wdrożenia; serwer działa na loopback.

## Rozszerzenie źródeł — 2026-09-13

W projekcie korzystamy z [Compabase API](https://github.com/ContentWriterco/Compabase-API).
Użytkownik zbiera firmy według głównego PKD: 41.10.Z i 41.20.Z (2007) oraz
68.11.Z i 68.12.A (2025). Adapter przechowuje kod razem z wersją, bez automatycznego
uznawania firmy za dewelopera. Dashboard pokazuje dostawcę, dokumentację i zakres zbierania.

Audyt folderu `referencja`: cztery pliki, jedna firma, sześć różnych rekordów finansowych
w 18 reprezentacjach. Brak konfliktów liczbowych we wspólnych niepustych polach objętych
porównaniem. Dwa odrębne okresy 2020 roku pozostają zachowane. Surowe pliki zarchiwizowano
z sumami SHA-256; nie dodano próbek do produkcyjnego panelu. Szczegóły w
REFERENCE_DATA_AUDIT.md oraz COMPABASE_API.md. Siedem testów adaptera i katalogu źródeł
oraz produkcyjny build frontendu przeszły. Test przeglądarkowy potwierdził nazwę źródła,
link dokumentacji i cztery PKD, wyszukiwanie firmy, lineage, badania, diagnostykę oraz
brak poziomego przewijania na telefonie i błędów JavaScript. Przy pierwszej próbie baza
była wyłączona; po jej uruchomieniu cały test przeszedł.

Pełne profile i wersjonowane działalności mają zaprojektowane tabele w DATA_MODEL.md;
ich migracja i import nowego zbioru do bazy nie są jeszcze wykonane. Adapter i audyt
pracują obecnie na plikach poglądowych. Nie uruchamiano płatnych zapytań do API.

Zachowano też oryginalny XML RDF dla DDC (KRS 0000994050), dokument 8529793.
Potwierdza 0,03 PLN przychodów finansowych w 2023 roku; to dowód dotyczący jednego
sprawozdania, nie walidacja skali całego panelu. Oryginał i metadane dowodu są w
`data/raw/rdf_objects` oraz `data/audit/rdf_evidence`. Nie zweryfikowano kryptograficznie podpisu.

## Pozostałe prace nad walidacją

Raport diagnostyczny jest gotowy: DIAGNOSTIC_FINDINGS, MODEL_DIAGNOSTICS i DIAGNOSTIC_PROTOCOL.
Kolejny krok: zweryfikować mapowanie oraz skale wskazanych KRS/lat w źródłowych
sprawozdaniach lub dokumentacji dostawcy. Same skrajności nie dowodzą niespójności jednostek.
Decyzje kwalifikacji zapisać jako nową warstwę, bez zmiany RAW i istniejącego panelu.
Dopiero po tym opublikować nowy dataset i porównać wyniki według ustalonego protokołu.
