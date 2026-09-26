# Plan badań

Status: protokół z etapu 1, rozszerzony przed pierwszą estymacją 12.09.2026.
Żaden wynik ani znak współczynnika nie jest założony. Brak score i rekomendacji inwestycyjnych.

## Pierwsze wykonanie eksploracyjne

Wersjonowany protokół `research/specs/initial_studies.json` realizuje R01–R04 na panelu
reported v1. Uruchomienie wymaga jawnego `--allow-provisional`. Nie zmienia ono research_ready
datasetu: to obliczeniowy test zależności na danych dostawcy, nie zatwierdzony model do decyzji
ani dowód predykcji poza próbą. Wszystkie raporty eksponują ten status i ograniczenia mapowania.

Pochodzenie próby: X w roku t (2018–2024), Y z dokładnego t+1. Complete cases, następnie
usunięcie singletonów z grafu firma/rok. Pooled z efektami roku i FE firmy/roku korzystają
z tej samej próby; SE klastrowane po firmie. Specyfikacje nie dodają lagowanego Y w R02/R03.
R01 dodatkowo bez liquidity: wspólna próba oraz poszerzona próba, osobno raportowane.
Nie mylimy różnicy próby z różnicą specyfikacji.

Wariant główny bez przycinania. Zaplanowana wrażliwość: winsoryzacja 1/99 percentyl X i Y
w próbie estymacyjnej, przed utworzeniem kwadratu. To analiza in-sample, nie preprocessing
modelu predykcyjnego. Progi i liczba zmienionych wartości są zapisywane. Cztery pierwotne testy
FE bez przycinania: leverage w R01, leverage² w R02, liquidity² w R03, receivables w R04;
BH FDR w rodzinie czterech testów. Pozostałe p oznaczone jako nieskorygowane analizy wrażliwości.
Nie wyznaczamy optymalnego długu/płynności z samej istotności kwadratu.

## Populacja i dopuszczenie danych

Badana jest dostępna kohorta Compabase, nie reprezentatywna próba wszystkich polskich firm.
Nie znamy pełnej reguły jej doboru. `revenue_window` sugeruje selekcję pasmami przychodów;
wymaga to ustalenia filtrów eksportu i uwzględnienia survivorship/selection bias.
Nie wnioskujemy o upadłości z braku kolejnego sprawozdania.

Bazowy panel jest niezbilansowany i jednostkowy. Główny okres roboczy: 2018–2025,
po selekcji dokumentów; 2011–2017 ma małą liczebność, 2026 jest częściowy.
Wszystkie lata pozostają w źródłach i panelu dostępności. Dokładny przedział modelu
wyznaczają wyniki kontroli okresów, jakości i dostępności zmiennych, zapisane w specyfikacji.
`panel_full`, `3plus`, `5plus`, `long` nie zastępują raportu rzeczywistej próby estymacyjnej.
Warunkowanie na długiej przyszłej historii może powodować selekcję; porównujemy kohorty,
a nie uznajemy panel_long z góry za bardziej wiarygodny.

Braki rozdzielamy na: pole niedostępne w wariancie sprawozdania, błąd ekstrakcji,
nieprawidłowy mianownik, brak roku, konflikt dokumentu, brak dostępności w dacie badania.
Nie imputujemy Y ani nie interpolujemy przyszłych sprawozdań. Raportujemy pokrycie wg roku
i profilu formularza; małe/mikro formularze mogą systematycznie ograniczać płynność i należności.
Complete-case dla konkretnej regresji z tabelą ubytku próby i analizą selekcji.
Imputacja X w ML jest wariantem późniejszym: trenowana tylko na zbiorze treningowym.

## Pierwszy pakiet

1. **R00: jakość i opis** — rozkłady, mediany, percentyle, braki, znaki kapitału/zysku,
   profile formularzy, długość historii, luki, przejścia pomiędzy latami. Bez score.
2. **R01 / A: leverage a przyszły wzrost przychodów** — główny endpoint `revenue_growth_(t+1)`;
   FE firmy i roku, X w t: szerokie zobowiązania/aktywa, current_ratio, ROA_end, log_assets.
   Główny model z płynnością i kontrolny bez płynności porównujemy również na wspólnej próbie,
   żeby rozdzielić zmianę specyfikacji od zmiany składu próby.
