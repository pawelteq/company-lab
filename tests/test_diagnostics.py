import numpy as np
import pandas as pd
from analytics.features import DEFINITIONS
from research.diagnostics import select_candidates, denominator_dependencies, omit_company


def test_candidate_selection_is_company_bounded_and_scale_invariant():
    index=pd.MultiIndex.from_product([['a','b','c'],[2019,2020]],names=['company_id','year'])
    sample=pd.DataFrame({'x':[100,99,0,1,2,3],'outcome':[1,1,1,1,1,1]},index=index)
    chosen=select_candidates(sample,2)
    assert len(chosen)==len({c['company_id'] for c in chosen})==2
    assert chosen[0]['company_id']=='a'
    rescaled=select_candidates(sample.assign(x=sample.x*10000),2)
    assert [(c['company_id'],c['year']) for c in chosen]==[(c['company_id'],c['year']) for c in rescaled]
    assert all(np.isfinite(c['review_priority']) for c in chosen)


def test_denominators_respect_exact_outcome_and_delta_years():
    assert denominator_dependencies(DEFINITIONS,'revenue_growth',1)==[('reported_revenue_total',0)]
    assert denominator_dependencies(DEFINITIONS,'delta_margin',1)==[('reported_revenue_total',0),('reported_revenue_total',1)]
    assert denominator_dependencies(DEFINITIONS,'current_ratio')==[('reported_short_term_liabilities',0)]
    assert denominator_dependencies(DEFINITIONS,'log_assets')==[]


def test_omission_removes_entire_company_and_new_singletons():
    index=pd.MultiIndex.from_tuples([('a',2019),('a',2020),('b',2019),('b',2020),('c',2020),('c',2021)],names=['company_id','year'])
    frame=pd.DataFrame({'x':range(6),'outcome':range(6)},index=index)
    reduced,removed,singletons=omit_company(frame,'a')
    assert removed==2 and singletons==4 and reduced.empty
    assert len(frame)==6  # Never mutates the saved sample.
