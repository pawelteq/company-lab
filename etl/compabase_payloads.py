"""Lossless adapters: return source pointers and copies; never edit source envelopes."""
from dataclasses import dataclass
from decimal import Decimal
import re
from etl.parsing import decimal_value, krs_valid

TARGET_PKD = (
    {'code':'41.10.Z','version':'2007'},
    {'code':'41.20.Z','version':'2007'},
    {'code':'68.11.Z','version':'2025'},
    {'code':'68.12.A','version':'2025'},
)


@dataclass(frozen=True)
class FinancialCandidate:
    pointer: str
    payload: dict
    preferred_container: bool
    context_krs: str | None

    def staging_payload(self):
        result=dict(self.payload)
        if not result.get('krs') and self.context_krs:
            result['krs']=self.context_krs
        return result


def kind(payload):
    if not isinstance(payload,dict):
        return 'unsupported'
    if isinstance(payload.get('company'),dict):
        return 'company_profile'
    if isinstance(payload.get('metrics'),list):
        return 'financial_statements'
    if isinstance(payload.get('graph'),dict):
        return 'connections'
    if isinstance(payload.get('roles'),list) and isinstance(payload.get('ownership'),list):
        return 'structure_people'
    if isinstance(payload.get('data'),list) and isinstance(payload.get('pagination'),dict):
        return 'company_search_page'
    return 'unsupported'


def company_krs(payload):
    company=payload.get('company') if isinstance(payload.get('company'),dict) else payload
    value=company.get('registry_number') or company.get('krs')
    return value if krs_valid(value) else None


def financial_candidates(payload):
    """Expose all representations, mark only one container preferred; no year dedup."""
    context=company_krs(payload)
    containers=[]
    if isinstance(payload.get('metrics'),list):
        containers.append(('/metrics',payload['metrics']))
    detail=payload.get('financialsDetail')
    if isinstance(detail,dict) and isinstance(detail.get('metrics'),list):
        containers.append(('/financialsDetail/metrics',detail['metrics']))
    financials=payload.get('financials')
    grouped=financials.get('byYear') if isinstance(financials,dict) else None
    preferred=containers[0][0] if containers else None
    if isinstance(grouped,dict):
        if preferred is None:
            preferred='/financials/byYear'
        for year,rows in sorted(grouped.items()):
            if not isinstance(rows,list):
                raise ValueError('financials.byYear must contain arrays; source retained for review')
            escaped=str(year).replace('~','~0').replace('/','~1')
            containers.append(('/financials/byYear/'+escaped,rows))
    for prefix,rows in containers:
        for index,row in enumerate(rows):
            if not isinstance(row,dict):
                raise ValueError('Financial record must be an object')
            own=row.get('krs')
            if own and context and own!=context:
                raise ValueError('Financial KRS conflicts with envelope identity')
            yield FinancialCandidate(f'{prefix}/{index}',row,prefix==preferred or (preferred=='/financials/byYear' and prefix.startswith(preferred+'/')),context)


def profile(payload):
    if kind(payload)!='company_profile':
        return None
    company=payload['company']
    krs=company_krs(payload)
    if not krs:
        raise ValueError('Profile requires a valid 10-digit KRS')
    names=['company_name','company_name_display','nip','regon','full_address','city','region','country','legal_form','extracted_at','state_date']
    result={'krs':krs,'source_pointer':'/company','attributes':{n:company.get(n) for n in names},'activities':[],
            'historical_validity_known':False,'developer_classification':None}
    # activities is the complete array; primary/secondary arrays are preserved mirrors.
    activities=company.get('activities')
    if activities is not None and not isinstance(activities,list):
        raise ValueError('company.activities must be an array')
    for index,a in enumerate(activities or []):
        if not isinstance(a,dict):
            raise ValueError('Activity must be an object')
        code=a.get('code_full');version=a.get('pkd_source');primary=a.get('is_primary')
        issues=[]
        if not isinstance(code,str) or not re.fullmatch(r'\d{2}\.\d{2}\.[A-Z]',code):
            issues.append('invalid_pkd_format')
        if version not in ('2007','2025'):
            issues.append('unknown_pkd_version')
        if not isinstance(primary,bool):
            issues.append('unknown_primary_status')
        result['activities'].append({'code':code,'version':version if version in ('2007','2025') else None,
            'reported_version':version,'is_primary':primary if isinstance(primary,bool) else None,
            'description':a.get('description'),'source_pointer':f'/company/activities/{index}',
            'issues':issues,'target_match':any(code==t['code'] and version==t['version'] for t in TARGET_PKD)})
    return result


def numeric_comparison(left,right,fields):
    result={'equal':[],'different':[],'missing_one_side':[],'invalid':[]}
    for field in fields:
        a=left.get(field);b=right.get(field)
        if a is None and b is None:
            continue
        if a is None or b is None:
            result['missing_one_side'].append(field)
            continue
        try:
            x,y=decimal_value(a),decimal_value(b)
        except ValueError:
            result['invalid'].append(field)
            continue
        result['equal' if x==y else 'different'].append(field)
    return result


def collection_requests():
    # One query per code, OR-union locally by KRS. Do not filter on revenue/status.
    return [{'method':'GET','url':'https://compabase.com/api/v1/companies/export',
             'params':{'pkd':t['code'],'primary_only':'true','limit':500},
             'expected_pkd_version':t['version']} for t in TARGET_PKD]