3. **R02 / B: nieliniowość leverage a ROA_(t+1)** — liniowy i kwadratowy wariant na tej samej
   próbie, marginal effects z CI i rozkładem obserwacji. Wynik eksploracyjny.
4. **R03 / C: nieliniowość płynności a marża_(t+1)** — analogicznie, osobno leverage jako kontrola.
5. **R04 / G: należności a przyszłe pogorszenie** — ciągła zmiana marży i zmiana zysku
   skalowana aktywami przed tworzeniem klasyfikatora ryzyka.

Wybór końcowych kontroli ustalamy przed estymacją i opisujemy diagramem zależności:
zmienna będąca mediatorem nie jest automatycznie kontrolą. ROA jako kontrola własnej
przyszłej wartości zmienia model w dynamiczny; taki wariant oznaczamy osobno i nie uznajemy
zwykłego FE za pozbawiony obciążenia krótkiego panelu. Modele B/C bazowo bez lagowanego Y.

## Rejestr pytań A–N

| Badanie | Ekspozycja i outcome | Horyzont / metoda / warunek |
|---|---|---|
| A | leverage → revenue_growth | +1; FE i pooled OLS jako punkt odniesienia |
| B | leverage i kwadrat → ROA, margin | +1; FE, nieliniowość, CI punktu zwrotnego |
| C | liquidity i kwadrat → ROA/margin | +1; FE; silna kontrola braków |
| D | delta_leverage → wzrost/ROA | +1,+2,+3; osobne horyzonty, event profiles; nie automatycznie przyczynowe |
| E | leverage → wzrost i downside | +1,+2; osobne modele średniej i pogorszenia, nie jeden score |
| F | equity_to_assets → wzrost | +1; osobno od leverage, ponieważ mogą być algebraicznie współliniowe |
| G | receivables/assets i delta → marża, strata | +1,+2; uwzględnić ograniczenia formularzy |
| H | asset_growth → revenue_growth | +1,+2,+3; FE, kontrola dotychczasowej wielkości |
| I | cechy w t → szybki wzrost | +1,+2; threshold wersjonowany; walidacja czasowa |
| J | cechy w t → pogorszenie | +1,+2; oddzielne endpointy, baseline logistyczny |
| K | cechy przed szokiem → głębokość spadku i czas odbudowy | wymaga zewnętrznego datowania szoku/koniunktury i spójnej ekspozycji |
| L | interakcje strategii z wielkością | +1; log_assets ciągłe lub ustalone kwantyle; nie ustawowe MŚP bez zatrudnienia |
| M | strategie × branża | wymaga PKD i wersji historycznej, dziś niedostępne |
| N | strategie × region | wymaga lokalizacji; dziś niedostępne |

## Estymacja i interpretacja

