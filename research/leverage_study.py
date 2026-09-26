"""Reproducible, exploratory leverage study; no selection by significance."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
import hashlib
import json
import re
import warnings

import numpy as np
import pandas as pd
from linearmodels import PanelOLS
from scipy.stats import norm
from statsmodels.stats.multitest import multipletests

from backend.app import connection
from backend.local_profiles import available as local_database_available
from backend.local_profiles import connect as local_connection
from backend.local_profiles import decompress_json
from etl.config import ROOT
from etl.developer_screening import normalized

SIGNIFICANCE_LEVEL = 0.10
CONFIDENCE_LEVEL = 1 - SIGNIFICANCE_LEVEL
Z_CRITICAL = float(norm.ppf(1 - SIGNIFICANCE_LEVEL / 2))
# The study is reported at alpha = 10%.  We retain these alternative thresholds
# as a transparent sensitivity check: they change only the interval/decision,
# never the fitted coefficient or p-value.
ALPHA_SENSITIVITY = (0.30, 0.20, 0.10, 0.01)

NAME = re.compile(r'\b(?:dev(?:elop(?:ment|er)\w*)?|dewelop\w*|apartament\w*|apartment\w*|domy?|osiedl\w*|mieszkan\w*)\b')
FIELDS = ['revenue_total', 'profit_net', 'ebit', 'equity', 'total_assets',
          'liabilities_and_provisions', 'current_assets', 'short_term_liabilities',
          'cash_and_equivalents', 'inventories', 'liabilities_borrowings',
          'long_term_liabilities_loans', 'short_term_liabilities_loans',
          'interest_expense', 'financial_costs', 'long_term_liabilities_related',
          'short_term_receivables', 'operating_costs_total', 'ebitda',
          'contract_deposits', 'contract_valuations', 'revenue_change_inventories']
PROTOCOL = {
    'version': 'lagged-leverage-3-alpha-10', 'minimum_years': 5,
    'selection': 'active, not suspended, description developer_candidate OR explicit housing/development name; contradictory other_activity excluded; latest usable annual PLN revenue >250000',
    'name_regex': NAME.pattern,
    'periods': 'standalone PLN, full calendar year, positive assets, balance within 2%; conflicting duplicate years excluded',
    'primary': 'two-year future annual average net profit / average assets; exposure current loans/assets; company and year fixed effects',
    'controls': ['log_assets', 'cash_assets', 'inventory_assets'],
    'horizons': [1, 2, 3], 'variants': ['raw', 'winsor_01_99'],
    'sensitivity': ['description_only', 'broad_liabilities_proxy'],
    'size_stratum': 'top 25% firms by median total assets across each selected firm\'s usable full-year reports; fixed company cohort',
    'debt': 'liabilities_borrowings, else sum short+long loans only if BOTH observed; disagreement excluded',
    'cost': 'interest_expense / mean debt(t-1,t), financial_costs proxy separately',
    'interaction': 'future ROA ~ loans/assets + observed interest cost + product + controls + firm FE + year FE',
    'scenarios': 'annual EBIT / average (equity+loans), equal-company weight, compare PRE-TAX annual 5..10%; not causal benefit or project IRR',
    'inference': 'cluster by company; overlapping horizons retained; two-sided alpha=0.10; 90% confidence intervals; BH q across reported debt and interaction tests',
    'significance_level': SIGNIFICANCE_LEVEL,
    'confidence_level': CONFIDENCE_LEVEL,
    'alpha_sensitivity': list(ALPHA_SENSITIVITY),
    'causal': False,
}


def num(value):
    try:
        result = float(value)
        return result if np.isfinite(result) else np.nan
    except (TypeError, ValueError):
        return np.nan


def debt_value(row):
    total = num(row.get('liabilities_borrowings'))
    short, long = (num(row.get(k)) for k in ['short_term_liabilities_loans', 'long_term_liabilities_loans'])
    component = short + long
    if np.isfinite(total) and np.isfinite(component) and abs(total-component) > max(1, abs(total)*.02):
        return np.nan, 'conflict'
    value = total if np.isfinite(total) else component
    if not np.isfinite(value) or value < 0:
        return np.nan, 'missing'
    return value, 'reported' if np.isfinite(total) else 'sum_two_observed_components'


def build(profiles, *, expanded=False, minimum_years=5):
    audit, reasons, selected, records = Counter(), Counter(), [], []
    coverage = Counter()
    for p in profiles:
        audit['all_profiles'] += 1
        if audit['all_profiles'] % 1000 == 0:
            print(f"Checked {audit['all_profiles']} profiles", flush=True)
        described = p.get('screening', {}).get('status') == 'developer_candidate'
        named = bool(NAME.search(normalized(p.get('name') or '')))
        if expanded:
            c = p.get('classification') or {}
            if c.get('business_type') not in ('developer','spv','contractor'):
                reasons['unresolved_or_other_activity'] += 1
                continue
            if c.get('is_active') is not True:
                reasons['inactive_or_unknown'] += 1
                continue
        else:
            if not (described or named):
                continue
            audit['description_or_name'] += 1
            if p.get('screening', {}).get('status') == 'other_activity':
                reasons['contradictory_description'] += 1
                continue
            if p.get('provider_status') != 'active' or p.get('is_currently_suspended'):
                reasons['inactive_or_unknown'] += 1
                continue
        years = defaultdict(list)
        for f in p.get('financials') or []:
            if f.get('currency') != 'PLN' or f.get('consolidation_scope') != 'standalone':
                audit['excluded_currency_scope_records'] += 1
                continue
            start = str(f.get('period_from_resolved') or f.get('sf_period_from') or '')[:10]
            end = str(f.get('period_to_resolved') or f.get('sf_period_to') or '')[:10]
            try:
                a, b = date.fromisoformat(start), date.fromisoformat(end)
            except ValueError:
                audit['excluded_period_records'] += 1
                continue
            if a != date(a.year, 1, 1) or b != date(a.year, 12, 31):
                audit['excluded_nonannual_records'] += 1
                continue
            r = {key: num(f.get(key)) for key in FIELDS}
            r.update(company_id=p['krs'], name=p.get('name'), year=b.year,
                     described=described, named=named, business_type=(p.get('classification') or {}).get('business_type'), source=f.get('source_pointer'),
                     source_hash=p.get('source_sha256'))
            r['debt'], r['debt_source'] = debt_value(f)
            if r['debt_source'] == 'conflict':
                audit['conflicting_debt_records'] += 1
            assets, equity, liabilities = (r[k] for k in ['total_assets', 'equity', 'liabilities_and_provisions'])
            if not (assets > 0 and np.isfinite(r['profit_net']) and np.isfinite(r['revenue_total'])
                    and np.isfinite(equity) and liabilities >= 0):
                audit['excluded_missing_core_records'] += 1
                continue
            if abs(assets-equity-liabilities) > max(1, assets*.02):
                audit['excluded_unbalanced_records'] += 1
                continue
            if r['debt'] > liabilities + max(1, liabilities*.02):
                r['debt'] = np.nan
                r['debt_source'] = 'exceeds_liabilities'
            r['source_conflicts'] = bool((p.get('source_merge') or {}).get('reports', {}).get('financials', {}).get('conflicts'))
            for key, value in f.items():
                if re.search(r'loan|borrow|related|shareholder|interest|affiliat', key) and not key.endswith(('_eur', '_usd')) and np.isfinite(num(value)):
                    coverage[key] += 1
            years[b.year].append(r)
        usable = []
        for year, group in years.items():
            signatures = {tuple(None if pd.isna(r[k]) else r[k] for k in FIELDS) for r in group}
            if len(signatures) > 1:
                audit['excluded_conflicting_company_years'] += 1
                continue
            audit['identical_duplicates_collapsed'] += len(group)-1
            usable.append(group[0])
        usable.sort(key=lambda r: r['year'])
        if len(usable) < minimum_years:
            reasons['less_than_five_usable_years' if minimum_years==5 else f'less_than_{minimum_years}_usable_years'] += 1
            continue
        if not expanded and usable[-1]['revenue_total'] <= 250000:
            reasons['latest_usable_revenue_not_above_250000'] += 1
            continue
        selected.append({'krs': p['krs'], 'name': p.get('name'), 'described': described, 'named': named,
                         'business_type':(p.get('classification') or {}).get('business_type'), 'years': [r['year'] for r in usable], 'latest_revenue': usable[-1]['revenue_total'],
                         'median_assets': float(np.median([r['total_assets'] for r in usable]))})
        records.extend(usable)
    frame = pd.DataFrame(records)
    if frame.empty:
        raise ValueError('No firms satisfy the predeclared selection')
    frame = frame.sort_values(['company_id', 'year']).set_index(['company_id', 'year'])
    frame['debt_assets'] = frame.debt / frame.total_assets
    frame['liabilities_assets'] = frame.liabilities_and_provisions / frame.total_assets
    frame['cash_assets'] = frame.cash_and_equivalents / frame.total_assets
    frame['inventory_assets'] = frame.inventories / frame.total_assets
    frame['log_assets'] = np.log(frame.total_assets)
    frame['capital'] = frame.equity + frame.debt
    # Firm size is fixed at the company level.  This avoids reclassifying a company
    # as "large" only after a high-result year and makes the top-quartile cohort
    # consistent across every annual observation.
    sizes = pd.Series({p['krs']: p['median_assets'] for p in selected}, name='median_assets')
    top_quartile_cutoff = float(sizes.quantile(.75))
    frame['top_assets_q4'] = frame.index.get_level_values('company_id').map(sizes).to_numpy() >= top_quartile_cutoff
    for p in selected:
        p['top_assets_q4'] = bool(p['median_assets'] >= top_quartile_cutoff)
    prior = shifted(frame[['total_assets', 'equity', 'capital', 'debt']], -1)
    for key in ['total_assets', 'equity', 'capital', 'debt']:
        frame['avg_'+key] = (frame[key]+prior[key])/2
    frame['roa'] = frame.profit_net / frame.avg_total_assets.where(frame.avg_total_assets > 0)
    frame['roe'] = frame.profit_net / frame.avg_equity.where((frame.avg_equity > 0) & (frame.equity > 0) & (prior.equity > 0))
    frame['pretax_roc'] = frame.ebit / frame.avg_capital.where((frame.capital > 0) & (prior.capital > 0) & (frame.equity > 0) & (prior.equity > 0))
    for field, label in [('interest_expense', 'interest_cost'), ('financial_costs', 'financial_cost_proxy')]:
        frame[label] = frame[field].where(frame[field] >= 0) / frame.avg_debt.where(frame.avg_debt > 0)
    audit.update(selected_companies=len(selected), selected_company_years=len(frame),
                 described_companies=sum(p['described'] for p in selected),
                 name_only_companies=sum(not p['described'] for p in selected),
                 top_assets_q4_companies=sum(p['top_assets_q4'] for p in selected),
                 top_assets_q4_company_years=int(frame.top_assets_q4.sum()))
    audit['top_assets_q4_cutoff_pln'] = top_quartile_cutoff
    return frame, selected, dict(audit), dict(reasons), dict(coverage)


def shifted(frame, years):
    """At (i,t), return original (i,t+years); missing years remain missing."""
    out = frame.copy()
    out.index = pd.MultiIndex.from_arrays([out.index.get_level_values(0), out.index.get_level_values(1)-years], names=out.index.names)
    return out


def future_mean(frame, field, horizon):
    windows = pd.concat([shifted(frame[[field]], h).rename(columns={field: str(h)}) for h in range(1, horizon+1)], axis=1).reindex(frame.index)
    return windows.mean(axis=1).where(windows.notna().all(axis=1))


def estimate(frame, horizon, exposure, outcome='roa', variant='raw', cohort='all', interaction=None,
             controls=None, outcome_at_t=False, point_lag=False):
    mask = (
        frame.described if cohort == 'description_only' else
        ~frame.source_conflicts if cohort == 'no_source_conflicts' else
        frame.top_assets_q4 if cohort == 'top_assets_q4' else
        pd.Series(True, index=frame.index)
    )
    controls = PROTOCOL['controls'] if controls is None else controls
    cols = [exposure, *controls] + ([interaction] if interaction else [])
    work = frame.loc[mask, cols].copy()
    work['outcome'] = frame[outcome] if outcome_at_t else shifted(frame[[outcome]],horizon)[outcome].reindex(frame.index) if point_lag else future_mean(frame, outcome, horizon)
    work = work.replace([np.inf, -np.inf], np.nan).dropna()
    if interaction:
        work = work[(work[interaction] >= 0) & (work[interaction] <= 1)]
    complete = len(work)
    while len(work):
        keep = (work.groupby(level=0).outcome.transform('size') >= 2) & (work.groupby(level=1).outcome.transform('size') >= 2)
        if keep.all():
            break
        work = work[keep]
    info = {'horizon': horizon, 'outcome': outcome, 'exposure': exposure, 'cohort': cohort,
            'variant': variant, 'interaction': interaction, 'complete_cases': complete,
            'outcome_at_t': outcome_at_t, 'point_lag':point_lag, 'n': len(work),
            'companies': work.index.get_level_values(0).nunique()}
    if len(work) < 50 or info['companies'] < 20:
        return {**info, 'status': 'insufficient_data'}
    if variant != 'raw':
        for c in work:
            work[c] = work[c].clip(*work[c].quantile([.01, .99]))
    x = work.drop(columns='outcome').assign(const=1.)
    if interaction:
        x['debt_x_cost'] = x[exposure]*x[interaction]
    try:
        with warnings.catch_warnings(record=True) as messages:
            fit = PanelOLS(work.outcome, x, entity_effects=True, time_effects=True, drop_absorbed=True).fit(cov_type='clustered', cluster_entity=True)
        coefficients = {
            key: {
                'value': float(fit.params[key]),
                'p': float(fit.pvalues[key]),
                'lo': float(fit.params[key] - Z_CRITICAL * fit.std_errors[key]),
                'hi': float(fit.params[key] + Z_CRITICAL * fit.std_errors[key]),
                'intervals_by_alpha': {
                    f'{alpha:.2f}': {
                        'confidence_level': 1 - alpha,
                        'lo': float(fit.params[key] - norm.ppf(1 - alpha / 2) * fit.std_errors[key]),
                        'hi': float(fit.params[key] + norm.ppf(1 - alpha / 2) * fit.std_errors[key]),
                        'significant': bool(fit.pvalues[key] < alpha),
                    }
                    for alpha in ALPHA_SENSITIVITY
                },
            }
            for key in fit.params.index
        }
        info.update(status='estimated', coefficients=coefficients, within_r2=float(fit.rsquared_within),
                    warnings=[str(m.message) for m in messages])
        if interaction and 'debt_x_cost' in fit.params.index and exposure in fit.params.index:
            info['marginal_at_cost'] = []
            for cost in [.05, .06, .07, .08, .09, .10]:
                b = fit.params[exposure]+cost*fit.params['debt_x_cost']
                variance = fit.cov.loc[exposure, exposure]+cost**2*fit.cov.loc['debt_x_cost', 'debt_x_cost']+2*cost*fit.cov.loc[exposure, 'debt_x_cost']
                se = np.sqrt(max(0, variance))
                info['marginal_at_cost'].append({'cost': cost, 'value': float(b), 'lo': float(b-Z_CRITICAL*se), 'hi': float(b+Z_CRITICAL*se)})
            info['observed_cost_quantiles'] = work[interaction].quantile([.05,.5,.95]).to_dict()
        return info
    except (ValueError, np.linalg.LinAlgError, ZeroDivisionError) as exc:
        return {**info, 'status': 'failed', 'error': str(exc)}


def scenarios(frame, cohort='all'):
    result = []
    if cohort == 'top_assets_q4':
        frame = frame.loc[frame.top_assets_q4]
    rng = np.random.default_rng(20260914)
    for horizon in [1, 2, 3]:
        future = future_mean(frame, 'pretax_roc', horizon).dropna()
        # One latest complete future window per firm avoids overweighting long histories.
        windows = future.groupby(level=0).tail(1)
        values = windows.to_numpy()
        if not len(values):
            continue
        for cost in [.05,.06,.07,.08,.09,.10]:
            shares = []
            for _ in range(500):
                shares.append(float(np.mean(rng.choice(values, len(values), replace=True) > cost)))
            result.append({'cohort': cohort, 'horizon': horizon, 'cost': cost, 'companies': len(values),
                           'median_annual_pretax_roc': float(np.median(values)),
                           'median_spread': float(np.median(values)-cost),
                           'share_above': float(np.mean(values > cost)),
                           'share_ci_low': float(np.quantile(shares, SIGNIFICANCE_LEVEL / 2)),
                           'share_ci_high': float(np.quantile(shares, 1 - SIGNIFICANCE_LEVEL / 2)),
                           'base_years': sorted(set(map(int, windows.index.get_level_values(1))))})
    return result


def load_current_panel():
    if local_database_available():
        data_source = 'local_sqlite'
        with local_connection() as conn:
            row = conn.execute('SELECT id FROM profile_collection ORDER BY created_at DESC,id DESC LIMIT 1').fetchone()
            collection = str(row['id'])
            profiles = conn.execute('SELECT profile_json_zlib FROM profile_screening WHERE collection_id=? ORDER BY krs', (collection,))
            panel = build(decompress_json(record['profile_json_zlib']) for record in profiles)
    else:
        data_source = 'postgres'
        with connection() as conn:
            collection = str(conn.execute('SELECT id FROM core.profile_collection ORDER BY created_at DESC,id DESC LIMIT 1').fetchone()['id'])
            with conn.cursor(name='leverage_profiles') as cursor:
                cursor.execute("SELECT profile - ARRAY['raw_profile','company_info','profile_details','connections','graph','people','roles','ownership','related_companies','statistics','insights_by_year','seo_metric_summaries_by_year','faq','similar_companies','subsidiary_companies','change_history','ownership_family_insight'] AS profile FROM core.profile_screening WHERE collection_id=%s ORDER BY krs", (collection,))
                panel = build(r['profile'] for r in cursor)
    return collection, data_source, panel


def run():
    collection, data_source, (frame, selected, audit, exclusions, fields) = load_current_panel()
    ident = hashlib.sha256((collection+Path(__file__).read_text(encoding='utf-8')).encode()).hexdigest()[:16]
    folder = ROOT/'data/research/leverage'/ident
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'protocol.json').write_text(json.dumps(PROTOCOL, ensure_ascii=False, indent=2), encoding='utf-8')
    models = []
    for h in [1,2,3]:
        print(f'Estimating horizon {h}', flush=True)
        for variant in ['raw', 'winsor_01_99']:
            models.append(estimate(frame,h,'debt_assets',variant=variant))
            models.append(estimate(frame,h,'liabilities_assets',variant=variant))
            models.append(estimate(frame,h,'debt_assets',outcome='roe',variant=variant))
        models.append(estimate(frame,h,'debt_assets',cohort='description_only'))
        models.append(estimate(frame,h,'debt_assets',cohort='no_source_conflicts'))
        models.append(estimate(frame,h,'debt_assets',cohort='top_assets_q4'))
        models.append(estimate(frame,h,'debt_assets',outcome='roe',cohort='top_assets_q4'))
        # Broader balance-sheet proxy, kept separate from loans because it can
        # include trade payables and provisions.
        models.append(estimate(frame,h,'liabilities_assets',cohort='top_assets_q4'))
    for cost in ['interest_cost', 'financial_cost_proxy']:
        for variant in ['raw', 'winsor_01_99']:
            models.append(estimate(frame,2,'debt_assets',variant=variant,interaction=cost))
    primary_terms = []
    for model in models:
        if model['status'] == 'estimated':
            term = 'debt_x_cost' if model['interaction'] else model['exposure']
            if term in model['coefficients']:
                primary_terms.append(model['coefficients'][term])
    if primary_terms:
        for term, q in zip(primary_terms, multipletests([t['p'] for t in primary_terms], method='fdr_bh')[1]):
            term['q_bh'] = float(q)
    counts = {key: {'observed': int(frame[key].notna().sum()), 'positive': int((frame[key] > 0).sum()),
                    'companies': int(frame[frame[key].notna()].index.get_level_values(0).nunique())}
              for key in ['debt', 'interest_cost', 'financial_cost_proxy', 'pretax_roc', 'long_term_liabilities_related']}
    output = {'run_id': ident, 'collection_id': collection, 'data_source': data_source, 'protocol': PROTOCOL, 'audit': audit,
              'exclusions': exclusions, 'field_inventory': fields, 'coverage': counts,
              'models': models, 'scenarios': scenarios(frame),
              'top_assets_q4_scenarios': scenarios(frame, 'top_assets_q4'),
              'years': sorted(map(int, frame.index.get_level_values(1).unique())),
              'limitations': [
                  'Nazwa to kwalifikacja przesiewowa, nie potwierdzenie działalności. Opis dotyczy obecnej firmy, nie każdego historycznego roku.',
                  'Wybór aktywnych firm, pięciu lat danych i przychodu powyżej progu powoduje selekcję oraz pominięcie młodych spółek projektowych.',
                  'Efekty stałe i opóźnienia nie dowodzą przyczynowości; decyzje o kredycie i oczekiwane wyniki mogą mieć wspólne przyczyny.',
                  'Zobowiązania i rezerwy obejmują pozycje nieoprocentowane; model tej zmiennej jest osobną analizą pomocniczą.',
                  'Koszty finansowe nie są samymi odsetkami. Odsetki kapitalizowane w zapasach mogą nie trafiać do bieżącego wyniku.',
                  'Zobowiązania wobec powiązanych nie oznaczają wyłącznie pożyczek; brak rozbicia odsetek według wierzyciela uniemożliwia porównanie oprocentowania banku i wspólnika.',
                  'Scenariusze 5–10% to księgowy zwrot przed podatkiem względem założonej stopy przed podatkiem, nie oszacowanie efektu nowego kredytu ani IRR projektu.',
                  'Modele ROE pomijają nie-dodatni kapitał; krótki panel, skrajne ilorazy i zależność spółek z jednej grupy ograniczają wnioskowanie.',
                  'Warstwa największych firm jest zdefiniowana przez medianę aktywów w dostępnej historii, a nie przez bieżący wynik. Nadal nie eliminuje to różnic jakości zarządzania, dostępu do finansowania ani przynależności do grupy.',
              ]}
    main = next(m for m in models if m['horizon']==2 and m['outcome']=='roa' and m['exposure']=='debt_assets' and m['cohort']=='all' and m['variant']=='raw' and not m['interaction'])
    c = main.get('coefficients',{}).get('debt_assets')
    if c is None:
        conclusion = 'Próba modelu głównego jest niewystarczająca. Tezy o dodatnim wpływie długu na przyszły wynik nie da się potwierdzić tym modelem.'
    elif c['lo'] <= 0 <= c['hi']:
        conclusion = 'Model główny nie rozstrzyga kierunku zależności długu z przyszłym wynikiem: przedział ufności obejmuje zero. Dane nie stanowią dowodu, że zwiększanie długu poprawia wyniki.'
    elif c['hi'] < 0:
        conclusion = 'Model główny wskazuje ujemną zależność udziału kredytów i pożyczek z przyszłym ROA. Wynik nie potwierdza ogólnej tezy, że większe zadłużenie poprawia wyniki.'
    else:
        conclusion = 'Model główny wskazuje dodatnią zależność długu z przyszłym ROA. Jej wiarygodność należy ocenić względem korekty wielokrotnych testów i wariantów wrażliwości; nie jest to dowód przyczynowy.'
    output['conclusion'] = conclusion
    large_main = next(m for m in models if m['horizon']==2 and m['outcome']=='roa' and m['exposure']=='debt_assets' and m['cohort']=='top_assets_q4' and m['variant']=='raw' and not m['interaction'])
    large_c = large_main.get('coefficients', {}).get('debt_assets')
    if large_c is None:
        output['top_assets_q4_conclusion'] = 'Dla największej jednej czwartej firm po zastosowaniu opóźnienia i kontroli nie ma jeszcze wystarczającej liczby obserwacji do oszacowania modelu głównego.'
    elif large_c['lo'] <= 0 <= large_c['hi']:
        output['top_assets_q4_conclusion'] = 'W największej jednej czwartej firm model główny nie rozstrzyga kierunku zależności długu z przyszłym ROA: przedział ufności obejmuje zero.'
    elif large_c['hi'] < 0:
        output['top_assets_q4_conclusion'] = 'W największej jednej czwartej firm model główny wskazuje ujemną zależność długu z przyszłym ROA; nie potwierdza to tezy o ogólnej korzyści z większego zadłużenia.'
    else:
        output['top_assets_q4_conclusion'] = 'W największej jednej czwartej firm model główny wskazuje dodatnią zależność długu z przyszłym ROA. Jest to wynik obserwacyjny, a nie dowód, że każdy dodatkowy kredyt podnosi wynik.'
    # JSON files retain all estimates, including insignificant and failed specifications.
    (folder/'results.json').write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    (folder/'selection.json').write_text(json.dumps(selected, ensure_ascii=False, indent=2), encoding='utf-8')
    frame.reset_index().to_parquet(folder/'panel.parquet', index=False)
    lines = ['# Dług i odroczone wyniki deweloperów', '', conclusion, '', f'Kolekcja: {collection}. Badanie: {ident}.', '',
             f"Próba: {len(selected)} firm, {len(frame)} obserwacji; {audit['described_companies']} według opisu, {audit['name_only_companies']} tylko według nazwy.",
             f"Największa 1/4: {audit['top_assets_q4_companies']} firm i {audit['top_assets_q4_company_years']} obserwacji; próg mediany aktywów: {audit['top_assets_q4_cutoff_pln']:.0f} PLN.",
             '', '## Największa jedna czwarta firm', '', output['top_assets_q4_conclusion'],
             '', '## Modele', '', f'Wynik: średnia roczna przyszłych ROA lub ROE, z dokładnie kolejnych 1–3 lat. Efekty firmy i roku, błędy klastrowane po firmie. Testy są dwustronne przy α = {SIGNIFICANCE_LEVEL:.0%}; podajemy {CONFIDENCE_LEVEL:.0%} przedziały ufności. Współczynnik × 10 daje zmianę wyniku w punktach procentowych przy wzroście udziału długu o 10 pp.', '',
             f'| Horyzont | Wynik | Zadłużenie | Wariant / próba / koszt | Firmy | N | Współczynnik | {CONFIDENCE_LEVEL:.0%} CI | p | q BH |',
             '|---|---|---|---|---:|---:|---:|---|---:|---:|']
    for m in models:
        c = m.get('coefficients',{}).get('debt_x_cost' if m['interaction'] else m['exposure'])
        if c:
            lines.append(f"| {m['horizon']} | {m['outcome']} | {m['exposure']} | {m['variant']} / {m['cohort']} / {m['interaction'] or '—'} | {m['companies']} | {m['n']} | {c['value']:.5f} | [{c['lo']:.5f}; {c['hi']:.5f}] | {c['p']:.4f} | {c.get('q_bh',1):.4f} |")
        else:
            lines.append(f"| {m['horizon']} | {m['outcome']} | {m['exposure']} | {m['variant']} / {m['cohort']} / {m['interaction']} | {m['companies']} | {m['n']} | {m['status']} | — | — | — |")
    main_coef = main.get('coefficients', {}).get('debt_assets')
    if main_coef:
        lines += ['', '## Wrażliwość na poziom istotności', '',
                  'To ten sam model główny; zmienia się wyłącznie próg decyzji i szerokość przedziału. Współczynnik oraz p nie są przeliczane ani dobierane ponownie.', '',
                  '| α | Poziom ufności | Przedział współczynnika | p | Istotny przy tym α? |',
                  '|---:|---:|---|---:|---|']
        for alpha in ALPHA_SENSITIVITY:
            interval = main_coef['intervals_by_alpha'][f'{alpha:.2f}']
            lines.append(f"| {alpha:.2f} | {interval['confidence_level']:.0%} | [{interval['lo']:.5f}; {interval['hi']:.5f}] | {main_coef['p']:.4f} | {'Tak' if interval['significant'] else 'Nie'} |")
    lines += ['', '## Scenariusze oprocentowania', '', f'Jedno najnowsze kompletne okno na firmę. Roczna średnia EBIT / średni kapitał (kapitał własny + kredyty i pożyczki). Brak danych nie jest zerem. Stopy nie są aktualną ofertą rynkową. Udziały mają {CONFIDENCE_LEVEL:.0%} bootstrapowe przedziały ufności.', '', f'| Lata wyniku | Koszt roczny | Firmy | Mediana zwrotu rocznego | Udział powyżej kosztu | {CONFIDENCE_LEVEL:.0%} CI udziału |', '|---|---:|---:|---:|---:|---|']
    for s in output['scenarios']:
        lines.append(f"| {s['horizon']} | {s['cost']:.0%} | {s['companies']} | {s['median_annual_pretax_roc']:.2%} | {s['share_above']:.1%} | [{s['share_ci_low']:.1%}; {s['share_ci_high']:.1%}] |")
    lines += ['', '### Największa jedna czwarta — scenariusze', '']
    for s in output['top_assets_q4_scenarios']:
        lines.append(f"| {s['horizon']} | {s['cost']:.0%} | {s['companies']} | {s['median_annual_pretax_roc']:.2%} | {s['share_above']:.1%} | [{s['share_ci_low']:.1%}; {s['share_ci_high']:.1%}] |")
    lines += ['', '## Pokrycie i wykluczenia', '', '```json', json.dumps({'audit':audit,'exclusions':exclusions,'coverage':counts},ensure_ascii=False,indent=2), '```', '', '## Ograniczenia', '', *['- '+s for s in output['limitations']], '', '## Metoda i źródła', '',
              '- [PanelOLS: efekty stałe](https://bashtage.github.io/linearmodels/panel/panel/linearmodels.panel.model.PanelOLS.html)',
              '- [Damodaran: zwrot z kapitału i koszt finansowania](https://pages.stern.nyu.edu/~adamodar/New_Home_Page/lectures/capstr.html)', '']
    (folder/'report.md').write_text('\n'.join(lines), encoding='utf-8')
    print(json.dumps({'folder':str(folder),'audit':audit,'coverage':counts}, ensure_ascii=False, indent=2), flush=True)
    return output


if __name__ == '__main__':
    run()
