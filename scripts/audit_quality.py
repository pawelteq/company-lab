"""Additional semantic diagnostics; all findings refer to original files and pointers."""
import csv
import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

from audit_data import number


def main():
    root = Path('firmy_b')
    counts = Counter()
    examples = defaultdict(list)
    year_companies = defaultdict(set)
    field_years = defaultdict(Counter)
    categories = defaultdict(Counter)
    company_ids = Counter()
    unique_people = set()
    nips = set()

    def flag(code, p, i, detail):
        counts[code] += 1
        if len(examples[code]) < 20:
            examples[code].append({'path':p.as_posix(),'pointer':f'/metrics/{i}','detail':detail})

    with (root/'firmy.csv').open(encoding='utf-8-sig',newline='') as f:
        for i,r in enumerate(csv.DictReader(f),start=2):
            company_ids[r['krs']] += 1
            for k,v in r.items():
                if v.strip() in ['—','–','-','N/A','null','None']:
                    counts['company_placeholder_'+k] += 1
            if not r['krs']:
                examples['company_missing_krs'].append({'path':'firmy_b/firmy.csv','csv_row':i,'record':r})
    counts['company_duplicate_nonblank_krs'] = sum(v>1 for k,v in company_ids.items() if k)
    for p in sorted((root/'raw'/'connections').glob('*.json')):
        obj = json.loads(p.read_bytes())
        counts['connection_website_populated'] += bool(obj.get('website'))
        for person in obj.get('people') or []:
            if person.get('person_id'):
                unique_people.add(person['person_id'])
        for r in obj.get('related_companies') or []:
            categories['related_relationship_kind'][str(r.get('relationship_kind'))] += 1
            if r.get('registry_number') and r.get('nip'):
                nips.add((r['registry_number'],r['nip']))
            h = number(r.get('holding_percent'))
            counts['related_holding_percent_outside_range'] += h is not None and not 0 <= h <= 100
    counts['distinct_person_provider_ids'] = len(unique_people)
    counts['krs_nip_pairs_in_related_companies'] = len(nips)
    counts['cohort_companies_with_nip_evidence_in_related'] = len({k for k,n in nips if k in company_ids})
    for p in sorted((root/'raw'/'financials').glob('*.json')):
        obj = json.loads(p.read_bytes())
        for i,r in enumerate(obj['metrics']):
            start = date.fromisoformat((r.get('period_from_resolved') or r['sf_period_from'])[:10])
            end = date.fromisoformat((r.get('period_to_resolved') or r['sf_period_to'])[:10])
            year_companies[end.year].add(p.stem)
            days = (end-start).days+1
            for field in ['revenue_total','profit_net','total_assets','equity','current_ratio','short_term_receivables','cash_and_equivalents']:
                field_years[str(end.year)][field+'_missing'] += number(r.get(field)) is None
            if days not in (365,366):
                flag('non_365_366_day_period',p,i,{'start':str(start),'end':str(end),'days':days})
            if days<=0:
                flag('non_positive_period',p,i,{'start':str(start),'end':str(end)})
            if days>550:
                flag('period_over_550_days',p,i,{'days':days})
            if (end.month,end.day)!=(12,31):
                flag('non_december_year_end',p,i,{'end':str(end)})
            if end>date(2026,9,11):
                flag('future_period_end_at_audit',p,i,{'end':str(end)})
            if r.get('extracted_at') and end>date.fromisoformat(r['extracted_at'][:10]):
                flag('period_ends_after_extraction',p,i,{'end':str(end),'extracted_at':r['extracted_at']})
            if r.get('sf_period_to') != r.get('period_to_resolved'):
                flag('period_end_disagreement',p,i,{'original':r.get('sf_period_to'),'resolved':r.get('period_to_resolved')})
            lines = r.get('esf_statement_lines') or {}
            profile = lines.get('statement_profile') or {}
            categories['bilans_form'][str(profile.get('bilans_form'))] += 1
            categories['unit_scale'][str(profile.get('metric_scale_to_pln'))] += 1
            categories['extracted_year'][str(r.get('extracted_at',''))[:4]] += 1
            if r.get('esf_consistency_warnings'):
                for w in r['esf_consistency_warnings']:
                    categories['warning_types'][json.dumps(w,sort_keys=True,ensure_ascii=False)[:300]] += 1
            a,e,l = [number(r.get(k)) for k in ['total_assets','equity','liabilities_and_provisions']]
            if None not in [a,e,l] and abs(a-e-l)>max(1,abs(a)*1e-6):
                flag('balance_mismatch',p,i,{'assets':a,'equity':e,'liabilities':l,'difference':a-e-l,'profile':profile})
                categories['balance_mismatch_profile'][str(profile.get('bilans_form'))] += 1
            for field in ['total_assets','cash_and_equivalents','liabilities_and_provisions','revenue_total']:
                v = number(r.get(field))
                if v is not None and v<0:
                    flag('negative_'+field,p,i,{'value':v})
    result = {'as_of':'2026-09-11','counts':counts,'unique_company_year_by_year':{str(y):len(v) for y,v in sorted(year_companies.items())},'missing_by_year':field_years,'categories':categories,'examples':examples}
    Path('data/audit/quality_details.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'counts':counts,'unique_company_year_by_year':result['unique_company_year_by_year'],'categories':{k:v for k,v in categories.items() if k!='warning_types'}},indent=2))


if __name__=='__main__':
    main()
