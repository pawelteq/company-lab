# Company Lab

Aplikacja do przeglądania firm, ich finansów i powiązań oraz badania zależności między zadłużeniem a późniejszymi wynikami. Polski interfejs działa na komputerze i telefonie. Projekt Android korzysta z Capacitor.

## Funkcje

- Katalog firm z wyszukiwaniem i filtrami.
- Ręczna i automatyczna weryfikacja firm z filtrem: zweryfikowane, potwierdzone, odrzucone lub niezweryfikowane.
- Finanse, wykresy, historia sprawozdań i powiązania osób.
- Finansowa mapa Polski z agregacją dla województw, powiatów i gmin, filtrem PKD, rankingiem i porównaniem regionów.
- Słowniczek oraz wnioski z badań opisane prostym językiem.
- Rozwijane szczegóły dla bardziej zaawansowanych użytkowników.
- Modele panelowe z opóźnieniem 1–3 lat i analizą wrażliwości.

Technologia: React, TypeScript, Vite, FastAPI, Python, SQLite i Capacitor. PostgreSQL jest opcjonalny i służy starszemu pipeline'owi. Badania są eksploracyjne: zależność statystyczna nie oznacza przyczynowości.

## Najprostsza instalacja na Windows

Repozytorium zawiera samą aplikację — bez prywatnych danych firm. Po pobraniu projektu:

