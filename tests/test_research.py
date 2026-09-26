import numpy as np
import pandas as pd
from research.run import prepare,fit


def test_outcome_alignment_does_not_jump_year_gap():
    rows=[{'company_id':str(c),'year':year,'x':float(c+year),'response':float(year)} for c in range(10) for year in [2018,2020,2021]]
    data,flow=prepare(pd.DataFrame(rows),{'exposure':'x','controls':[],'outcome':'response'},
        {'horizon':1,'year_from':2018,'year_to':2020})
    assert flow['outcome_available']==10  # Only 2020 has a real year+1.
    assert flow['after_singletons']==0


def test_fixed_effects_recover_known_conditional_coefficient():
    rng=np.random.default_rng(87)
    records=[]
    for c in range(20):
        xs=rng.normal(size=7)
        for i,year in enumerate(range(2017,2024)):
            records.append({'company_id':str(c),'year':year,'x':xs[i],
                'response':2*xs[i-1]+c*.3+year*.1 if i else np.nan})
    spec={'exposure':'x','controls':[],'outcome':'response','quadratic':False}
    data,flow=prepare(pd.DataFrame(records),spec,{'horizon':1,'year_from':2017,'year_to':2022})
    result=fit(data,spec,'firm_and_year_fe','untrimmed')
    assert result['status']=='estimated'
    assert result['n_observations']==120
    assert abs(result['coefficients']['x']['coefficient']-2)<1e-10
    assert result['covariance']=='clustered_by_company'
    scaled=data.copy()
    scaled['x']=scaled['x']*1e12
    large=fit(scaled,spec,'firm_and_year_fe','untrimmed')
    assert abs(large['coefficients']['x']['coefficient']*1e12-2)<1e-10