Model bazowy: `growth_it = β1 liquidity_i,t−1 + β2 leverage_i,t−1 + β3 roa_i,t−1
+ β4 log_assets_i,t−1 + α_i + γ_t + ε_it`. Znaki β są estymowane swobodnie.
Stałe firmy i roku, SE klastrowane po firmie jako wariant podstawowy;
[linearmodels udostępnia tę specyfikację kowariancji](https://bashtage.github.io/linearmodels/panel/panel/linearmodels.panel.model.PanelOLS.fit.html).
Przy wspólnych szokach badamy wrażliwość błędów standardowych, ale mała liczba lat
ogranicza wiarygodność klastrowania po czasie. Grupy kapitałowe mogą wymagać klastrów grupowych,
jeżeli dostępne będzie wiarygodne przypisanie grup w badanym okresie.

Raport: liczba firm i obserwacji po każdej filtracji, zakres lat, liczba klastrów,
singletony i zmienne pochłonięte przez FE, coefficients, SE, 95% CI, p, R2 i within R2
z dokładną definicją estymatora, warianty próby, wykresy zależności i ograniczenia.
Sprawdzamy współliniowość, zmienność within, wpływ obserwacji skrajnych i seryjną korelację.
Nie raportujemy nieidentyfikowalnych współczynników ani nie zamieniamy błędu modelu w zero.

Kwadrat nie dowodzi istnienia optimum. `−β1/(2β2)` pokazujemy tylko przy odpowiedniej
krzywiźnie, wewnątrz empirycznego zakresu z wystarczającym wsparciem, z CI obliczonym np.
bootstrapem firm i porównaniem stabilności. Gdy mianownik bliski zeru lub CI nieograniczony,
wynik brzmi „brak wiarygodnego punktu zwrotnego”. Nie ekstrapolujemy optimum poza dane.

Winsoryzacja to analiza wrażliwości (np. 1/99 percentyl wobec danych bez winsoryzacji),
nie ukryte czyszczenie. Progi wyznaczane w train dla predykcji; wartości oryginalne zachowane.
Pierwotny endpoint A zapisany przed obliczeniem. Dodatkowe Y/horyzonty/segmenty oznaczone
eksploracyjnie; rodziny testów i korekta Benjamini–Hochberg FDR raportowane obok surowych p.
Pokazujemy wyniki zerowe i niezgodne z hipotezą, bez wybierania „najlepszego” modelu po znaku.

RE wymaga uzasadnienia braku korelacji efektu firmy z X; porównanie correlated RE/Mundlak
może pomóc, ale nie tworzy przyczynowości. System GMM dopiero po analizie dynamicznego panelu,
założeń instrumentów, AR(1)/AR(2), Hansen/difference-in-Hansen, ograniczeniu i raportowaniu
liczby instrumentów. [Roodman opisuje problem nadmiernej liczby instrumentów](https://onlinelibrary.wiley.com/doi/abs/10.1111/j.1468-0084.2008.00542.x).
Nie zakładamy, że `linearmodels` automatycznie realizuje potrzebny System GMM.

Każdy wynik ma klasę: **opis/korelacja**, **zależność predykcyjna zweryfikowana poza próbą**,
**oszacowanie warunkowe modelu** lub **efekt przyczynowy przy jawnej identyfikacji**.
FE + lag należą do oszacowań warunkowych, nie dowodów przyczynowych.

## Quality of Growth — metodologia przed score

V1 to wektor zmian: przychody, zysk (wzrost przy dodatniej bazie i skalowana zmiana),
aktywa, szerokie zobowiązania, dług odsetkowy jeśli rozpoznany, gotówka, należności, marża.
Wyświetlamy komponenty, jednostki, podstawy porównania i braki. Rozróżniamy wzrost nominalny
od realnego; realny wymaga zewnętrznych deflatorów, których eksport nie zawiera.

Porównanie A/B z pytania: podobny wzrost sprzedaży może współwystępować z różną zmianą
marży, finansowania i gotówki. Nie oznacza to automatycznie, że dług B jest błędną decyzją
(mógł finansować inwestycję z późniejszym efektem). Badamy następne 1–3 lata.
Do czasu danych cash flow stan gotówki nie jest operacyjnym przepływem pieniężnym.

Po uzupełnieniu segmentów: percentyle komponentów w roku i branży/rozmiarze, z jawnie
zdefiniowaną grupą odniesienia. Analiza Pareto jako opis kompromisów, bez automatycznego
uznania minimalnego długu/maksymalnej gotówki za cel. Score dopiero gdy istnieje jawny
cel (np. przyszła rentowność i downside), z walidacją poza próbą, analizą wag, stabilności
i niepewności. Wagi preferencji użytkownika nie mogą udawać parametrów odkrytych w danych.

## Event studies

Definicja wersjonowana: `delta_leverage_t >= X`, X w punktach procentowych przeliczonych
na ułamek, minimalna baza, porównywalne lata, okno −2…+3. Analogicznie aktywa/należności/
płynność/przychody. Próg wybieramy z uzasadnieniem przed oceną wyników, pokazujemy wrażliwość.
Data zdarzenia księgowego nie oznacza dokładnej daty decyzji finansowej.

Najpierw opisowe trajektorie, rok −1 jako odniesienie, CI bootstrapem po firmie,
liczebność dla każdego h, widoczna utrata obserwacji i wariant wspólnego okna.
Przy powtarzających się wydarzeniach zapis wszystkich; wariant główny pierwsze kwalifikowane
zdarzenie, brak nakładających się okien wg jawnej reguły. Nie traktujemy lat jednej firmy
jako niezależnych zdarzeń. Porównania z firmami bez zdarzenia dobranymi wyłącznie po historii
sprzed zdarzenia, bez selekcji po przyszłym wyniku i bez obiecywania usunięcia confoundingu.

Przyczynowe DiD/event study wymaga zewnętrznego uzasadnienia zdarzenia, parallel trends,
braku antycypacji, właściwej grupy kontrolnej i analizy pretrendów; brak istotnego pretrendu
nie dowodzi założenia. Dla rozłożonego w czasie treatment metoda dopasowana do mechanizmu,
np. [Callaway–Sant’Anna](https://arxiv.org/abs/1803.09015) dla właściwego projektu.
Zadłużenie zmienne i odwracalne nie staje się automatycznie absorbującym treatment.

## Peer group i klastry

Peery w dacie t: najpierw dostępność informacji i porównywalność finansów; następnie
branża (gdy dostępna), wielkość, region/wiek (gdy dostępne), leverage, liquidity, ROA,
struktura aktywów i historia do t. Start metodologiczny: robust scaling cech liczbowych,
odległość ważona z jawnymi wagami i karą/ograniczeniem wspólnego pokrycia; cechy kategoryczne
mogą wymagać odległości Gowera. Wybór po diagnostyce, nie zwykłe sortowanie przychodów.
Minimum wspólnego pokrycia i caliper ograniczają wymuszanie podobieństwa; wynik może być pusty.
Wykluczamy własną firmę, a gdy wiarygodne grupy dostępne także podmioty tej samej grupy.
Pokazujemy N, dystanse, rozkład późniejszych wyników i zakres cech, których nie porównano.

Obecnie pełne peery branżowo-regionalne są zablokowane brakiem danych. Finansowe peery
mogą później działać jako osobna, jasno opisana metoda. „Podobni, którzy urośli” to analiza
retrospektywna po wybraniu peerów w t; przyszły wynik nie służy do ustalania podobieństwa.

Clustering dopiero po ocenie braków, skali i redundancji cech. PCA opisuje strukturę;
porównanie KMeans/GMM/HDBSCAN przez stabilność resamplingową, silhouette, BIC dla GMM,
udział szumu i interpretowalność. Nie ustalamy K z nazw pożądanych grup. UMAP wyłącznie
wizualizuje; odległości i klastry nie są uzasadniane samym rysunkiem 2D.

## Early Warning i walidacja czasowa

Endpointy osobne: przejście do straty (profit_t≥0, profit_t+h<0), spadek marży o ustalone
pp, spadek płynności poniżej jawnego progu. Progi wymagają analizy użyteczności, są
wersjonowane przed treningiem; nie nazywamy ich prawdopodobieństwem upadłości.
Brak przyszłego dokumentu → nieznany outcome/cenzorowanie, nigdy „firma zdrowa”.
Survival wymaga wiarygodnej daty zdarzenia, wejścia do ryzyka i cenzorowania; danych tych dziś brak.

Baseline częstości + regresja logistyczna; później modele drzewiaste z porównaniem jakości.
Walidacja expanding window po roku, końcowe lata testowe nietykane przy strojeniu;
horyzont h wymusza odcięcie etykiet treningu kończących się po dacie origin.
Osobna ocena generalizacji do nowych firm (holdout podmiotów/grup). Random split wierszy
firma–rok jest niedopuszczalny jako jedyna walidacja.
Scaler, imputacja, selekcja cech, peers i kalibracja dopasowane wyłącznie na train:
[dokumentacja scikit-learn o leakage](https://scikit-learn.org/1.8/common_pitfalls.html).

Prawdziwy backtest „co wiedzieliśmy wtedy” wymaga publikacji/dostępności każdej wersji.
Dzisiejszy snapshot z ekstrakcjami w 2026 nie daje takiej gwarancji. Do pozyskania historii
publikacji wyniki mogą być wyłącznie retrospektywne, z jawnym ryzykiem rewizji/look-ahead.
Nie dodajemy fikcyjnych dat dostępności; założony lag publikacji tylko jako oznaczona analiza wrażliwości.

Metryki: PR-AUC, ROC-AUC, Brier, krzywe kalibracji, precision/recall przy progu związanym
z kosztem alarmu, bazowa częstość, CI bootstrapem firm i pokrycie według segmentów.
Wyjaśnienie cech modelu nie jest wyjaśnieniem przyczyn. UI pokazuje wersję modelu, datę,
horyzont, liczbę obserwacji walidacji, kalibrację, braki i warunki użycia. Poza domeną → abstencja.

## Nieruchomości, premium i Decision Lab

Najpierw klasyfikacja A–E na podstawie datowanych dowodów WWW/inwestycji, nie PKD 41.20.Z.
Powiązanie SPV–projekt–grupa z rolami i datami, bez podwójnego liczenia projektów.
Pozyskać datowane ceny, metraże, jakość, lokalizację, status lokalu, transakcje/sprzedaż,
koszty budowy, harmonogram finansowania i przepływy projektu. Dziś tych danych nie ma.

`market_premium = project_price_m2 / benchmark_price_m2 − 1` dla dodatniego benchmarku,
porównywalnego standardu ceny (oferta/transakcja, VAT, parking), okresu i lokalnego segmentu.
Benchmark wyłącza badany projekt, zawiera N i rozproszenie. Hierarchia promień/dzielnica/miasto
z minimalnym pokryciem; poszerzenie obszaru jawne, a brak wsparcia oznacza brak wyniku.
Hedonic log(price/m²) na cechach jakości/lokalizacji/czasu, walidacja czasowa i przestrzenna;
quality-adjusted premium = exp(residual)−1. Reszty także zawierają nieobserwowaną jakość.

Mechanizm: premium → tempo sprzedaży → kapitał zamrożony → koszt finansowania →
marża → ROIC/NPV → wynik firmy. Połączenie wyniku projektu z firmą musi uwzględniać inne
projekty i opóźnienia rozpoznania przychodów. Model całkowitego efektu premium nie kontroluje
automatycznie mediatorów; mechanizm badany osobno. Popyt i wybór jakości/ceny są endogeniczne.

LOW COST/MAINSTREAM/PREMIUM/LUXURY to hipotezy segmentów, bez sztywnych progów i rankingu
„lepszy”. Nieliniowość, interakcje miejsca/czasu/finansowania tylko przy wystarczającej próbie.
NPV wymaga przepływów i uzasadnionej stopy dyskontowej, ROIC jawnej definicji kapitału,
tempo sprzedaży obserwacji z cenzorowaniem. Nie wyprowadzamy ich z samych przychodów rocznych.

Scenariusze 0/10/20/30% premium są dozwolonymi założeniami użytkownika, nie prognozami.
Prognoza wymaga zwalidowanego modelu sprzedaży, kosztów i finansowania, przedziału predykcji
(odrębnego od CI parametrów), liczby peerów i zakresu zastosowania. Brak modelu/zmiennej
→ „brak wystarczających danych”, bez fikcyjnego expected margin, NPV czy estimated risk.

## Kontrakt raportu i ekranów

Każde badanie: pytanie, wersja danych, N firm/obserwacji, lata, metodologia i specyfikacja,
wyniki z przedziałami, wykresy, interpretacja, ograniczenia i klasa wniosku.
Model builder pozwala wybierać tylko wdrożone i zwalidowane modele oraz zgodne Y/X;
pozostałe mają opis wymagań. Raport zapisuje wszystkie wykluczenia i ostrzeżenia.
Nawigacja docelowa zgodna z wymaganiem: Dashboard, Firmy, Firma, Finanse, Porównanie,
Badania, Modele, Early Warning, Strategie, Nieruchomości, Decision Lab.
Ekran firmy rozdziela obserwacje, benchmarki i predykcje oraz pokazuje braki i pochodzenie KPI.
