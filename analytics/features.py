"""Exact-year feature graph with explicit missingness and source dependencies."""
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, localcontext
from etl.parsing import METRICS

BALANCE=set('total_assets equity liabilities_and_provisions fixed_assets current_assets short_term_receivables cash_and_equivalents inventories short_term_liabilities long_term_liabilities liabilities_borrowings'.split())
DEFINITIONS={}


def define(name,op,inputs=(),*,unit='fraction',annual=False,role='feature',source=None):
    DEFINITIONS[name]={'op':op,'inputs':[{'name':n,'offset':o} for n,o in inputs],
        'unit':unit,'annual':annual,'role':role,'source':source}


for metric in METRICS:
    define('reported_'+metric,'source',unit='provider_reported',source=metric)
for name,num,den,annual in [
    ('liabilities_to_assets','liabilities_and_provisions','total_assets',False),
    ('liabilities_to_equity','liabilities_and_provisions','equity',False),
    ('short_term_liabilities_to_assets','short_term_liabilities','total_assets',False),
    ('long_term_liabilities_to_assets','long_term_liabilities','total_assets',False),
    ('current_ratio','current_assets','short_term_liabilities',False),
    ('cash_ratio','cash_and_equivalents','short_term_liabilities',False),
    ('cash_to_assets','cash_and_equivalents','total_assets',False),
    ('roa','profit_net','total_assets',True),('roe','profit_net','equity',True),
    ('net_margin','profit_net','revenue_total',True),('ebitda_margin','ebitda','revenue_total',True),
    ('asset_turnover','revenue_total','total_assets',True),('equity_to_assets','equity','total_assets',False),
    ('receivables_to_assets','short_term_receivables','total_assets',False),
    ('receivables_to_revenue','short_term_receivables','revenue_total',True),
    ('cash_to_revenue','cash_and_equivalents','revenue_total',True),
    ('inventories_to_assets','inventories','total_assets',False),
    ('current_assets_to_assets','current_assets','total_assets',False),
]:
    define(name,'ratio',[(f'reported_{num}',0),(f'reported_{den}',0)],annual=annual)
for name,metric in [('revenue','revenue_total'),('profit','profit_net'),('asset','total_assets'),
                    ('equity','equity'),('debt','liabilities_and_provisions'),('cash','cash_and_equivalents'),('receivables','short_term_receivables')]:
    define(name+'_growth','growth',[(f'reported_{metric}',0),(f'reported_{metric}',-1)],annual=True)
for name,metric in [('revenue','revenue_total'),('assets','total_assets'),('equity','equity')]:
    define('log_'+name,'log',[(f'reported_{metric}',0)],unit='log_reported_amount',annual=True)
for name,feature in [('leverage','liabilities_to_assets'),('liquidity','current_ratio'),('roa','roa'),
                    ('margin','net_margin'),('cash','reported_cash_and_equivalents'),
                    ('receivables','reported_short_term_receivables'),('assets','reported_total_assets'),('equity','reported_equity')]:
    define('delta_'+name,'delta',[(feature,0),(feature,-1)],unit='reported_amount' if feature.startswith('reported_') else 'fraction_change',annual=True)
define('profit_change_scaled','scaled_change',[('reported_profit_net',0),('reported_profit_net',-1),('reported_total_assets',-1)],annual=True)
for name,feature,lags in [('debt','liabilities_to_assets',[1,2,3]),('liquidity','current_ratio',[1]),
                         ('roa','roa',[1]),('size','log_assets',[1])]:
    for lag in lags:
        define(f'{name}_lag{lag}','identity',[(feature,-lag)],annual=True)
for feature in ['revenue_growth','profit_growth','roa']:
    for horizon in [1,2,3]:
        define(f'future_{feature}_h{horizon}','identity',[(feature,horizon)],annual=True,role='target')
for op in ['mean','std']:
    define('revenue_growth_rolling3_'+op,op,[('revenue_growth',0),('revenue_growth',-1),('revenue_growth',-2)],annual=True)


