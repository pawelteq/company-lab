"""Read-only, reproducible audit of the supplied export. No third-party dependencies."""
import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path


def missing(v):
    return v is None or (isinstance(v, str) and not v.strip())


def number(v):
    if missing(v) or isinstance(v, bool):
        return None
    try:
        n = float(v)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


class Profile:
    def __init__(self):
        self.n = 0
        self.fields = defaultdict(Counter)

    def add(self, row):
        self.n += 1
        for k, v in row.items():
            f = self.fields[k]
            f['present'] += 1
            if missing(v):
                f['null_or_blank'] += 1
            else:
                f['nonempty'] += 1
                if isinstance(v, (list, dict)) and not v:
                    f['empty_container'] += 1
                n = number(v)
                if n is not None:
                    f['numeric'] += 1
                    f['zero'] += n == 0
                    f['negative'] += n < 0

    def result(self):
        return {'rows': self.n, 'fields': {k: dict(v, absent=self.n-v['present']) for k,v in sorted(self.fields.items())}}


def main(source, output):
    output.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in source.rglob('*') if p.is_file())
    inventory = []
    profiles = defaultdict(Profile)
    stats = defaultdict(Counter)
    ids = defaultdict(set)
    years = defaultdict(set)
    pairs = Counter()
    scoped_pairs = Counter()
    metric_ids = Counter()
    raw_values = {}
    duplicates = defaultdict(list)
    issues = []
    nested = defaultdict(Counter)
    scalar_checks = Counter()
    numeric_fields = 'revenue_total profit_net total_assets equity liabilities_and_provisions current_assets short_term_liabilities cash_and_equivalents short_term_receivables ebitda'.split()

    def walk(v, path, group):
        nested[group][path + ':' + type(v).__name__] += 1
        if isinstance(v, dict):
            for k, item in v.items():
                walk(item, path + '/' + k.replace('~','~0').replace('/','~1'), group)
        elif isinstance(v, list):
            for item in v:
                walk(item, path + '/*', group)

    for idx, p in enumerate(files):
        b = p.read_bytes()
        rel = p.relative_to(source).as_posix()
        inventory.append({'path':rel, 'bytes':len(b), 'sha256':hashlib.sha256(b).hexdigest()})
        if p.suffix != '.json':
            continue
        group = p.parent.name
        ids[group].add(p.stem)
        try:
            obj = json.loads(b)
        except (ValueError, UnicodeError) as exc:
            issues.append({'path':rel,'issue':'invalid_json','detail':str(exc)})
            continue
        if not isinstance(obj, dict):
            issues.append({'path':rel,'issue':'non_object_json'})
            continue
        profiles[group+'_root'].add(obj)
        walk(obj, '', group)
        if group == 'financials':
            rows = obj.get('metrics', [])
            stats[group]['empty_metrics'] += not bool(rows)
            stats['pagination'][json.dumps(obj.get('pagination'), sort_keys=True)] += 1
            stats[group]['documents_count'] += len(obj.get('documents') or [])
            for i, r in enumerate(rows):
                profiles['raw_metrics'].add(r)
                rid = r.get('id')
                metric_ids[rid] += 1
                key = str(r.get('krs') or p.stem)
                ids['metrics'].add(key)
                stats['metric_krs_mismatch'][str(r.get('krs') != p.stem)] += 1
                end = r.get('period_to_resolved') or r.get('sf_period_to')
                start = r.get('period_from_resolved') or r.get('sf_period_from')
                y = None
                try:
                    y = date.fromisoformat(end[:10]).year
                except (TypeError, ValueError):
                    stats['period']['invalid_or_missing_end'] += 1
                if y:
                    years[key].add(y)
                    pairs[key,y] += 1
                    scoped_pairs[key,y,r.get('consolidation_scope')] += 1
                    stats['years'][str(y)] += 1
                    duplicates[key,y].append({'path':rel,'pointer':f'/metrics/{i}','id':rid,'start':start,'end':end,'scope':r.get('consolidation_scope')})
                if start and end:
                    try:
                        days = (date.fromisoformat(end[:10])-date.fromisoformat(start[:10])).days+1
                        stats['period_days'][str(days)] += 1
                    except ValueError:
                        stats['period']['invalid_dates'] += 1
                else:
                    stats['period']['missing_start_or_end'] += 1
                for field in ['currency','consolidation_scope','document_type_ui','esf_extraction_status','has_esf_xml']:
                    stats[field][str(r.get(field))] += 1
                details = r.get('esf_statement_lines')
                if isinstance(details, dict):
                    stats['statement_profiles'][json.dumps(details.get('statement_profile'),sort_keys=True)] += 1
                if r.get('esf_consistency_warnings'):
                    stats['quality']['records_with_source_warnings'] += 1
                vals = {f:number(r.get(f)) for f in numeric_fields}
                a,e,l = (vals[f] for f in ['total_assets','equity','liabilities_and_provisions'])
                if all(v is not None for v in [a,e,l]):
                    scalar_checks['balance_checked'] += 1
                    scalar_checks['balance_mismatch'] += abs(a-e-l) > max(1, abs(a)*1e-6)
                for field, numerator, denominator in [('roa','profit_net','total_assets'),('roe','profit_net','equity'),('net_margin','profit_net','revenue_total'),('liabilities_to_total_assets','liabilities_and_provisions','total_assets'),('current_ratio','current_assets','short_term_liabilities'),('cash_ratio','cash_and_equivalents','short_term_liabilities')]:
                    v,n,d = number(r.get(field)),vals.get(numerator),vals.get(denominator)
                    if v is not None and n is not None and d not in (None,0):
                        q = n/d
                        scalar_checks[field+'_checked'] += 1
                        scalar_checks[field+'_fraction_match'] += math.isclose(v,q,rel_tol=1e-5,abs_tol=1e-7)
                        scalar_checks[field+'_percent_match'] += math.isclose(v,100*q,rel_tol=1e-5,abs_tol=1e-7)
                raw_values[rid] = tuple('' if missing(r.get(f)) else str(r[f]) for f in ['krs','sf_period_to']+numeric_fields)
        else:
            for field in ['people','related_companies']:
                values = obj.get(field) or []
                stats['connections'][field+'_count'] += len(values)
                stats['connections'][field+'_nonempty_companies'] += bool(values)
                for item in values:
                    profiles[field].add(item)
                    rels = item.get('relationships') or []
                    seen = set()
                    for relation in rels:
                        profiles['relationships'].add(relation)
                        stats['relationship_kinds'][str(relation.get('kind'))] += 1
                        s = json.dumps(relation,sort_keys=True)
                        stats['connections']['repeated_relationships_within_entity'] += s in seen
                        seen.add(s)
            graph = obj.get('graph') or {}
            for field in ['nodes','edges']:
                stats['graph'][field] += len(graph.get(field) or [])
                for item in graph.get(field) or []:
                    profiles['graph_'+field].add(item)
        if (idx+1)%2000 == 0:
            print(f'JSON scanned: {idx+1}/{len(files)}',flush=True)

    csv.field_size_limit(100_000_000)
    for p in sorted(source.glob('*.csv')):
        name = p.stem
        with p.open(encoding='utf-8-sig',newline='') as f:
            reader = csv.DictReader(f)
            for r in reader:
                profiles[name].add(r)
                ids[name].add(r.get('krs'))
                if name == 'progress':
                    stats['progress_status'][r.get('status')] += 1
                if name == 'firmy':
                    for field in ['voivodeship','revenue_year','revenue_window']:
                        stats['company_'+field][r.get(field)] += 1
                if name == 'firmy_finanse':
                    rid = r.get('id')
                    stats['csv_reconciliation']['rows'] += 1
                    stats['csv_reconciliation']['id_missing_in_raw'] += rid not in raw_values
                    if rid in raw_values:
                        actual = tuple(r.get(f) or '' for f in ['krs','sf_period_to']+numeric_fields)
                        expected = raw_values[rid]
                        for j,(x,y) in enumerate(zip(actual,expected)):
                            same = x==y or (j>=2 and number(x) is not None and number(y) is not None and math.isclose(number(x),number(y),rel_tol=1e-12,abs_tol=0.0051))
                            if not same:
                                stats['csv_value_mismatches'][(['krs','sf_period_to']+numeric_fields)[j]] += 1
    stats['panel']['unique_company_year'] = len(pairs)
    stats['panel']['duplicate_company_year_groups'] = sum(v>1 for v in pairs.values())
    stats['panel']['excess_company_year_records'] = sum(v-1 for v in pairs.values())
    stats['panel']['duplicate_scoped_company_year_groups'] = sum(v>1 for v in scoped_pairs.values())
    stats['panel']['duplicate_metric_id_groups'] = sum(v>1 for v in metric_ids.values())
    for threshold,label in [(1,'full'),(3,'3plus'),(5,'5plus'),(7,'long')]:
        selected = {k:v for k,v in years.items() if len(v)>=threshold}
        stats['panel']['companies_'+label] = len(selected)
        stats['panel']['observations_'+label] = sum(map(len,selected.values()))
    for ys in years.values():
        stats['history_length'][str(len(ys))] += 1
        stats['panel']['companies_with_calendar_gaps'] += len(ys) != max(ys)-min(ys)+1
        for lag in [1,2,3]:
            stats['calendar_pairs'][str(lag)] += sum(y-lag in ys for y in ys)
    ids = {k:{x for x in v if not missing(x)} for k,v in ids.items()}
    sets = {k:len(v) for k,v in ids.items()}
    differences = {f'{a}_without_{b}':sorted(ids[a]-ids[b]) for a,b in [('firmy','financials'),('financials','firmy'),('firmy','connections'),('firmy','metrics'),('metrics','firmy_finanse'),('firmy_finanse','metrics')]}
    result = {'generated_at':datetime.now(timezone.utc).isoformat(), 'source':str(source.resolve()), 'files':len(files),'bytes':sum(x['bytes'] for x in inventory),'counts':sets,'stats':dict(stats),'profiles':{k:v.result() for k,v in profiles.items()},'scalar_checks':scalar_checks,'set_differences':differences,'issues':issues}
    (output/'summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'source_manifest.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
    (output/'nested_field_inventory.json').write_text(json.dumps(nested,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'duplicate_company_years.json').write_text(json.dumps([dict(krs=k[0],year=k[1],records=v) for k,v in duplicates.items() if len(v)>1],indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ['files','bytes','counts','scalar_checks']},indent=2))
    print(json.dumps({k:stats[k] for k in ['panel','years','period','history_length','csv_reconciliation','csv_value_mismatches','connections']},indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,default=Path('firmy_b'))
    parser.add_argument('--output',type=Path,default=Path('data/audit'))
    args = parser.parse_args()
    if args.output.resolve() == args.source.resolve() or args.source.resolve() in args.output.resolve().parents:
        parser.error('Output must be outside the source directory')
    main(args.source,args.output)
