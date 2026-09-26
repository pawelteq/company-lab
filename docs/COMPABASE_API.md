# Źródło danych: Compabase API

**W projekcie korzystamy z Compabase API. Użytkownik zbiera dane z tego API.**
Dokumentacja: [ContentWriterco/Compabase-API](https://github.com/ContentWriterco/Compabase-API).
Kontrakt: [v1.yaml](https://github.com/ContentWriterco/Compabase-API/blob/main/v1.yaml).
Baza adresów: `https://compabase.com/api/v1`. Zweryfikowano 2026-09-13.

## Uzgodniony zakres zbierania

| Kod | Wersja klasyfikacji dla zakresu | Zastosowanie |
|---|---|---|
| 41.10.Z | PKD 2007 | Realizacja projektów budowlanych związanych ze wznoszeniem budynków |
| 41.20.Z | PKD 2007 | Roboty związane z budową budynków mieszkalnych i niemieszkalnych |
| 68.11.Z | PKD 2025 | Kupno i sprzedaż nieruchomości na własny rachunek |
| 68.12.A | PKD 2025 | Realizacja projektów budowlanych związanych ze wznoszeniem budynków mieszkalnych |

Zakres dotyczy działalności głównej: osobne zapytanie po każdym kodzie, `primary_only=true`.
Wersja klasyfikacji jest weryfikowana w odpowiedzi `company.activities[].pkd_source`;
nie dodajemy nieudokumentowanego parametru wersji do API.
Kod i wersja to wspólny identyfikator klasyfikacji. Ten sam tekst kodu może mieć znaczenie
w różnych wersjach; unknown pozostaje unknown. Nie wnioskujemy wersji tylko z daty ekstrakcji.

Według [klucza GUS](https://klasyfikacje.stat.gov.pl/static/pkd_25/pdf/KlasyfikacjaPKD2025.pdf)
41.10.Z nie przechodzi wyłącznie w 68.12.A — obejmuje też inne nowe podklasy.
68.11.Z odpowiada obszarowi dawnego 68.10.Z, więc cztery wskazane kody nie są pełnym
automatycznym przekładem jednej dawnej populacji. Zachowujemy dokładnie zakres użytkownika.
[GUS opisuje równoległe stosowanie klasyfikacji](https://bip.stat.gov.pl/dzialalnosc-statystyki-publicznej/rejestr-regon/pkd-2025/).

Firma może pojawić się w kilku eksportach/snapshotach. Łączymy identyfikację po KRS,
zachowując historię zapytań i członkostwo we wszystkich kohortach. Nie sumujemy liczebności
czterech eksportów. PKD nie jest dowodem faktycznej działalności deweloperskiej ani klasy A–E.

## Jakie odpowiedzi zachowujemy

| Endpoint | Warstwa RAW | Zastosowanie |
|---|---|---|
| `/companies/export` | Cała odpowiedź, filtr, paginacja | Lista kandydatów i pochodzenie doboru próby |
| `/companies/krs/{krs}` | Pełny profil | NIP/REGON, adres, lokalizacja, PKD, powiązania, sekcje źródłowe |
| `/companies/krs/{krs}/financial-statements` | Pełne finanse | Szczegółowe rekordy i okresy |
| `/companies/krs/{krs}/financial-documents` | Metadane dokumentów | Identyfikatory i źródła sprawozdań |
| `/companies/krs/{krs}/connections` | Pełny graf | Powiązania, bez domniemanej ważności historycznej |
| `/companies/krs/{krs}/structure-people` | Pełna struktura | Role i udziały; dane osób nie są eksportowane do publicznego UI |

Odpowiedź profilu może zawierać finanse równocześnie w `financials.byYear` i
`financialsDetail.metrics`. Adapter udostępnia oba z oryginalnymi JSON Pointer, ale preferuje
szczegółowy kontener. To nie są dwa niezależne sprawozdania. Powtórzenia między osobnymi
odpowiedziami porównujemy po ID dokumentu/rekordu i wartościach, bez nadpisywania źródła.

W plikach poglądowych firma Partnerbud ma 6 rekordów z lat 2020–2024, w tym dwa różne
okresy roku 2020. To nadal panel wymagający selekcji okresów, a nie 6 rocznych obserwacji.
Wynik audytu: [REFERENCE_DATA_AUDIT.md](REFERENCE_DATA_AUDIT.md).

## Bezpieczeństwo integracji i dobór próby

Autoryzacja Compabase jest wykonywana nagłówkiem `X-API-Key` lub Bearer. Klucz należy
przechowywać wyłącznie backendowo w `COMPABASE_API_KEY`, nigdy w `VITE_*`, JSON-ach źródłowych,
raportach, URL lub repozytorium. Nie dostarczono klucza i program nie uruchamia teraz
samodzielnego pobierania przez płatne endpointy; obsługuje analizę lokalnych eksportów.

Nie używamy automatycznie filtrów aktywności ani minimalnych przychodów. Usunięcie firm
nieaktywnych/bez finansów zmienia populację i może wprowadzić bias przeżywalności.
Każdą stronę eksportu zachowujemy wraz z filtrem, datą obserwacji, kursorem/offsetem i
`hasMore`. Według dokumentacji wynik może zmieniać się w trakcie stronicowania; nie
deklarujemy snapshotu populacji bez niezależnego sprawdzenia pokrycia i duplikatów.

Provider `companySummary`, `faq`, `insightsByYear`, `similarCompanies` i rankingi pozostają
osobnymi danymi dostawcy. Nie stają się dowodem faktu, naszym wynikiem modelu, etykietą
ryzyka ani rekomendacją. Trzeba zachować ich pochodzenie i status generowanej treści.

## Wdrożone elementy

- `etl/compabase_payloads.py`: adapter profilu, PKD, różnych kontenerów finansów, pochodzenie
  danych, rozróżnienie liczb tekstowych od NULL, plan czterech zapytań.
- `scripts/audit_references.py`: niezmienne kopie plików, SHA-256, audyt kontenerów i porównań.
- Pliki `referencja/` to referencje, nie nowy wsad populacyjny. Nie zmieniają obecnych modeli.
- W aplikacji widoczna informacja o Compabase API, zakresie PKD i audycie referencji.