1. Zainstaluj [Python 3.12](https://www.python.org/downloads/) i [Node.js 22 LTS](https://nodejs.org/).
2. Kliknij dwa razy `INSTALUJ.bat` i poczekaj na komunikat o zakończeniu.
3. Zaimportuj otrzymaną paczkę danych zgodnie z sekcją poniżej.
4. Kliknij dwa razy `URUCHOM_STRONE.bat`. Strona otworzy się pod adresem <http://127.0.0.1:8000/>.

Instalator tworzy prywatne środowisko projektu, pobiera wymagane biblioteki i buduje interfejs. Nie trzeba wpisywać poleceń w terminalu.

### Przenoszenie wszystkich danych jednym ZIP-em

Na komputerze, na którym dane już działają:

1. Kliknij `EKSPORTUJ_DANE_DO_ZIP.bat`.
2. Gotowa paczka pojawi się w katalogu `PACZKI_DANYCH`.
3. Przekaż ZIP bezpiecznym kanałem. **Nie dodawaj go do GitHuba** — zawiera całą lokalną bazę firm.

Na drugim komputerze:

1. Najpierw uruchom `INSTALUJ.bat`.
2. Przeciągnij otrzymany ZIP na `IMPORTUJ_DANE_Z_ZIP.bat`. Alternatywnie włóż jeden ZIP do katalogu `IMPORTUJ_TUTAJ` i kliknij plik importu.
3. Po zakończeniu kliknij `URUCHOM_STRONE.bat`.

Paczka zawiera obie bazy aplikacji, pełne opisy profili, kwalifikacje firm i podgrupy, zapisane weryfikacje ręczne/AI, dane mapy, gotowe raporty widoczne w zakładkach badań oraz historię i pliki pomocnicze analiz. Import sprawdza integralność i sumy kontrolne paczki. Jeśli na komputerze były już dane, zapisuje ich kopię w `.local/backups` przed podmianą. Gotowe raporty są od razu kopiowane również do zbudowanej strony, więc nie trzeba ponownie wykonywać wielogodzinnych obliczeń. Obsługiwane są także ZIP-y z surowym katalogiem `profiles`, które zostaną automatycznie przetworzone. Nie wysyłaj danych osobom bez uprawnień do ich używania.

Zmiana etykiety firmy jest od razu zapisywana w lokalnej bazie. Katalog, liczniki, eksport CSV i mapa korzystają z niej przy następnym odświeżeniu danych. Eksport ZIP przenosi te decyzje na drugi komputer. Gotowe raporty badawcze w ZIP-ie pozostają niezmienionym wynikiem poprzedniego uruchomienia; po ponownym uruchomieniu badania jego dobór próby uwzględni zapisane decyzje ręczne i Gemini.

## Ręczne uruchomienie na Windows

Wymagania: Python 3.12 i Node.js 22 LTS (lub nowszy wspierany przez zależności). Polecenia wykonuj w PowerShell, zaczynając w katalogu projektu.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.lock
cd frontend
npm ci
npm run build
cd ..
```

### Import własnych danych

Repozytorium zawiera kod, bez bazy firm i raportów z prywatnych danych. Po sklonowaniu zaimportuj własne odpowiedzi dostawcy, do których masz prawo dostępu i wykorzystania. Nie ma wbudowanej bazy demonstracyjnej.

```text
firmy_b/raw/
  profiles/          # pliki numerKRS.json z profilami
  financials/        # opcjonalne finanse, te same nazwy plików
  connections/      # opcjonalne powiązania
  structure-people/ # opcjonalne osoby i role
```

```powershell
.venv\Scripts\python.exe -m scripts.import_profiles --source firmy_b\raw\profiles
.venv\Scripts\python.exe scripts\build_sqlite.py status
.venv\Scripts\python.exe -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
```

Otwórz <http://127.0.0.1:8000/>. Zostaw terminal serwera uruchomiony; Ctrl+C kończy jego pracę. Import tworzy `data/` i `.local/company_lab.sqlite3`. Mając już lokalny eksport w `data/profiles`, możesz odtworzyć bazę przez `scripts\build_sqlite.py build`.

Polecenie `scripts\build_sqlite.py build` tworzy równocześnie lekki indeks `.local/financial_map.sqlite3`, z którego korzysta zakładka **Mapa**. Jeśli główna baza już istnieje, sam indeks mapy możesz odtworzyć poleceniem:

```powershell
.venv\Scripts\python.exe scripts\build_financial_map.py
```

Mapa korzysta wyłącznie z rzeczywistych rekordów w zaimportowanych profilach. Brak danych pozostaje brakiem danych, a zero jest uwzględniane jako liczba. Dla wskaźników procentowych opcja „Wskaźnik zagregowany” liczy iloraz sum składowych.

### Rozwijanie interfejsu

Przy działającym backendzie uruchom w drugim terminalu:

```powershell
cd frontend
npm run dev
```

Vite poda adres i przekieruje `/api` do backendu. `npm run build` aktualizuje wersję na porcie 8000. Po pierwszym buildzie uruchom backend ponownie.

### Redis (cache i kolejka zadań)

Aplikacja wykorzystuje Redis do:
1. **Cache'owania odpowiedzi API** (`/api/profiles`, `/api/profiles/locations`, `/api/profiles/{krs}`) — powtarzające się zapytania zwracane są błyskawicznie z pamięci.
2. **Kolejki zadań w tle (RQ)** — ciężkie operacje (eksport CSV, przebudowa SQLite, badania badawcze) wykonywane są asynchronicznie bez blokowania interfejsu.

> [!NOTE]
> **Graceful degradation:** Aplikacja działa poprawnie również **bez** Redisa — w przypadku braku połączenia zapytania trafiają bezpośrednio do SQLite, a eksporty są realizowane synchronicznie.

#### Instalacja Redisa na Windows

- **Opcja A (Memurai — zalecana na Windows):** Pobierz i zainstaluj darmowy [Memurai Developer](https://www.memurai.com/) (natywny serwis Windows, 100% kompatybilny z Redis).
- **Opcja B (Docker):** `docker run -d --name redis -p 6379:6379 redis:alpine`
- **Opcja C (WSL2):** `sudo apt install redis-server && sudo service redis-server start`

#### Konfiguracja

Domyślny adres to `redis://127.0.0.1:6379/0`. Jeśli używasz innego adresu, ustaw zmienną środowiskową:
```powershell
$env:REDIS_URL = "redis://127.0.0.1:6379/0"
```

#### Uruchomienie workera kolejki zadań

W osobnym oknie terminala uruchom proces roboczy:
```powershell
.venv\Scripts\python.exe -m backend.worker
```
Worker nasłuchuje na kolejce `company-lab` i przetwarza zadania eksportu oraz przebudowy bazy.



## Badania

```powershell
.venv\Scripts\python.exe -m research.leverage_study
.venv\Scripts\python.exe -m research.developer_questions_study
```

Program wypisze folder wyniku `data/research/leverage/<identyfikator>`. Użyj tego konkretnego folderu do lokalnej publikacji:

```powershell
.venv\Scripts\python.exe -m scripts.publish_leverage_study data\research\leverage\<identyfikator>
cd frontend
npm run build
```

Zastąp `<identyfikator>` nazwą folderu z ukończonego badania. Publikator sprawdza zgodność kolekcji. `frontend/public/research/` jest pomijany przez Git. Aktualny protokół w `research/leverage_study.py` określa dobór próby, poziom istotności 0,1 i dodatkowe poziomy analizy wrażliwości.

Drugi moduł zapisuje analizy zapasów, gotówki, należności i stabilności w `data/research/developer_questions/<identyfikator>`. Opublikuj ten wynik poleceniem `.venv\Scripts\python.exe -m scripts.publish_developer_questions data\research\developer_questions\<identyfikator>`, a następnie przebuduj frontend. Oba badania i publikatory wybierają lokalną bazę SQLite, gdy jest dostępna — tę samą kolekcję, którą pokazuje katalog aplikacji. Oba raporty stosują α = 0,1 i 90% przedziały ufności.

## Android i Tailscale

Zainstaluj Android Studio, JDK 21 i SDK zgodny z `frontend/android/variables.gradle`. Polecenia Capacitor wykonuj wyłącznie z `frontend/`.

1. Skopiuj `frontend/.env.example` do `frontend/.env.production.local`.
2. Wpisz `VITE_API_BASE_URL=http://ADRES_TAILSCALE_KOMPUTERA:8000`, zastępując adres rzeczywistym adresem komputera.
3. Uruchom backend z tym adresem jako `--host`. Komputer i telefon muszą być połączone z Tailscale; zapora musi dopuszczać połączenie.
4. Zbuduj i zsynchronizuj interfejs:

```powershell
cd frontend
npm run build
npx cap sync android
npx cap open android
```

W Android Studio zbuduj APK, albo w `frontend/android` uruchom ` .\gradlew.bat assembleDebug`. Plik pojawi się w `frontend/android/app/build/outputs/apk/debug/app-debug.apk`.

Obecna konfiguracja dopuszcza HTTP do prywatnego backendu testowego. Publiczne wdrożenie wymaga osobnego przygotowania HTTPS i kontroli dostępu. `VITE_*` jest widoczne w aplikacji: nie wpisuj tam sekretów. Zmiana adresu API wymaga nowego builda i synchronizacji Capacitor.

## GitHub i kopie zapasowe

Instrukcja: [GitHub Desktop krok po kroku](docs/GITHUB_DESKTOP.md).

Do repozytorium trafia kod, testy, konfiguracja Androida i wersje zależności. `.gitignore` pomija dane, SQLite, pliki `.env`, klucze podpisu, raporty lokalne, zależności oraz gotowe APK. Bazę i dane archiwizuj osobno. GitHub przechowuje kod; publikacja repozytorium nie uruchamia backendu.

## Sprawdzenie zmian

```powershell
cd frontend
npm run build
cd ..
.venv\Scripts\python.exe -m pytest tests/test_local_profiles.py -q
```

Część pozostałych testów wymaga lokalnych danych lub PostgreSQL. Nie wszystkie działają samodzielnie na świeżym klonie.

Nie nadano projektowi licencji open source. Przed publikacją publiczną ustal licencję kodu oraz prawa do ewentualnie udostępnianych materiałów dostawcy.
