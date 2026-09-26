# Mapa jako filtr katalogu

W zakładce **Firmy** znajduje się mapa w lokalnym iframe. Kliknięcie województwa wybiera region i przybliża mapę. Kliknięcie punktu miasta albo miejscowości na liście filtruje katalog. Wybór miasta przełącza mapę na punkty. Wybrany element jest zielony, pozostałe szare. Ponowne kliknięcie tego samego elementu lub przycisk **Wyczyść lokalizację** usuwa wybór. **Cała mapa** zmienia tylko przybliżenie, zachowując filtr.

Wyszukiwarka miejscowości obsługuje nazwy bez polskich znaków. Filtr lokalizacji łączy się z wyszukiwaniem firm, statusem kwalifikacji i segmentem. Liczniki mapy uwzględniają te pozostałe filtry, zachowując pozostałe lokalizacje do porównania. Lista i eksport CSV stosują ten sam warunek miejscowości oraz województwa; wybór zeruje stronę katalogu.

## Dane i dokładność

Adres siedziby pochodzi z już zaimportowanych profili. Nie są to lokalizacje inwestycji ani dokładne punkty budynków. Przybliżone punkty miejscowości pobrano z [GeoNames](https://www.geonames.org/) (CC BY 4.0), a uproszczone granice z [Eurostat / GISCO](https://gisco-services.ec.europa.eu/distribution/v2/nuts/) (NUTS 2024, skala 1:20 mln). Mazowieckie jest jednym województwem: użyto granicy PL9 zamiast dwóch regionów statystycznych PL91 i PL92. Mapa zawiera 16 województw.

Dopasowanie wykorzystuje nazwę miejscowości i województwo. Jednoznaczne rekordy rejestru miejscowości mają pierwszeństwo. Pomocniczo używany jest zbiór kodów pocztowych: punkty tej samej miejscowości w jednej gminie są uśredniane. Homonimy w różnych gminach nie są automatycznie przypisywane do największego miasta. Takie wpisy pozostają na liście z oznaczeniem **bez pewnego punktu**. Filtr miejscowości oznacza parę nazwa–województwo, nie unikalny identyfikator gminy.

Dla kolekcji `6c063c3c-2c7c-5270-825e-778093946fb9`: 32 918 firm, 3574 grupy lokalizacji, punkty dla 30 797 firm (93,56%), 2121 firm bez jednoznacznego punktu. Dwie firmy nie mają miasta ani województwa. Żadna firma nie została usunięta z katalogu.

## Odtworzenie

Uruchom z katalogu projektu:

```powershell
.venv/Scripts/python.exe -m scripts.build_geography
npm run build --prefix frontend
```

Pierwsze uruchomienie pobiera publiczne archiwa. Późniejsze korzystają z kopii w `data/geography/`. Dane gazetteera znajdują się w `data/geography/places.json`, granice województw w `frontend/public/maps/poland.json`, granice powiatów w `frontend/public/maps/powiaty.json`, a granice gmin w `frontend/public/maps/gminy.json`. Mapie nie przekazuje się pojedynczych profili ani adresów: otrzymuje tylko miejscowości i zagregowane liczby firm. Działa bez zewnętrznych kafelków i bez klucza API.

Po zmianie kodu backendu uruchom ponownie serwer. Nowe importy korzystają z tego samego słownika miejscowości; endpoint `/api/profiles/locations` zawsze liczy bieżącą kolekcję. Brak słownika nie blokuje listy miejscowości i filtrowania, ale wyłącza punkty.

## Sprawdzenie

Testy `tests/test_geography.py` sprawdzają połączenie filtrów, rozróżnienie miejscowości o tej samej nazwie w różnych województwach, zgodność eksportu, brak danych geograficznych i nieznaną kolekcję. Sprawdzono też interakcję iframe z katalogiem w przeglądarce: Warszawa 6473 firmy, Małopolskie 4040 firm, czyszczenie wyboru oraz wyszukiwanie bez polskich znaków.

Przytrzymanie lewego przycisku myszy i przeciąganie przesuwa mapę także po przybliżeniu. Ruch mniejszy niż 5 pikseli pozostaje kliknięciem; przeciąganie nie zmienia filtra. Przycisk **Cała mapa** przywraca widok Polski. Przyciski **Powiaty** i **Gminy** pozwalają włączyć lub wyłączyć wyświetlanie granic administracyjnych niższego szczebla (z nazwami widocznymi po najechaniu).
