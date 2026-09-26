"""Render the audit evidence as Markdown; never reads or writes source data."""
import json
from pathlib import Path


def main():
    audit = Path('data/audit')
    s = json.loads((audit/'summary.json').read_text(encoding='utf-8'))
    q = json.loads((audit/'quality_details.json').read_text(encoding='utf-8'))
    manifest = json.loads((audit/'source_manifest.json').read_text(encoding='utf-8'))
    n = s['profiles']['raw_metrics']['rows']
    fields = s['profiles']['raw_metrics']['fields']
    out = Path('docs')
    out.mkdir(exist_ok=True)
    lines = ['# Data Audit — rzeczywisty eksport', '',
        'Data audytu: 11.09.2026. Zakres: cały katalog roboczy; przed pracą zawierał wyłącznie `firmy_b/`.',
        'Nie znaleziono istniejącego kodu aplikacji, konfiguracji, migracji, testów, AGENTS.md ani repozytorium Git.',
        'Skan objął wszystkie pliki dostarczonego eksportu, nie próbkę. Żaden plik źródłowy nie został zmieniony.', '',
        '## Najważniejsze ustalenie', '',
        f"Mamy **{s['counts']['firmy']:,} rozpoznanych firm**, **{n:,} rekordów finansowych** i **57 866 różnych par KRS–rok**.",
        'To panel dostępności przed selekcją sprawozdań, a nie gotowy, oczyszczony panel badawczy.',
        'Dane pozwalają rozpocząć budowę laboratorium finansowego. Nie wystarczają jeszcze do badań branżowych,',
        'regionalnych, historii właścicielskiej ani premium pricing. Istotne problemy okresów i mapowania',
        'wymagają rozstrzygnięcia przed modelami i UI.', '',
        '## Inwentaryzacja', '', '| Źródło | Pliki | Rozmiar bajty | Zawartość |', '|---|---:|---:|---|']
    for prefix,label,desc in [('firmy.csv','firmy.csv','11 518 wierszy, 14 pól; jeden wiersz bez identyfikacji'),('firmy_finanse.csv','firmy_finanse.csv','58 113 wierszy, 310 pól'),('progress.csv','progress.csv','11 517 wpisów status=ok'),('raw/financials/','raw/financials/*.json','11 517 odpowiedzi; metrics, documents, pagination i kursy'),('raw/connections/','raw/connections/*.json','11 517 odpowiedzi; people, related_companies i graph')]:
        fs = [f for f in manifest if f['path'].startswith(prefix)]
        lines.append(f"| `{label}` | {len(fs):,} | {sum(f['bytes'] for f in fs):,} | {desc} |")
    lines += ['',f"Łącznie **{s['files']:,} plików**, **{s['bytes']:,} bajtów** (~1,67 GB dziesiętnie).",
        'Wszystkie 23 034 JSON-y parsują się poprawnie. Dla każdego pliku zapisano SHA-256 i rozmiar.',
        'Wszystkie odpowiedzi mają `hasMore=false`, `docsOffset=0`, `docsLimit=25`; `documents=[]` wszędzie.',
        'To nie dowodzi kompletności zasobów dostawcy. Nie ma XML/PDF sprawozdań, mimo flag `has_esf_xml`.', '',
        '## Przykłady struktury', '',
        '`raw/financials/0000000746.json`: obiekt z tablicą `metrics` (8 rekordów), pustą tablicą',
        '`documents`, paginacją i mapami kursów. Rekord ma identyfikatory dokumentu/metryki/podmiotu,',
        'kwoty jako tekst, wskaźniki, daty `sf_*` i `*_resolved`, zakres konsolidacji, status ekstrakcji',
        'oraz `esf_statement_lines` z `bilans`, `rzis`, kolejnością kodów i profilem formularza.',
        'Każdy z 310 kluczy metryki jest obecny w każdym rekordzie; obecność klucza nie oznacza wartości.',
        'Cały katalog pól zagnieżdżonych i ich typów zapisano w `data/audit/nested_field_inventory.json`.', '',
        '`raw/connections/0000000746.json`: metadane podmiotu, `people` z rolami i udziałami,',
        '`related_companies` z ownership/subsidiary i udziałami, graf węzłów i krawędzi.',
        'To obserwacja relacji, bez przedziałów historycznej ważności. Nie należy liczyć grafu jako',
        'dodatkowych niezależnych relacji obok pozostałych reprezentacji.', '',
        'CSV finansowy zawiera zagnieżdżone struktury zapisane jako tekst reprezentacji obiektów Pythona',
        '(np. pojedyncze cudzysłowy), nie zawsze JSON. Natywny JSON jest bezpieczniejszą podstawą parsera.', '',
        '## Identyfikacja i kompletność danych firm', '',
        '| Pole | Stan |', '|---|---|',
        '| KRS | 11 517 niepustych, bez duplikatów; odpowiadają plikom obu rodzajów JSON |',
        '| Nazwa, forma prawna, profile_url | 11 517 niepustych; forma prawna wymaga ujednolicenia skrótów/opisów |',
        '| NIP, REGON | 100% puste w firmy.csv |',
        '| Województwo, miasto, adres | 100% puste w firmy.csv; brak tych pól także w JSON-ach |',
        '| PKD, data założenia, współrzędne | Nie znaleziono |',
        '| WWW w CSV | 1 124 wartości innych niż pustka i placeholder; 10 393 znaków „—”, 1 puste |',
        '| WWW w JSON connections | 1 122 niepuste wartości; wymagana walidacja i uzgodnienie źródeł |',
        '| revenue/profit w firmy.csv | Tekst prezentacyjny z M/PLN; nie używać do precyzyjnych obliczeń |',
        '| revenue_year | Wszędzie „2024/2025”; nie jest rokiem obserwacji panelowej |', '',
        'Wiersz logiczny CSV nr 10 520 nie ma KRS/nazwy, ma tylko etykietę lat i pasmo przychodów.',
        'Pozostaje w RAW, trafia do kwarantanny identyfikacji, nie liczy się jako firma.',
        'Dwie firmy z pustym `metrics`: KRS `0000371079` i `0000619863`; pozostają w katalogu firm.',
        'NIP występuje częściowo w `related_companies`: 3 101 różnych par KRS–NIP, w tym dowód',
        'dla 483 firm z kohorty. Nie jest to 3 101 dodatkowych badanych firm ani kompletne uzupełnienie NIP.', '',
        '## Lata i liczebność', '',
        'Rok = rok końca okresu `period_to_resolved`, z fallback do `sf_period_to`.',
        'W tym eksporcie daty końca są zgodne. Poniższe liczby obejmują wszystkie zakresy',
        'i okresy, także niepełne i problematyczne. Unikalna para nie jest zatwierdzonym rokiem finansowym.', '',
        '| Rok | Rekordy finansowe | Różne firmy / pary firma–rok |', '|---|---:|---:|']
    for year,ct in q['unique_company_year_by_year'].items():
        lines.append(f"| {year} | {s['stats']['years'][year]:,} | {ct:,} |")
    lines += ['', 'Najwięcej danych przypada na 2018–2025. 2026 obejmuje tylko 11 obserwacji;',
        'nie znaleziono okresów kończących się po dniu audytu ani po dacie ekstrakcji.',
        '508 firm ma luki kalendarzowe. Pary lat oddalonych o 1/2/3: 45 821 / 35 575 / 26 798',
        '(przed selekcją i kontrolą cech; nie są to jeszcze N regresji).', '',
        '| Klasa dostępności | Firmy | Unikalne firma–rok |', '|---|---:|---:|']
    for label in ['full','3plus','5plus','long']:
        panel = s['stats']['panel']
        lines.append(f"| panel_{label} | {panel['companies_'+label]:,} | {panel['observations_'+label]:,} |")
    lines += ['', 'Klasy oparte na liczbie różnych lat, bez wymogu ciągłości. Po wyborze standalone,',
        'rozstrzygnięciu okresów i konfliktów liczebności należy przeliczyć. 1 026 firm ma tylko jeden rok,',
        '1 437 ma dwa; nie są automatycznie odrzucane z aplikacji/panel_full.', '',
        '## Kompletność finansów', '',
        f'Mianownik = wszystkie {n:,} rekordów przed deduplikacją. Brak = null/pusty tekst/nieobecny klucz;',
        'zero i wartości ujemne zachowane. Kompletność nie jest dowodem poprawności mapowania.', '',
        '| Pole | Dostępne | Braki | Braki % | Zero | Ujemne |', '|---|---:|---:|---:|---:|---:|']
    for field in 'revenue_total profit_net total_assets equity liabilities_and_provisions fixed_assets current_assets short_term_liabilities long_term_liabilities cash_and_equivalents short_term_receivables inventories ebit ebitda roa roe net_margin ebitda_margin asset_turnover current_ratio cash_ratio liabilities_to_total_assets liabilities_borrowings interest_expense esf_statement_lines'.split():
        f = fields[field]
        available=f.get('nonempty',0)
        lines.append(f"| {field} | {available:,} | {n-available:,} | {(n-available)/n*100:.2f}% | {f.get('zero',0):,} | {f.get('negative',0):,} |")
    lines += ['', 'Pełne 310 pól: [DATA_DICTIONARY_AUDIT.md](DATA_DICTIONARY_AUDIT.md).',
        '69 z 310 pól jest całkowicie pustych, 13 ma wartość we wszystkich rekordach (w tym metadane).',
        'Braki kluczowych pól według roku: `data/audit/quality_details.json` → `missing_by_year`.', '',
        '## Problemy jakości i ich konsekwencje', '',
        '1. **Wielokrotne firma–rok**: 246 grup, 247 dodatkowych rekordów; nadal 233 grupy po',
        '   dodaniu zakresu konsolidacji do klucza. Brak powtórzonych metric_id. Przykład KRS',
        '   `0000011858`, 2019: dwa rozłączne okresy roku, nie zwykła kopia. Nie wybierać pierwszego',
        '   rekordu i nie sumować bilansów. Rejestr wszystkich kandydatów: `duplicate_company_years.json`.',
        '2. **Okresy**: `sf_period_from` puste w 100%, ale resolved start/end kompletne.',
        '   51 432 rekordy mają 365/366 dni; 6 681 inną długość, 46 ponad 550 dni, 556 koniec',
        '   poza 31 grudnia. KRS `0000736670`, `/metrics/7`: start 2019-01-01, koniec 2018-12-31.',
        '   Najdłuższy okres 3 653 dni. Resolved nie oznacza automatycznie wiarygodny.',
        '3. **Bilans**: 2 605 rozbieżności na 57 109 sprawdzalnych rekordów, przy tolerancji',
        '   `max(1 PLN, |assets| × 10^-6)`. To test orientacyjny float, nie prawny audyt ksiąg.',
        '   Przykład KRS `0000002877`, `/metrics/5`: 550 120,03 ≠ 158 749,37 + 570 566,20.',
        '   Weryfikować jednostki, profil formularza i mapowanie; produkcyjna kontrola Decimal.',
        '4. **Znaki i dzielniki**: aktywa ujemne 17, gotówka ujemna 84, zobowiązania ujemne 18,',
        '   przychody ujemne 76. Ujemny kapitał 10 531 i strata 20 344 nie są same w sobie błędem.',
        '   Nie liczyć logów niedodatnich kwot ani klasycznego wzrostu od zerowej/ujemnej bazy.',
        '5. **Skala wskaźników**: ROA/ROE/marża/leverage zazwyczaj procenty, liquidity ilorazy.',
        '   ROA pasuje do 100×profit/assets w 56 607 z 56 945 sprawdzonych; ROE w 44 834 z 49 122;',
        '   leverage w 56 278 z 56 860. Current ratio pasuje do current_assets/ST liabilities',
        '   w 40 996 z 41 079, cash ratio w 41 015 z 41 048. Pozostałe różnice wymagają wyjaśnienia.',
        '   Dopasowania przy zerze mogą spełniać obie skale. Nie dzielić wszystkich kolumn przez 100.',
        '6. **Profile i jednostki**: pełny, inna, mała, mikro, IFRS i OP mają różne mapowania.',
        '   Wszystkie currency=PLN, ale 16 profili jawnie ma scale=1000 i 268 scale=1;',
        '   pozostałe 57 829 nie mają jawnego scale w profilu. Nie mnożyć ponownie bez sprawdzenia',
        '   relacji wartości metryki do pozycji źródłowej. PLN nie dowodzi jednostki kwot.',
        '7. **Ekstrakcja**: 702 statusy failed, 3 brak statusu; 3 246 rekordów z ostrzeżeniami',
        '   dostawcy; 905 has_esf_xml=false. Progress „ok” oznacza pobranie, nie jakość sprawozdania.',
        '8. **Dane historycznie dostępne**: wszystkie extracted_at pochodzą z 2026.',
        '   Brak dat publikacji i historii wersji nie pozwala udawać prawdziwego point-in-time backtestu.',
        '9. **Selekcja kohorty**: nie ma kodu pobierania ani opisu pełnych filtrów. Etykiety',
        '   revenue_window i revenue_year wymagają wyjaśnienia. Nie zakładamy reprezentatywności.',
        '10. **Pola szczegółowe**: część całkowicie pusta; występuje np. literówka',
        '    `short_term_liilities_tax`. Zachować oryginał i jawne mapowanie, bez ukrytej korekty.', '',
        '## Powiązania', '',
        '24 737 wystąpień osób, 21 117 różnych provider person_id; 11 370 firm ma niepuste people.',
        '5 783 wystąpienia related_companies u 2 305 firm: ownership 2 802, subsidiary 2 981.',
        'Grafy łącznie: 36 188 wystąpień węzłów i 55 247 krawędzi. Te liczby nie oznaczają',
        'unikalnych globalnych osób/relacji. W relationships są 3 457 dokładne powtórzenia',
        'wewnątrz tej samej listy osoby. Dane trzeba deduplikować w warstwie relacyjnej z zachowaniem dowodów.',
        'Brak dat ważności relacji. Nie można obecnie pokazać rzetelnej historii właścicielskiej/zarządu.', '',
        '## Co zostało sprawdzone i co działa', '',
        '- Pełne parsowanie JSON i CSV; struktura, typy, braki, podstawowe kontrole finansowe i czasu.',
        '- Zgodność KRS metryk z nazwami plików: 58 113/58 113.',
        '- Każdy rekord CSV finansowego ma id w RAW. KRS, sf_period_to i 10 podstawowych kwot',
        '  porównano: zero rozbieżności przy tolerancji zaokrągleń kwot 0,0051 i relatywnej 10^-12.',
        '  To nie jest porównanie każdej z 310 wartości, ani niezależna weryfikacja poprawności źródła.',
        '- Działają narzędzia audytu; pliki maszynowe zawierają dowody, przykłady i manifest.',
        '- Powstały projekty architektury, schematu, ETL, cech i plan badań.',
        '- Nie uruchomiono bazy/API/UI ani modeli. Nie ma jeszcze opublikowanego analytical dataset.', '',
        '## Czego brakuje', '',
        'Słownika i dokumentacji mapowania dostawcy (szczególnie resolved dates, skala i warianty),',
        'oryginalnych sprawozdań dla weryfikacji konfliktów, reguł doboru kohorty, PKD, lokalizacji,',
        'wieku firm, dat publikacji/rewizji oraz historii relacji. Brak danych projektów, mieszkań,',
        'cen lokalnych, jakości, sprzedaży, kosztów i cash flow projektowego. Brak makro/deflatorów.', '',
        '## Dokładny następny krok', '',
        'Wdrożyć migracje raw/identity/statements i lokalny ingest do PostgreSQL zgodny z DATA_MODEL:',
        'najpierw rejestr manifestu i 23 034 JSON-ów oraz 3 CSV bez utraty bajtów/pól; następnie',
        'staging wszystkich 58 113 metryk wraz ze ścieżką źródłową i issue. Równolegle rozstrzygnąć',
        'mapowania okresów/jednostek i 246 grup firma–rok. Nie publikować tych konfliktów jako',
        'gotowych obserwacji rocznych. Po weryfikacji powstaje wersja standalone panelu, słownik cech,',
        'lineage i raport wykluczeń. Dopiero na niej R00–R04, potem API i frontend.', '',
        '## Odtwarzanie', '',
        'Z katalogu projektu, Python 3 (wyłącznie biblioteka standardowa):', '',
        '```powershell', 'python scripts/audit_data.py', 'python scripts/audit_quality.py',
        'python scripts/render_audit_report.py', 'python -m unittest discover -s tests -v', '```', '',
        'Audyt zapisuje wyłącznie `data/audit/` i raporty `docs/`. Zachować manifest pierwszego',
        'importu w rejestrze wersji przed kolejnym importem. Dzisiejsze raporty są stanem lokalnej',
        'inspekcji, nie mechanizmem produkcyjnej retencji. Szczegółowe próbki problemów są ograniczone',
        'do 20 na kategorię; liczniki obejmują całość, lista duplikatów wszystkie grupy.', '']
    (out/'DATA_AUDIT.md').write_text('\n'.join(lines),encoding='utf-8')
    detail = ['# Kompletność wszystkich pól finansowych', '',f'Mianownik: {n:,} rekordów RAW. Wszystkie liczby przed selekcją dokumentów.',
        'Brak = null/pusty tekst/nieobecność. Pusta lista/obiekt są liczone osobno w summary.json.',
        'To inwentaryzacja pól, nie zatwierdzony słownik semantyczny. Zera nie są brakami.', '',
        '| Pole | Niepuste | Braki | Braki % | Zero | Ujemne |', '|---|---:|---:|---:|---:|---:|']
    for k,f in fields.items():
        avail=f.get('nonempty',0)
        detail.append(f"| {k} | {avail} | {n-avail} | {(n-avail)/n*100:.2f} | {f.get('zero',0)} | {f.get('negative',0)} |")
    (out/'DATA_DICTIONARY_AUDIT.md').write_text('\n'.join(detail)+'\n',encoding='utf-8')
    print('Rendered DATA_AUDIT.md and DATA_DICTIONARY_AUDIT.md')


if __name__ == '__main__':
    main()
