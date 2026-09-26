import numpy as np
import pandas as pd

from research.leverage_study import build, debt_value, future_mean, estimate


def test_missing_debt_component_is_not_zero_and_conflicts_are_rejected():
    assert np.isnan(debt_value({'short_term_liabilities_loans': 10})[0])
    assert debt_value({'short_term_liabilities_loans': 10, 'long_term_liabilities_loans': 0})[0] == 10
    assert debt_value({'liabilities_borrowings': 50, 'short_term_liabilities_loans': 10, 'long_term_liabilities_loans': 5})[1] == 'conflict'


def test_future_windows_require_every_calendar_year_and_annualize():
    frame = pd.DataFrame({'company_id': ['a']*4, 'year': [2018,2019,2021,2022], 'roa': [.1,.2,.4,.6]}).set_index(['company_id','year'])
    assert np.isnan(future_mean(frame,'roa',2).loc[('a',2018)])
    assert future_mean(frame,'roa',1).loc[('a',2021)] == .6
    full = pd.DataFrame({'company_id':['a']*3,'year':[2020,2021,2022],'roa':[.1,.2,.4]}).set_index(['company_id','year'])
    assert abs(future_mean(full,'roa',2).loc[('a',2020)]-.3) < 1e-12


def profile(krs, count):
    return {'krs':krs,'name':'Test Development','provider_status':'active','screening':{'status':'missing_summary'},
            'financials':[{'currency':'PLN','consolidation_scope':'standalone','period_from_resolved':f'{y}-01-01',
                           'period_to_resolved':f'{y}-12-31','total_assets':1000000,'equity':600000,
                           'liabilities_and_provisions':400000,'profit_net':20000,'revenue_total':300000}
                          for y in range(2018,2018+count)]}


def test_five_year_minimum_counts_distinct_usable_years_not_records():
    short = profile('0000000001',4)
    short['financials'].append(dict(short['financials'][0]))
    long = profile('0000000002',5)
    _, selected, _, reasons, _ = build([short,long])
    assert [p['krs'] for p in selected] == ['0000000002']
    assert reasons['less_than_five_usable_years'] == 1


def test_conflicting_duplicate_year_does_not_silently_pick_first():
    conflict = profile('0000000001',5)
    conflict['financials'].append({**conflict['financials'][0], 'profit_net':99999})
    _, selected, audit, _, _ = build([conflict,profile('0000000002',5)])
    assert [p['krs'] for p in selected] == ['0000000002']
    assert audit['excluded_conflicting_company_years'] == 1


def test_lagged_fe_model_recovers_known_coefficient():
    rng = np.random.default_rng(12)
    records = []
    for company in range(30):
        debt = rng.uniform(.05,.8,8)
        for j, year in enumerate(range(2016,2024)):
            records.append({'company_id':str(company),'year':year,'debt_assets':debt[j],
                            'log_assets':rng.normal(15,1),'cash_assets':rng.uniform(0,.4),
                            'inventory_assets':rng.uniform(0,.7),'described':True,'source_conflicts':False,
                            'roa':.25*debt[j-1]+company*.003+year*.001 if j else np.nan})
    frame = pd.DataFrame(records).set_index(['company_id','year'])
    result = estimate(frame,1,'debt_assets')
    assert result['status'] == 'estimated'
    assert abs(result['coefficients']['debt_assets']['value']-.25) < 1e-9
