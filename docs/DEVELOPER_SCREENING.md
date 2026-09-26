# Bieżące profile i wybór deweloperów — 2026-09-13

Domyślny zbiór aplikacji pochodzi z `firmy_b/raw/profiles`: 3 992 poprawne profile
o unikalnych KRS. Starsze 11 515 firm z panelu finansowego pozostaje dostępne
wyłącznie po wybraniu archiwum. Nie usuwano starszych danych ani wyników badań.

## Wynik kwalifikacji

| Status | Firmy |
|---|---:|
| Deweloper według opisu — domyślna lista | 124 |
| Opis innej działalności | 67 |
| Do sprawdzenia | 237 |
| Brak opisu | 3 564 |
| Wszystkie bieżące profile | 3 992 |

Ponadto **1 253** profili bez opisu ma nazwę zawierającą sygnał deweloperki,
nieruchomości, inwestycji lub mieszkań. Ta liczba jest kolejką do sprawdzenia,
nie dodatkowym statusem i nie sumuje się z tabelą jako osobna kategoria.

428 profili ma niepusty opis. Wszystkie 124 wybrane firmy mają co najmniej jeden
rekord finansowy w profilu; nie oznacza to kompletnej historii ani gotowości do modeli.

## Jak działa wybór

Reguły tekstowe analizują `company.company_summary`, awaryjnie `companySummary.en`
lub `.pl` albo tekstowy `companySummary`. Nie przeszukują opisów podobnych firm,
FAQ ani rankingów. Nie wykonują płatnych zapytań ani wywołań zewnętrznego modelu.

Pozytywna kwalifikacja wymaga opisu dewelopera nieruchomości, działalności real estate
development lub budowy i sprzedaży nieruchomości, kontekstu mieszkaniowego/komercyjnego
oraz zgodności słów identyfikujących podmiot z podmiotem zdania. To heurystyka, nie
niezależna weryfikacja działalności. Nazwa i PKD samodzielnie nie kwalifikują firmy.

Brak opisu, nazwa innej marki, sprzeczny KRS w opisie, opisy usług dla deweloperów,
historycznej działalności, klientów, branży technologicznej i niejasnych ról wymagają
oddzielnego sprawdzenia. Identyczny opis kilku KRS nie kwalifikuje automatycznie tych
spółek do próby. Różne opisy tej samej grupy mogą nie zostać wykryte — to pozostaje
ograniczeniem doboru próby. Segment to dodatkowa wskazówka tekstowa: mieszkaniowy,
komercyjny, mieszany lub nieokreślony.

Przykład użytkownika: KRS 0000023958, Partnerbud, ma opis portalu Awbud.pl.
Status: opis innej działalności; flaga możliwej rozbieżności marki i KRS. Oznacza
wyłączenie z domyślnej listy na podstawie dostarczonego opisu, a nie ustalenie całej
historii działalności spółki.

## Baza, źródła i ponowienie importu

Aktualizacja importera (14.09.2026): odczytuje również sąsiednie foldery
`financials`, `connections` i `structure-people`. Zasady uzupełniania, zachowania
konfliktów i raporty opisuje [Import pełnej paczki](PROFILE_BUNDLE_IMPORT.md).
Liczebności na początku tego dokumentu opisują wcześniejszą kolekcję z 13.09;
aktualne liczby są w aplikacji i podsumowaniu nowego importu.

Migracja 0006 dodaje `core.profile_collection` i `core.profile_screening`, append-only.
Publikacja kolekcji i wszystkich profili jest jedną transakcją. Bieżąca kolekcja jest
najnowszą opublikowaną kolekcją; nie jest odczytem zmieniającego się folderu przy każdym
żądaniu. Identyfikator zależy od manifestu plików i kodu importu/kwalifikacji.

Oryginalne bajty są w `data/raw/profile_objects/<prefix>/<sha256>`. Manifest, raport
liczebności, odrzucone pliki i wyniki kwalifikacji: `data/profiles/<collection_id>/`.
Po dopobraniu opisów uruchom:

```powershell
.venv/Scripts/python.exe -m etl.cli migrate
.venv/Scripts/python.exe -m scripts.import_profiles
```

Następnie odśwież aplikację. Identyczny import nie tworzy kolejnej wersji. Zmieniony
plik albo kod klasyfikacji tworzy nową kolekcję. Kontrolne podsumowania pobierania
(`checkpoint.json`) nie służą do ustalania liczby pełnych profili.

GET `/api/profiles/collections` zwraca kolekcje. GET `/api/profiles?collection=<uuid>`
domyślnie ogranicza listę do `developer_candidate`; filtry `status`, `segment`, `q`,
`limit` i `offset` są walidowane, wartości SQL parametryzowane. GET
`/api/profiles/<krs>?collection=<uuid>` zwraca profil tylko z tej kolekcji.
API zachowuje rolę SELECT-only i nie udostępnia danych osobowych/płatniczych całego RAW.

## Finanse i badania

Profil kandydata pokazuje finanse z preferowanego kontenera bieżącego profilu, z datami,
walutą i zakresem konsolidacji. Lustrzane kontenery nie są sumowane. Różne dokumenty
tego samego roku pozostają osobno. Nie wypełniamy braków zerami, nie przeliczamy walut
i nie wyznaczamy tu panelu rocznego. Kwoty pozostają danymi dostawcy do walidacji.

R01–R04 nie zostały przeliczone dla tych 124 kandydatów. Widok bieżących badań wyjaśnia
ten stan; stare wyniki są oznaczone jako archiwalne. Kwalifikacji na podstawie obecnej
strony nie należy przenosić automatycznie na historyczne lata finansowe.

Weryfikacja: testy granic klasyfikatora (brak opisu, portal, wykonawca, pośrednik,
zaprzeczenie, inny podmiot, oprogramowanie, konflikt KRS), integracja API z aktualną bazą,
kontrola liczebności, domyślnego filtra i uprawnień SELECT-only. TypeScript i build Vite.
W kolejce bez opisu pokazujemy dodatkowo główne PKD, stronę WWW, status dostawcy,
najnowszy przychód jednostkowy i jego rok. Wartości te służą do priorytetyzacji
sprawdzenia; nie zastępują potwierdzenia działalności deweloperskiej.
