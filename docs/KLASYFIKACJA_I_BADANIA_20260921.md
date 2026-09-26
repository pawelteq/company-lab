# Rozszerzona klasyfikacja i badania

Wdrożono wymagania przekazane 21 września 2026. Oryginalne pliki i wcześniejszy screening pozostają zachowane. Nowa klasyfikacja jest oddzielnym, odtwarzalnym wzbogaceniem bazy SQLite i ma uzasadnienie przy każdej firmie.

## Kolejność rozstrzygania

1. Mocne słowa development/developer/deweloper/SPV i wzorce projektów/etapów mają pierwszeństwo przed wykluczeniami. Marka z dodatkowym członem nazwy oznacza prawdopodobne SPV, a nie potwierdzenie.
2. Główne PKD 68.12.A oznacza dewelopera, z wyjątkiem jawnego biura projektowego lub handlu materiałami.
3. Wcześniejszy segment mieszkaniowy/komercyjny/mieszany lub jednoznaczny opis dewelopera.
4. Wykluczenia w nazwie i wcześniejszy opis innej działalności. Dostawcy, pośrednicy i administratorzy są poza panelem wykonawców.
5. PKD 41.10.Z i skok sprzedaży po roku z niskim przychodem oznaczają prawdopodobne SPV. Próg pomocniczy: przychód 0–100 tys. PLN, następny rok ≥1 mln PLN i ≥10 razy poprzedni.
6. Neutralna nazwa z „bud”, przychód >5 mln PLN i brak rozstrzygnięcia kieruje do `needs_web_grounding` przed zastosowaniem heurystyki stabilności.
7. Stabilność to ostatnie 3–4 kolejne pełne lata, wszystkie przychody dodatnie, współczynnik zmienności ≤20% i stosunek maksimum/minimum ≤1,5. Reguła pomocnicza wskazuje wykonawcę.
8. Pozostałe słowa z listy deweloperskiej kwalifikują heurystycznie; brak sygnału pozostawia firmę niejednoznaczną.

Słowa dopasowujemy bez polskich znaków i wielkości liter, na granicach słów. Samo „bud” nie jest wykluczeniem. Zerowy przychód nie ustawia nieaktywności. Likwidacja, upadłość, zawieszenie lub status nieaktywny ustawiają `is_active=false`; nieznany status pozostaje nieznany.

## Kwoty, mapa i eksport

Przedziały dotyczą ostatniego pełnego roku kalendarzowego, jednostkowego sprawozdania w PLN. Nie cofamy się do wcześniejszego roku tylko dlatego, że w najnowszym brakuje wartości. Konfliktujące duplikaty nie są arbitralnie rozstrzygane. Granice są włączne; braki nie są zerami. Każda firma pokazuje rok, przychód i zysk użyty do filtra. Katalog, mapa i CSV używają wspólnego filtrowania.

Mapa w iframe i wykresy SVG reagują na kółko myszy w punkcie kursora, zatrzymując przewijanie strony. Wykresy mają reset, obsługę +/− i Home. Mapa zachowuje przyciski przybliżania i „Cała mapa”.

## Badanie

Oddzielne panele: deweloperzy/SPV (wynik dokładnie t+3, t+4) i wykonawcy (t+1, t+2). Minimum 3 kompletne lata, bez progu przychodu. Model wymaga co najmniej dwóch użytecznych par na firmę, zatem długie opóźnienia naturalnie wymagają dłuższej historii.

Miary: zobowiązania **i rezerwy** / aktywa oraz ujawniony dług oprocentowany / dodatni kapitał własny. Pierwsza miara nie oznacza samych pożyczek. Brak komponentu długu pozostaje brakiem. ROA i ROE używają średnich aktywów/kapitału z dwóch kolejnych lat; ROE wymaga dodatniego kapitału. Kontrola logarytmem aktywów, efekty stałe firmy i roku, błędy grupowane po firmie. Raport: wariant surowy i percentyle 1–99, przedziały 90%, p i korekta BH q. Nie interpretujemy związku jako przyczynowego wpływu pożyczek.

Ograniczenia: klasyfikacja według przychodów wykorzystuje pełną historię i nie jest prognozą; możliwy błąd klasyfikacji i przeżywalności aktywnych firm. Roczne dane nie pokazują rzeczywistych przepływów pojedynczej inwestycji. Reguły rozpoznawania przychodu z załącznika służą jako motywacja horyzontów, nie jako uniwersalne stwierdzenie o rachunkowości każdej spółki.

## Weryfikacja w sieci i adresy

Gemini Search Grounding nie jest dostępne w tej sesji. Kolejka 666 podmiotów z KRS, NIP i przygotowanymi zapytaniami jest w `data/classification/web_grounding_queue.json`. Nie wykonano tych zapytań i nie oznaczono firm jako zweryfikowanych. Te podmioty są wyłączone z nowych modeli do czasu rozstrzygnięcia.

Eurobrus KRS 0000372041 / NIP 1231233035: uzupełniono ul. Nowogrodzka 31, 00-511 Warszawa, mazowieckie, na podstawie zrzutu Panorama Firm. To adres katalogowy przekazany przez użytkownika, bez potwierdzenia aktualności rejestrowej. Korekta sprawdza NIP, zapisuje oryginalny adres oraz źródło i działa także przy odbudowie bazy.

Pro-Bud KRS 0000896387 / NIP 7952563375 pozostaje bez pewnego adresu. Strona https://www.pro-bud.pl/kontakt/ przedstawia inną firmę: KRS 0001033956 / NIP 6710000490. Adres św. Wojciecha 4 w Kołobrzegu nie został przypisany błędnemu podmiotowi.

## Odtworzenie

Uruchom z katalogu projektu:

```
.venv/Scripts/python.exe -m backend.profile_enrichment
.venv/Scripts/python.exe -m research.segmented_study
npm --prefix frontend run build
```

Wyniki, wybrane firmy i panel roczny są w `data/research/segmented/<identyfikator>/`. Aplikacja pokazuje `latest.json`. Stare analizy są zachowane w osobnej rozwijanej sekcji.

## Kontrola

Nowe testy obejmują kolizje słów i PKD, neutralne nazwy, SPV bez sprzedaży, stabilność, konfliktujące lata, ochronę przed przypisaniem adresu innej firmie, dokładne opóźnienia oraz zgodność filtrów katalog/mapa/CSV. Kompilacja interfejsu przechodzi.

Pełny historyczny zestaw testów: 76 zaliczonych, 4 pominięte, 4 niezaliczone i 6 błędów. Testy PostgreSQL nie mogą się połączyć z dawną bazą. Stary manifest źródeł nie odpowiada rozszerzonemu katalogowi `firmy_b`. Nie nadpisywano manifestu ani źródeł w celu ukrycia tych rozbieżności.
