# Protokół diagnostyki R01–R04 — 2026-09-12

Cel: wyjaśnić wrażliwość zapisanych modeli, bez korygowania źródeł i bez wyboru wyników
pod oczekiwaną tezę. Diagnostyka jest post hoc; nie stanowi kolejnego testu potwierdzającego.

1. Zweryfikować hashe runu i datasetu. Użyć dokładnie zapisanych próbek modelowych.
2. Dla każdej zmiennej X i Y pokazać min, p1, p25, medianę, p75, p99, max oraz liczbę
   obserwacji poza p1/p99. Progi służą opisowi, nie automatycznemu odrzucaniu danych.
3. Wybrać do przeglądu pięć firm na badanie. Kolejność wyznacza największa odległość
   dowolnej zmiennej od jej mediany podzielona przez IQR. Jest to priorytet przeglądu
   skrajności, nie ranking ryzyka firmy ani pełna miara wpływu na model. Remisy rozstrzyga
   company_id i rok; przy zerowym IQR użyć MAD, następnie odchylenia standardowego,
   a dla stałej zmiennej odległości 0. Jedna firma może wystąpić w kilku badaniach.
4. Dla wybranego wiersza i wszystkich zmiennych modelu pokazać wartości, źródła i mianowniki.
   W przypadku Y użyć dokładnego t+1; delta marży wymaga dwóch oddzielnych mianowników.
   Mały mianownik: dodatnia wartość w dolnym 1% odpowiedniego składnika w tej samej próbie
   (z uwzględnieniem przesunięcia roku). Porównanie jest orientacyjne przy niezweryfikowanej
   skali i heterogenicznych firmach. Mały mianownik nie oznacza błędu; skrajny iloraz też nie.
5. Odtworzyć główny FE bez przycinania. Porównać cały wektor współczynników z zapisanym runem.
   Dla każdej z pięciu firm osobno powtórzyć FE po pominięciu CAŁEJ jej historii modelowej.
   Pozostałe zmienne i procedura SE bez zmian; ewentualne nowe singletony usuwać jawnie.
   Raportować zmianę parametru głównego, 95% CI, N oraz zmianę podzieloną przez bazowy SE.
   Ta ostatnia liczba to opisowa skala porównawcza, nie klasyczny DFBETAS ani nowy p-value.
6. Nie twierdzić, że znaleziono globalnie najbardziej wpływowe firmy: badamy pięć kandydatur
   wybranych według skrajności. Nie zmieniać podstawowych wyników ani BH; nie traktować
   usuwania firm jako nowej zaakceptowanej specyfikacji. Każdy przypadek ma status do przeglądu.

Wyniki i manifest zapisane jako nowy niezmienny `research.diagnostic_run` powiązany z runem.
Weryfikacja jednostek wymaga dokumentacji dostawcy lub sprawozdań; sam JSON nie dowodzi skali.
Algorytm nie wpisuje korekt do RAW/staging/panelu i nie kwalifikuje datasetu jako research_ready.

Estymator: [PanelOLS — efekty firmy i roku](https://bashtage.github.io/linearmodels/panel/panel/linearmodels.panel.model.PanelOLS.html).
