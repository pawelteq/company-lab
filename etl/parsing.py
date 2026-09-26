from datetime import date, datetime
from decimal import Decimal, InvalidOperation, localcontext
import re
import simplejson as json

PARSER_VERSION='compabase-staging-v1'
METRICS='''revenue_total revenue_net_sales_products revenue_change_inventories
operating_costs_total cost_amortization cost_materials_energy cost_external_services
cost_taxes_fees cost_wages cost_social_security_other profit_sales other_oper_income
other_oper_costs financial_income financial_costs profit_gross income_tax profit_net
total_assets ebit ebitda roa roe net_margin asset_turnover fixed_assets current_assets
short_term_receivables cash_and_equivalents inventories equity liabilities_and_provisions
long_term_liabilities short_term_liabilities ebitda_margin current_ratio cash_ratio
liabilities_to_total_assets cash_to_total_assets receivables_to_total_assets
liabilities_borrowings interest_expense'''.split()


def dumps(value):
    return json.dumps(value,use_decimal=True,ensure_ascii=False,allow_nan=False,separators=(',',':'))


def no_duplicate_keys(pairs):
    result={}
    for k,v in pairs:
        if k in result:
            raise ValueError('Duplicate JSON object key')
        result[k]=v
    return result


def loads(data):
    return json.loads(data,use_decimal=True,allow_nan=False,object_pairs_hook=no_duplicate_keys)


def krs_valid(value):
    return isinstance(value,str) and re.fullmatch(r'[0-9]{10}',value) is not None


def text_value(value):
    return None if value is None or str(value).strip() in ('','—','–','-') else str(value)


def decimal_value(value):
    if value is None or value=='':
        return None
    if isinstance(value,(bool,list,dict)):
        raise ValueError('Not a decimal scalar')
    try:
        result=Decimal(str(value))
    except InvalidOperation as e:
        raise ValueError('Invalid decimal') from e
    if not result.is_finite():
        raise ValueError('Non-finite decimal')
    return result


def stage_financial(record):
    issues=[]
    def issue(code,path,detail,severity='warning'):
        issues.append((code,path,detail,severity))
    def read_date(field):
        value=record.get(field)
        if not value:
            return None
        try:
            return date.fromisoformat(value)
        except (ValueError,TypeError):
            issue('invalid_date','/'+field,{'value':value},'error')
            return None
    original_start=read_date('sf_period_from')
    original_end=read_date('sf_period_to')
    resolved_start=read_date('period_from_resolved')
    resolved_end=read_date('period_to_resolved')
    start=resolved_start or original_start
    end=resolved_end or original_end
    if original_start and resolved_start and original_start!=resolved_start:
        issue('period_start_conflict','/period_from_resolved',{},'error')
    if original_end and resolved_end and original_end!=resolved_end:
        issue('period_end_conflict','/period_to_resolved',{},'error')
    duration=(end-start).days+1 if start and end else None
    if duration is not None and duration<=0:
        issue('invalid_period','/period_from_resolved',{'start':str(start),'end':str(end)},'error')
        start=None  # Invalid original and resolved dates remain untouched in raw.record.
    elif duration not in (365,366):
        issue('non_annual_period','/period_from_resolved',{'duration_days':duration})
    if not start or not end:
        issue('incomplete_period','/period_from_resolved',{},'error')
    if end and (end.month,end.day)!=(12,31):
        issue('non_calendar_year','/period_to_resolved',{})
    values={}
    for key in METRICS:
        try:
            values[key]=decimal_value(record.get(key))
        except ValueError:
            values[key]=None
            issue('invalid_number','/'+key,{},'error')
    with localcontext() as ctx:
        ctx.prec=50
        a,e,l=[values[k] for k in ['total_assets','equity','liabilities_and_provisions']]
        if None not in (a,e,l) and abs(a-e-l)>max(Decimal(1),abs(a)*Decimal('0.000001')):
            issue('balance_mismatch','/total_assets',{'difference':a-e-l},'error')
    for key in ['total_assets','cash_and_equivalents','liabilities_and_provisions','revenue_total']:
        if values[key] is not None and values[key]<0:
            issue('negative_value','/'+key,{'value':values[key]})
    lines=record.get('esf_statement_lines')
    profile=lines.get('statement_profile') if isinstance(lines,dict) else None
    profile=profile if isinstance(profile,dict) else {}
    try:
        scale=decimal_value(profile.get('metric_scale_to_pln'))
    except ValueError:
        scale=None
        issue('invalid_unit_scale','/esf_statement_lines/statement_profile/metric_scale_to_pln',{},'error')
    if scale is None:
        issue('unit_scale_unverified','/esf_statement_lines/statement_profile',{},'info')
    elif scale<=0:
        issue('invalid_unit_scale','/esf_statement_lines/statement_profile/metric_scale_to_pln',{},'error')
    if record.get('esf_extraction_status')!='ok':
        issue('extraction_not_ok','/esf_extraction_status',{'status':record.get('esf_extraction_status')})
    if record.get('esf_consistency_warnings'):
        issue('source_consistency_warning','/esf_consistency_warnings',{'warnings':record['esf_consistency_warnings']})
    scope=record.get('consolidation_scope')
    if scope not in ('standalone','consolidated'):
        scope='unknown'
        issue('unknown_consolidation_scope','/consolidation_scope',{},'error')
    if record.get('currency')!='PLN':
        issue('currency_requires_mapping','/currency',{'currency':record.get('currency')})
    extracted=None
    if record.get('extracted_at'):
        try:
            extracted=datetime.fromisoformat(record['extracted_at'])
            if extracted.tzinfo is None:
                raise ValueError('Timezone missing')
        except (ValueError,TypeError):
            extracted=None
            issue('invalid_extraction_time','/extracted_at',{})
    if end and extracted and end>extracted.date():
        issue('period_ends_after_extraction','/period_to_resolved',{},'error')
    return {
        'period_start':start,'period_end':end,'fiscal_year':end.year if end else None,
        'duration_days':duration,'period_resolution_method':'provider_resolved_unverified' if resolved_start or resolved_end else 'reported',
        'consolidation_scope':scope,'currency':record.get('currency'),'reported_unit_scale':scale,
        'extracted_at':extracted,'reported_metrics':values,'statement_profile':profile,
        'quality_codes':sorted({x[0] for x in issues}),
    },issues