@dataclass(frozen=True)
class Value:
    value: Decimal | None
    reason: str | None=None


def choose(records):
    standalone=[r for r in records if r['consolidation_scope']=='standalone']
    if len(standalone)==1:
        return standalone[0],'selected_unique'
    return None,'unresolved_multiple' if standalone else 'unavailable_standalone'


def annual(record):
    return bool(record and record['period_start'] and record['period_end'] and record['duration_days'] in (365,366)
        and not set(record['quality_codes']) & {'invalid_period','invalid_date','period_start_conflict','period_end_conflict','incomplete_period'})


class FeatureEngine:
    def __init__(self,selected):
        self.selected=selected
        self.cache={}

    def value(self,name,year):
        key=name,year
        if key in self.cache:
            return self.cache[key]
        with localcontext() as ctx:
            ctx.prec=28
            value=self.calculate(name,year)
        self.cache[key]=value
        return value

    def calculate(self,name,year):
        row=self.selected.get(year)
        if row is None:
            return Value(None,'missing_year' if year not in self.selected else 'unresolved_selection')
        definition=DEFINITIONS[name]
        if definition['op']=='source':
            v=row['reported_metrics'].get(definition['source'])
            if v is not None:
                v=Decimal(str(v))
            return Value(v,None if v is not None else 'missing_input')
        if 'extraction_not_ok' in row['quality_codes']:
            return Value(None,'extraction_not_ok')
        if row['currency']!='PLN':
            return Value(None,'unsupported_currency')
        if definition['annual'] and not annual(row):
            return Value(None,'invalid_period')
        values=[]
        for dependency in definition['inputs']:
            target_year=year+dependency['offset']
            other=self.selected.get(target_year)
            result=self.value(dependency['name'],target_year)
            if result.value is None:
                return Value(None,result.reason)
            if other is None:
                return Value(None,'missing_year')
            if other['currency']!=row['currency']:
                return Value(None,'unsupported_currency')
            if other.get('reported_unit_scale')!=row.get('reported_unit_scale'):
                return Value(None,'incompatible_reported_scale')
            if 'extraction_not_ok' in other['quality_codes']:
                return Value(None,'extraction_not_ok')
            source=DEFINITIONS[dependency['name']]['source']
            if source in BALANCE and 'balance_mismatch' in other['quality_codes']:
                return Value(None,'balance_mismatch')
            if definition['annual'] and not annual(other):
                return Value(None,'invalid_period')
            values.append(result.value)
        op=definition['op']
        if op in ('growth','delta','scaled_change','mean','std'):
            years=sorted({year+x['offset'] for x in definition['inputs']})
            for a,b in zip(years,years[1:]):
                if b!=a+1 or self.selected[a]['period_end']+timedelta(days=1)!=self.selected[b]['period_start']:
                    return Value(None,'incompatible_periods')
        if op in ('ratio','growth','scaled_change'):
            denominator=values[-1]
            if denominator<=0:
                return Value(None,'nonpositive_denominator')
        if op=='ratio':
            return Value(values[0]/values[1])
        if op=='growth':
            return Value(values[0]/values[1]-1)
        if op=='delta':
            return Value(values[0]-values[1])
        if op=='scaled_change':
            return Value((values[0]-values[1])/values[2])
        if op=='log':
            return Value(values[0].ln()) if values[0]>0 else Value(None,'nonpositive_log_input')
        if op=='identity':
            return Value(values[0])
        if op=='mean':
            return Value(sum(values)/len(values))
        if op=='std':
            mean=sum(values)/len(values)
            return Value((sum((v-mean)**2 for v in values)/(len(values)-1)).sqrt())
        raise ValueError('Unknown operator')

    def row(self,year):
        values={name:self.value(name,year) for name in DEFINITIONS}
        return {k:v.value for k,v in values.items()},{k:v.reason for k,v in values.items() if v.reason}
