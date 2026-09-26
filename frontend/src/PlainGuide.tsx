const terms = [
  ['Przychody', 'Kwota, którą firma uzyskała z działalności. To jeszcze nie zysk — trzeba odjąć koszty.'],
  ['Zysk netto', 'Wynik po uwzględnieniu kosztów i podatku. Ujemny wynik oznacza stratę.'],
  ['Aktywa', 'Majątek firmy: m.in. nieruchomości, zapasy, należności i pieniądze.'],
  ['Kapitał własny', 'Część majątku finansowana przez właścicieli i zatrzymane wyniki firmy.'],
  ['ROA i ROE', 'ROA porównuje zysk z majątkiem, a ROE — z kapitałem własnym. Sprawdź okres i sposób obliczenia przed porównaniem firm.'],
  ['EBIT i EBITDA', 'EBIT to wynik operacyjny. EBITDA to EBIT powiększony o amortyzację; nie oznacza gotówki na koncie.'],
  ['Punkty procentowe (pp.)', 'Wzrost z 5% do 7% to 2 punkty procentowe.'],
  ['Wynik nierozstrzygający', 'Dane nie pozwalają określić kierunku zależności dostatecznie precyzyjnie. To nie dowód, że zależności nie ma.'],
];

export function PlainGuide() {
  return <details className="plain-guide">
    <summary>Słownik finansowy</summary>
    <dl className="guide-grid">{terms.map(([term, description]) => <div key={term}><dt>{term}</dt><dd>{description}</dd></div>)}</dl>
    <p className="muted">Kreska w tabeli oznacza brak wartości, a nie zero. Kolor wykresu jest wskazówką — przeczytaj też opis zmiany.</p>
  </details>;
}
