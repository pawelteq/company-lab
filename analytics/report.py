"""R00: descriptive coverage and distributions, not model estimates or recommendations."""
import json
from pathlib import Path
import pandas as pd
import pyarrow.parquet as pq
import psycopg
from etl.config import ROOT
from etl.storage import digest_file


def report(url,dataset):
    with psycopg.connect(url,connect_timeout=10) as conn:
        meta=conn.execute('SELECT artifact_manifest,maturity,research_ready FROM analytics.dataset WHERE id=%s',(dataset,)).fetchone()
        if meta is None:
            raise ValueError('Unknown dataset')
    manifest=meta[0]
    for item in manifest:
        if digest_file(Path(item['path']))!=(item['sha256'],item['bytes']):
            raise ValueError('Dataset artifact differs from published manifest')
    folder=Path(manifest[0]['path']).parent
    summary=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
    columns=['company_id','krs','year','selection_status','panel_full','panel_3plus','panel_5plus','panel_long',
             'revenue_growth','profit_growth','asset_growth','equity_growth','liabilities_to_assets','current_ratio',
             'roa','roe','net_margin','cash_to_assets','receivables_to_assets','profit_change_scaled','delta_margin']
    frame=pq.read_table(folder/'panel.parquet',columns=columns).to_pandas()
    if frame.duplicated(['company_id','year']).any():
        raise ValueError('Duplicate company-year in published panel')
    lines=['# R00 — pierwszy raport panelu','',f'Dataset: `{dataset}`.',
        '**Status: eksploracyjny, na wartościach raportowanych przez dostawcę. Nie jest dopuszczony do rekomendacji ani zatwierdzonych modeli.**',
        'Raport opisuje dostępność i rozkłady; nie ocenia efektu zadłużenia, optymalnej strategii ani ryzyka upadłości.', '',
        '## Zakres','',f"Panel zawiera {len(frame):,} par firma–rok i {frame.company_id.nunique():,} firm.",
        f"Wybrano jednoznacznego kandydata jednostkowego w {summary['selection'].get('selected_unique',0):,} parach.",
        'Pozostałe wiersze pozostają w panelu z pustymi cechami i statusem wyboru. Firma bez finansów pozostaje w katalogu.', '',
        '| Klasa | Firmy | Obserwacje dostępności |','|---|---:|---:|']
    for name in ['panel_full','panel_3plus','panel_5plus','panel_long']:
        part=frame[frame[name]]
        lines.append(f'| {name} | {part.company_id.nunique():,} | {len(part):,} |')
    lines+=['','Klasy liczone z dostępnych lat, nie z liczby kompletnych obserwacji regresji.',
        'Nie są cechami predykcyjnymi, ponieważ uwzględniają pełną dostępną historię.', '',
        '## Pokrycie według roku','',
        '| Rok | Firma–rok | Wybrany standalone | Dostępny revenue_growth |','|---|---:|---:|---:|']
    for year,part in frame.groupby('year'):
        lines.append(f"| {year} | {len(part):,} | {(part.selection_status=='selected_unique').sum():,} | {part.revenue_growth.notna().sum():,} |")
    lines+=['','## Rozkłady dostępnych wartości','',
        'Wskaźniki i wzrosty podano jako ułamki (0,10 oznacza 10%). Dane nominalne, bez winsoryzacji.',
        'Percentyle opisują wyłącznie dostępne wartości konkretnej zmiennej; próby w wierszach mogą się różnić.',
        'Ekstremalne ilorazy mogą wynikać z bardzo małego dodatniego mianownika lub błędnego mapowania.', '',
        '| Zmienna | N | Braki % | P01 | Mediana | P99 |','|---|---:|---:|---:|---:|---:|']
    distribution={}
    for name in columns[8:]:
        series=frame[name].dropna()
        quantiles=series.quantile([.01,.5,.99]) if len(series) else pd.Series([float('nan')]*3,index=[.01,.5,.99])
        distribution[name]={'n':len(series),'missing':len(frame)-len(series),'p01':None if not len(series) else float(quantiles.loc[.01]),
                            'median':None if not len(series) else float(quantiles.loc[.5]),'p99':None if not len(series) else float(quantiles.loc[.99])}
        fmt=lambda x:f'{x:.4g}' if pd.notna(x) else 'brak'
        lines.append(f'| {name} | {len(series):,} | {(1-len(series)/len(frame))*100:.1f} | {fmt(quantiles.loc[.01])} | {fmt(quantiles.loc[.5])} | {fmt(quantiles.loc[.99])} |')
    lines+=['','## Quality of Growth','',
        'W wersji v1 jest wektorem zmian przychodów, zysku, zobowiązań, aktywów, gotówki, należności i marży.',
        'Nie utworzono łącznego score. Wzrost zysku od zerowej/ujemnej bazy jest niedostępny;',
        'profit_change_scaled zachowuje możliwość opisania przejść ze straty do zysku.', '',
        '## Ograniczenia i dalsze badania','',
        '- Wartości są zależne od mapowań dostawcy; spójność importu nie dowodzi poprawności semantycznej.',
        '- Brak niezależnego potwierdzenia skali kwot i części okresów resolved.',
        '- Braki i wykluczenia nie są losowe: formularze, rozmiar firmy i długość historii zmieniają próbę.',
        '- Kohorta nie jest udokumentowaną próbą reprezentatywną wszystkich firm.',
        '- Źródła pobrano retrospektywnie; brak historii publikacji ogranicza backtest i predykcję.',
        '- Raport nie zawiera regresji, prognoz, przyczynowych efektów ani rekomendacji.', '',
        'Następny krok: zatwierdzanie mapowań na poziomie formularza/zmiennej, raport przejścia do próby',
        'estymacyjnej, analiza małych mianowników i planowane warianty wrażliwości, następnie R01–R04.', '',
        'Szczegółowy protokół: [DATASET_SPEC.md](DATASET_SPEC.md). Architektura: [ARCHITECTURE.md](ARCHITECTURE.md).', '']
    destination=ROOT/'docs/R00_PANEL_REPORT.md'
    destination.write_text('\n'.join(lines),encoding='utf-8')
    out=ROOT/'data/research'/str(dataset)
    out.mkdir(parents=True,exist_ok=True)
    (out/'r00_distributions.json').write_text(json.dumps(distribution,indent=2),encoding='utf-8')
    print('R00 report: '+str(destination))
    return distribution
