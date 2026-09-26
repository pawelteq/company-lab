# Audyt czytelności interfejsu — 14.09.2026

Zakres: działające ekrany bieżącego zbioru — Dashboard, katalog firm, profil z finansami i powiązaniami, Badania. Kontrola kodu, rzeczywistych danych i zrzutów z Chrome. Zachowano zieloną kolorystykę aplikacji.

## Ustalenia i poprawki

| Problem | Wprowadzona poprawka |
|---|---|
| Liczne opisy i nagłówki miały 7–11 px, a pomocniczy tekst był bardzo jasny. | Tekst podstawowy 16 px, tabele 14 px, większość opisów 13 px; ciemniejsze kolory opisów, nagłówków i etykiet. |
| Niespójne rozmiary i odstępy pomiędzy kartami, filtrami i danymi. | Ujednolicona hierarchia nagłówków, odstępy, powierzchnie kart i przyciski o wysokości co najmniej 44 px. |
| Filtry miały wyłącznie etykiety dla czytnika ekranu. | Stałe, widoczne podpisy wyszukiwarki, kwalifikacji, segmentu i sortowania. Kierunek opisany słowami. |
| Nazwy firm i dane w tabelach konkurowały o niewielką szerokość. | Minimalne szerokości kolumn, naprzemienne tła wierszy, lokalne przewijanie, wskazówka nad katalogiem. Nazwa firmy otwiera profil, także bez przewijania do ostatniej kolumny. |
| Długie liczby na osi wykresu były ucinane. | Margines wyliczany z długości etykiet. Wykresy w jednym rzędzie pionowym, z czytelnym rozmiarem i przewijaniem na mniejszych ekranach. |
| Mapa była pomniejszana, a długa lista relacji rozciągała pusty obszar. | Minimalna szerokość mapy, przewijanie, ograniczona wysokość listy szczegółów; etykiety powiązań wyróżniane dla aktywnego węzła. |
| Wąskie ekrany ściskały statystyki, kontrolki i etykiety. | Poprawione układy kart i filtrów, zawijanie oznaczeń oraz nagłówka; brak przewijania całej strony w poziomie w sprawdzonych widokach. |
| Przewijane dane nie miały jawnej obsługi fokusu. | Regiony tabel i schematów dostępne klawiaturą, wyraźniejszy fokus, link „Przejdź do treści”, oznaczenie aktywnego ekranu. |
| Wygląd zależał od zewnętrznego importu fontów. | Usunięty import sieciowy; jawny systemowy zestaw zapasowy Segoe UI / Arial. |

## Weryfikacja

- Kompilacja TypeScript i produkcyjny build Vite.
- Skrypt `scripts/audit_readability.cjs`: cztery widoki na szerokościach 1440, 1024, 768, 390 i 320 px; kontrola szerokości strony, tekstu HTML poniżej 12 px i etykiet formularzy.
- Sprawdzenie klawiaturą linku do głównej treści, wyszukiwania, sortowania, pobrania CSV i otwierania profilu przez nazwę.
- Kontrola wizualna dashboardu, katalogu, profilu i wykresów; zrzuty oraz wyniki w `.local/audit-*.png` i `.local/readability-results.json`.

## Granice audytu

To audyt stylistyki i czytelności bieżących widoków, nie certyfikacja WCAG ani audyt bezpieczeństwa lub jakości finansów. Wspólne style obejmują również komponenty archiwalne, ale archiwum nie zostało przetestowane jako odrębny przepływ.

Istniejący `scripts/smoke_ui.cjs` zatrzymuje się na oczekiwaniu sekcji „Obliczenia dodatkowe”: komponent tej sekcji nie jest wywoływany w obecnym widoku finansów. Ten problem występował przed zmianami stylistycznymi; nie zmieniano zakresu prezentowanych obliczeń. Bieżące przepływy sprawdza oddzielny skrypt audytu.
