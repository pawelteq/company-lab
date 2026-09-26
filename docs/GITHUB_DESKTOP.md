# Publikacja przez GitHub Desktop

Lokalne repozytorium jest przygotowane na gałęzi `main`. Pierwszy commit oraz publikację wykonasz w GitHub Desktop.

## Pierwsza publikacja

1. Zaloguj się w GitHub Desktop.
2. Wybierz **File → Add local repository…** (Ctrl+O).
3. Wskaż istniejący folder `aplikacja dla pawelka` na pulpicie, następnie **Add repository**. Nie wybieraj podfolderu `frontend` ani tworzenia nowego katalogu.
4. W zakładce **Changes** przejrzyj pliki. Baza `.local`, `firmy_b`, `data`, `.env.production`, `node_modules` i APK mają być nieobecne — są ignorowane.
5. W **Summary** wpisz `Pierwsza wersja Company Lab`, potem **Commit to main**. Jeśli program poprosi o autora commita, ustaw swoje konto / adres prywatności GitHub.
6. Kliknij **Publish repository**. Jako nazwę podaj np. `company-lab`.
7. Zostaw zaznaczone **Keep this code private** i kliknij **Publish repository**.
8. Wybierz **Repository → View on GitHub**, aby zobaczyć kod i README.

Nie dodawaj nowego szablonu README ani `.gitignore` — projekt zawiera gotowe pliki.

## Kolejne zmiany

Przejrzyj **Changes**, wpisz opis w **Summary**, wybierz **Commit to main**, potem **Push origin**. Commit zapisuje historię lokalnie; Push przesyła ją do GitHuba. Przed pracą na drugim komputerze użyj **Fetch origin**, a jeśli są nowe zmiany — **Pull origin**.

## Ważne dla tej aplikacji

Repozytorium nie zawiera bazy i danych firm. Kopię tych plików wykonuj osobno. GitHub Desktop nie jest hostingiem API — telefon nadal potrzebuje działającego backendu oraz Tailscale. Nowy komputer wymaga instalacji zależności i własnego importu według README.

Źródło: [oficjalna instrukcja GitHub Desktop](https://docs.github.com/en/desktop/adding-and-cloning-repositories/adding-an-existing-project-to-github-using-github-desktop).
