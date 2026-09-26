from datetime import date
from decimal import Decimal as D
from uuid import uuid4

from analytics.features import FeatureEngine,choose,DEFINITIONS


def observation(year,**values):
    return {'id':uuid4(),'company_id':uuid4(),'krs':'0000000001','fiscal_year':year,
        'period_start':date(year,1,1),'period_end':date(year,12,31),
        'duration_days':366 if year%4==0 else 365,'currency':'PLN','reported_unit_scale':None,
        'quality_codes':[],'consolidation_scope':'standalone',
        'reported_metrics':{k:D(str(v)) for k,v in dict(total_assets=100,equity=60,liabilities_and_provisions=40,
            current_assets=60,short_term_liabilities=30,cash_and_equivalents=20,revenue_total=100,profit_net=10,**values).items()}}


def test_lag_uses_calendar_not_row_offset():
    engine=FeatureEngine({2018:observation(2018),2020:observation(2020)})
    assert engine.value('debt_lag1',2020).reason=='missing_year'
    assert engine.value('debt_lag2',2020).value==D('.4')
    assert engine.value('revenue_growth',2020).value is None


def test_zero_is_not_missing_and_negative_profit_has_scaled_change():
    a=observation(2019)
    a['reported_metrics']['profit_net']=D('-10')
    a['reported_metrics']['liabilities_and_provisions']=D(0)
    b=observation(2020)
    engine=FeatureEngine({2019:a,2020:b})
    assert engine.value('liabilities_to_assets',2019).value==0
    assert engine.value('profit_growth',2020).reason=='nonpositive_denominator'
    assert engine.value('profit_change_scaled',2020).value==D('.2')


def test_recomputed_ratios_and_growth():
    a=observation(2019)
    b=observation(2020)
    b['reported_metrics']['revenue_total']=D(140)
    b['reported_metrics']['roa']=D(10)  # Supplier percentage must not be copied as fraction.
    engine=FeatureEngine({2019:a,2020:b})
    assert engine.value('revenue_growth',2020).value==D('.4')
    assert engine.value('roa',2020).value==D('.1')


def test_balance_issue_only_masks_dependent_derived_features():
    row=observation(2020)
    row['quality_codes']=['balance_mismatch']
    engine=FeatureEngine({2020:row})
    assert engine.value('roa',2020).reason=='balance_mismatch'
    assert engine.value('reported_total_assets',2020).value==100
    assert engine.value('net_margin',2020).value==D('.1')


def test_no_annualization_or_gap_bridging():
    a=observation(2019)
    b=observation(2020)
    b['period_start']=date(2020,2,1)
    b['duration_days']=335
    engine=FeatureEngine({2019:a,2020:b})
    assert engine.value('revenue_growth',2020).reason=='invalid_period'
    assert engine.value('current_ratio',2020).value==2


def test_conflicting_statements_remain_unresolved():
    a,b=observation(2020),observation(2020)
    assert choose([a,b])==(None,'unresolved_multiple')
    b['consolidation_scope']='consolidated'
    assert choose([a,b])==(a,'selected_unique')
    features,reasons=FeatureEngine({2020:None}).row(2020)
    assert all(v is None for v in features.values())
    assert set(reasons.values())=={'unresolved_selection'}


def test_forward_values_are_targets_and_do_not_change_past_features():
    a,b=observation(2019),observation(2020)
    before=FeatureEngine({2019:a,2020:b})
    b['reported_metrics']['profit_net']=D(99)
    assert before.value('roa',2019).value==D('.1')
    assert before.value('future_roa_h1',2019).value==D('.99')
    assert DEFINITIONS['future_roa_h1']['role']=='target'
    for name,d in DEFINITIONS.items():
        if d['role']=='feature':
            assert all(i['offset']<=0 for i in d['inputs'])


def test_rolling_requires_three_actual_growth_rates():
    rows={y:observation(y) for y in [2018,2019,2020,2021]}
    for y,row in rows.items():
        row['reported_metrics']['revenue_total']=D(100)*D(2)**(y-2018)
    engine=FeatureEngine(rows)
    assert engine.value('revenue_growth_rolling3_mean',2020).value is None
    assert engine.value('revenue_growth_rolling3_mean',2021).value==1
    assert engine.value('revenue_growth_rolling3_std',2021).value==0
