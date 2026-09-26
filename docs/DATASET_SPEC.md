# Panel v1 — protokół przed budową

Data: 12.09.2026. Pierwsza wersja ma status **exploratory_reported**, nie „dane zweryfikowane
do rekomendacji”. Pełna integralność importu została potwierdzona. Semantyka mapowań
dostawcy i skala kwot nie zostały jeszcze niezależnie potwierdzone dla wszystkich formularzy.

## Jednostka i selekcja

Jeden wiersz dla każdej dostępnej pary company_id–rok końca okresu, w danym dataset_id.
Zachowujemy również wiersze z nierozstrzygniętym wyborem dokumentu; mają puste wartości
analityczne i jawny powód. Firmy z jednym/dwoma latami nie znikają z panel_full.
Firmy bez finansów pozostają w katalogu firm, bez sztucznego roku w panelu.

Wybieramy tylko wtedy, gdy istnieje dokładnie jeden kandydat standalone w danym roku.
Nie łączymy okresów, nie wybieramy „najnowszej ekstrakcji” spośród konfliktów i nie podmieniamy
standalone dokumentem consolidated. Więcej kandydatów standalone = unresolved_multiple;
brak standalone = unavailable_standalone. Wszystkie kandydatury są zapisane z FK do staging.
Unikalny kandydat nie znaczy, że rok nadaje się do każdej analizy.

Panel_full obejmuje wszystkie pary dostępności, a 3plus/5plus/long zależą od liczby takich
lat (>=3/5/7). Osobne n_selected_years i n_annual_years opisują realne możliwości analizy.
Nie wykorzystujemy tych kohort jako cechy w predykcji: mogą zawierać przyszłą historię.

## Wartości, jakość i dziedziny

Kwoty źródłowe pozostają w staging/RAW. Bazowe `reported_*` w panelu odzwierciedlają je
bez mnożenia przez niepotwierdzoną skalę. Wskaźniki obliczamy z raportowanych kwot, w ułamkach,
nie kopiujemy procentowych ROA/ROE dostawcy. Wartości pozostają oznaczone jako zależne od
mapowania dostawcy. „PLN” w eksporcie nie dowodzi niezależnie skali każdej pozycji.

Powody braku: missing_input, missing_year, unresolved_selection, invalid_period,
nonpositive_denominator, nonpositive_log_input, incompatible_periods, balance_mismatch,
extraction_not_ok, unsupported_currency, incompatible_reported_scale.
Zero nie jest brakiem. Zmiana zysku i kapitału przy ujemnej bazie ma deltę, ale nie klasyczny growth.
Ujemny kapitał nie jest sam w sobie błędem. Wielkości ze struktury bilansu obarczone
balance_mismatch nie zasilają wskaźników zależnych od bilansu, choć ich reported_* są zachowane.

Nieannualny okres może dostarczyć stanów bilansowych i ich ilorazów. Strumienie (marża,
ROA, rotacja), logi i dynamiki do pierwszej próby wymagają poprawnych pełnych okresów
365/366 dni; wynik nie jest automatycznie annualizowany. Daty resolved nadal są pochodzenia dostawcy.

Wzrosty/delty/rolling wymagają ciągłych, porównywalnych okresów. Dla roku t szukamy dokładnie
t−1/t−2/t−3, a nie poprzedniego wiersza. Zmiana nominalnej kwoty między latami wymaga PLN
i zgodnej deklarowanej skali; brak skali po obu stronach pozostawia ostrzeżenie, nie dowód zgodności.
Wszystkie wyniki v1 są zatem eksploracyjne. `research_ready=false` dla całej wersji do czasu
osobnego zatwierdzenia mapowań, zasad kwalifikacji próby i dostępności danych w czasie.

## Pochodzenie i publikacja

Definicja każdej cechy zawiera operator, wejścia i przesunięcia lat. Wiersz wskazuje wybrany
rekord staging, a ten RAW i JSON Pointer. Łańcuch zależności prowadzi do wszystkich lat
uczestniczących w obliczeniu. Definicje cech są zapisywane z datasetem i hash kodu/config.
Przyszłe outcome mają role=target; nie należą do zestawu cech X.

Dokładne wartości Decimal zapisujemy jako JSONB numeric w PostgreSQL. Parquet do narzędzi
statystycznych zawiera float64, z jawną informacją o konwersji i bez inf/NaN jako wyników.
Metadata Parquet, rejestr cech i raport braków należą do tej samej wersji. Budowa publikowana
atomowo w DB po kontroli unikalności/liczebności, artefakty z hashami. Ponowne wykonanie
tej samej wersji weryfikuje istniejący artefakt. Źródeł nie modyfikujemy.

## Quality of Growth i pierwszy raport

Wektor: revenue_growth, profit_growth/profit_change_scaled, debt_growth, asset_growth,
cash_growth, receivables_growth, delta_margin. Bez sumowania w arbitralny score.
R00 pokaże liczebności, braki, kohorty i rozkłady cech; nie poda współczynników regresji,
ryzyka ani rekomendacji, dopóki kwalifikacja danych do modeli nie będzie uzasadniona.
