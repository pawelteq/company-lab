# Import pełnej paczki Compabase

Importer obsługuje katalog projektu `firmy_b` z układem:

```text
firmy_b/raw/
  profiles/<KRS>.json
  financials/<KRS>.json
  connections/<KRS>.json
  structure-people/<KRS>.json
```

Uruchomienie z katalogu projektu, przy działającej bazie:

```powershell
.venv/Scripts/python.exe -m scripts.import_profiles --source firmy_b
```

Dotychczasowe wywołanie bez parametrów również odczytuje dodatkowe foldery obok `profiles`. Należy pozostawić starsze profile w folderze, jeżeli mają pozostać w bieżącym katalogu. Import tworzy nową wersję całej kolekcji; nie dopisuje nowych firm do poprzedniej kolekcji. Po zakończeniu wystarczy odświeżyć aplikację.

## Zasady łączenia

- Bazą jest profil o nazwie zgodnej z jego KRS. Odpowiedzi dodatkowe dobierane są po tej samej nazwie pliku. KRS w odpowiedzi, jeżeli występuje na poziomie głównym lub w rekordzie finansowym, musi być zgodny.
- Rekordy finansowe łączone są po identyfikatorze rekordu `id`, a nie po roku ani kolejności. Odrębne sprawozdania z tego samego roku pozostają osobne. Rekord bez identyfikatora, który można pomylić z istniejącym okresem, zatrzymuje publikację.
- Dodatkowe pola i wartości w miejsce `null` uzupełniają profil. Różne niepuste wartości nie są automatycznie nadpisywane: pozostaje wartość profilu, a ścieżka rozbieżności trafia do raportu.
- Tablic osób, ról i powiązań nie łączymy po pozycji. Puste role/własność można uzupełnić. Różne niepuste listy pozostają w osobnych źródłach i są oznaczone jako konflikt. To nie oznacza automatycznego uzgodnienia wszystkich danych osobowych lub relacji.
- Oryginalne pliki ze wszystkich folderów są archiwizowane po SHA-256. Manifest obejmuje każdą odpowiedź, więc zmiana dowolnego źródła zmienia wersję kolekcji.
- Niepoprawna paczka lub plik dodatkowy bez profilu nie powoduje publikacji niepełnego zbioru. Odrzucone paczki opisuje `.local/profile-import-rejected.json`.
- Znacznik `hasMore` z dowolnej odpowiedzi finansowej pozostaje ostrzeżeniem o niepełnej historii. Importer nie wykonuje zapytań do Compabase ani nie pobiera następnych stron.

## Wyniki i pochodzenie

W `data/profiles/<collection_id>/` powstają: `summary.json`, `manifest.json`, `merge_report.json` oraz `screening.json`. Raport łączenia wskazuje dodane ścieżki, konflikty i hashe źródeł. Oryginały: `data/raw/profile_objects/<pierwsze 2 znaki SHA>/<SHA>`.

`source_sha256` profilu nadal identyfikuje bazową odpowiedź `profiles`. `source_files` wskazuje wszystkie użyte odpowiedzi. Finansowe `source_pointer` wskazuje złożony kontener (`source_container=assembled_profile`), dlatego nie należy interpretować go jako ścieżki do pojedynczego oryginalnego pliku.

Nowa kolekcja ma nowy identyfikator. Ręczne decyzje zapisane w przeglądarce dla starej kolekcji nie są automatycznie przenoszone — mogła zmienić się treść profilu.

Testy zasad łączenia: `tests/test_profile_bundle.py`.

## Zakończony import — 14.09.2026

Kolekcja: `30a4178a-1255-5121-bac0-5cf9c65386d5`.

- 6957 firm, 27 828 plików źródłowych; żadna paczka nie została odrzucona.
- 154 kandydatów według opisu, 78 opisów innej działalności, 311 do sprawdzenia, 6414 bez opisu.
- 6836 paczek zawiera rozbieżności źródeł, w tym różnice struktur/list i metadanych; to nie jest liczba błędnych wartości finansowych.
- Potwierdzono publikację przez API, liczebność całego katalogu oraz dodatkowe pola finansowe w profilach KRS 0000023958 i 0000005938.
- 32 testy importera, adaptera, kwalifikacji i API zakończyły się powodzeniem po publikacji.
