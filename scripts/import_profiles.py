"""Publish a reproducible current-profile collection without replacing older panels."""
import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import gc
import hashlib
import json
import os
import tempfile
from pathlib import Path

import psycopg

from etl.compabase_payloads import profile, financial_candidates
from etl.config import ROOT, database_url
from etl.developer_screening import VERSION, LABELS, classify, extract_summary
from etl.ingest import uid, js
from etl.parsing import loads, dumps, decimal_value
from etl.storage import archive, digest_file
from etl.profile_bundle import merge_bundle

def _decimal(record, key):
    """Read a numeric source value without changing the provider's value."""
    try:
        return decimal_value(record.get(key))
    except (TypeError, ValueError):
        return None


def enrich_financial_record(payload):
    """Keep the complete provider record and add auditable derived metrics.

    Compabase already sends EBITDA and a number of ratios for many statements.
    We preserve those reported values and calculate a second, explicitly named
    value whenever the source fields are sufficient.  This prevents a proxy from
    silently replacing an official value while still making missing metrics
    usable in the profile and later econometric work.
    """
    record = dict(payload)
    calculated = {}

    def put(key, value, formula, inputs):
        if value is None:
            return
        record[f'calculated_{key}'] = value
        record[f'calculated_{key}_formula'] = formula
        record[f'calculated_{key}_inputs'] = inputs
        if record.get(key) is not None:
            source = _decimal(record, key)
            if source is not None:
                record[f'calculated_{key}_difference'] = value - source
        calculated[key] = {'value': value, 'formula': formula, 'inputs': inputs,
                           'matches_provider': record.get(key) is None or record.get(f'calculated_{key}_difference') == 0}

    ebit = _decimal(record, 'ebit')
    amort = _decimal(record, 'cost_amortization')
    calculated_ebit = None

    sales_profit = _decimal(record, 'profit_sales')
    other_income = _decimal(record, 'other_oper_income')
    other_cost = _decimal(record, 'other_oper_costs')
    if sales_profit is not None and other_income is not None and other_cost is not None:
        calculated_ebit = sales_profit + other_income - other_cost
        put('ebit', calculated_ebit,
            'zysk ze sprzedaży + pozostałe przychody operacyjne − pozostałe koszty operacyjne',
            ['profit_sales', 'other_oper_income', 'other_oper_costs'])

    gross = _decimal(record, 'profit_gross')
    tax = _decimal(record, 'income_tax')
    if gross is not None and tax is not None:
        put('profit_net', gross - tax, 'zysk brutto − podatek dochodowy', ['profit_gross', 'income_tax'])
    if ebit is None and calculated_ebit is None and gross is not None:
        financial_income_source = _decimal(record, 'financial_income')
        financial_costs_source = _decimal(record, 'financial_costs')
        if financial_income_source is not None and financial_costs_source is not None:
            calculated_ebit = gross - financial_income_source + financial_costs_source
            put('ebit', calculated_ebit, 'zysk brutto − przychody finansowe + koszty finansowe',
                ['profit_gross', 'financial_income', 'financial_costs'])

    ebit_for_ebitda = ebit if ebit is not None else calculated_ebit
    if ebit_for_ebitda is not None and amort is not None:
        put('ebitda', ebit_for_ebitda + amort, 'EBIT + amortyzacja', ['ebit', 'cost_amortization'])

    revenue = _decimal(record, 'revenue_total')
    assets = _decimal(record, 'total_assets')
    equity = _decimal(record, 'equity')
    current_assets = _decimal(record, 'current_assets')
    current_liabilities = _decimal(record, 'short_term_liabilities')
    cash = _decimal(record, 'cash_and_equivalents')
    receivables = _decimal(record, 'short_term_receivables')
    liabilities = _decimal(record, 'liabilities_and_provisions')
    borrowings = _decimal(record, 'liabilities_borrowings')
    net_profit = _decimal(record, 'profit_net')
    ebitda = ebit_for_ebitda + amort if ebit_for_ebitda is not None and amort is not None else _decimal(record, 'ebitda')
    if revenue not in (None, 0):
        gross_profit = _decimal(record, 'profit_gross')
        operating_costs = _decimal(record, 'operating_costs_total')
        financial_costs = _decimal(record, 'financial_costs')
        if gross_profit is not None:
            put('gross_margin', gross_profit / revenue * 100, 'zysk brutto / przychody razem × 100', ['profit_gross', 'revenue_total'])
        if operating_costs is not None:
            put('operating_cost_ratio', operating_costs / revenue * 100, 'koszty działalności operacyjnej / przychody razem × 100', ['operating_costs_total', 'revenue_total'])
        if financial_costs is not None:
            put('financial_cost_ratio', financial_costs / revenue * 100, 'koszty finansowe / przychody razem × 100', ['financial_costs', 'revenue_total'])
        if net_profit is not None:
            put('net_margin', net_profit / revenue * 100, 'zysk netto / przychody razem × 100', ['profit_net', 'revenue_total'])
        if ebit is not None:
            put('ebit_margin', ebit / revenue * 100, 'EBIT / przychody razem × 100', ['ebit', 'revenue_total'])
        if ebitda is not None:
            put('ebitda_margin', ebitda / revenue * 100, 'EBITDA / przychody razem × 100', ['ebitda', 'revenue_total'])
        put('asset_turnover', revenue / assets if assets not in (None, 0) else None,
            'przychody razem / aktywa razem', ['revenue_total', 'total_assets'])
    if assets not in (None, 0) and net_profit is not None:
        put('roa', net_profit / assets * 100, 'zysk netto / aktywa razem × 100', ['profit_net', 'total_assets'])
    if equity not in (None, 0) and net_profit is not None:
        put('roe', net_profit / equity * 100, 'zysk netto / kapitał własny × 100', ['profit_net', 'equity'])
    if current_liabilities not in (None, 0):
        if current_assets is not None:
            put('current_ratio', current_assets / current_liabilities, 'aktywa obrotowe / zobowiązania krótkoterminowe', ['current_assets', 'short_term_liabilities'])
        if cash is not None:
            put('cash_ratio', cash / current_liabilities, 'środki pieniężne / zobowiązania krótkoterminowe', ['cash_and_equivalents', 'short_term_liabilities'])
    if assets not in (None, 0):
        if liabilities is not None:
            put('liabilities_to_total_assets', liabilities / assets * 100, 'zobowiązania i rezerwy / aktywa razem × 100', ['liabilities_and_provisions', 'total_assets'])
        if cash is not None:
            put('cash_to_total_assets', cash / assets * 100, 'środki pieniężne / aktywa razem × 100', ['cash_and_equivalents', 'total_assets'])
        if receivables is not None:
            put('receivables_to_total_assets', receivables / assets * 100, 'należności krótkoterminowe / aktywa razem × 100', ['short_term_receivables', 'total_assets'])
    if equity not in (None, 0) and liabilities is not None:
        put('debt_to_equity', liabilities / equity * 100, 'zobowiązania i rezerwy / kapitał własny × 100', ['liabilities_and_provisions', 'equity'])
    if current_assets is not None and current_liabilities is not None:
        put('working_capital', current_assets - current_liabilities, 'aktywa obrotowe − zobowiązania krótkoterminowe', ['current_assets', 'short_term_liabilities'])
    if borrowings is not None and cash is not None:
        put('net_debt', borrowings - cash, 'kredyty i pożyczki − środki pieniężne', ['liabilities_borrowings', 'cash_and_equivalents'])
    if calculated:
        record['calculated_metrics'] = calculated
    return record


def public_profile(payload, file_krs, sha):
    parsed = profile(payload)
    if not parsed or parsed['krs'] != file_krs:
        raise ValueError('Profile identity does not match filename')
    company = payload['company']
    summary, pointer = extract_summary(payload)
    name = company.get('company_name_display') or company.get('company_name')
    screening = classify(name, summary, file_krs)
    details = payload.get('details') or {}
    contacts = details.get('contacts') or {}
    website = contacts.get('website') or company.get('website')
    financials = []
    issues = []
    try:
        for candidate in financial_candidates(payload):
            if candidate.preferred_container:
                # Do not project onto a short allow-list: the financial endpoint
                # contains detailed P&L, balance-sheet, currency conversions and
                # extraction metadata needed for the user's deeper analysis.
                financials.append(enrich_financial_record(candidate.payload) |
                                  {'source_pointer': candidate.pointer})
    except ValueError:
        financials = []
        issues.append('Finanse wymagają sprawdzenia: sprzeczna identyfikacja lub nieprawidłowy kontener.')
    financials.sort(key=lambda r: str(r.get('period_to_resolved') or r.get('sf_period_to') or ''), reverse=True)
    latest_standalone = next((r for r in financials if r.get('consolidation_scope') == 'standalone'), None)
    primary = next((a for a in parsed['activities'] if a.get('is_primary') is True), None)
    if (payload.get('financialsDetail') or {}).get('pagination', {}).get('hasMore'):
        issues.append('Dostawca wskazuje kolejne strony sprawozdań; historia może być niepełna.')
    # Keep the provider's complete profile envelope in the published row. The
    # UI renders the important sections and offers a raw JSON disclosure for any
    # fields not yet assigned a dedicated card.
    company_info = dict(company)
    raw_profile = {key: value for key, value in payload.items()
                   if key not in {'company', 'financials', 'financialsDetail', 'connections'}}
    return {
        'krs': file_krs, 'name': name, 'city': company.get('city'), 'region': company.get('region'),
        'website': website,
        'provider_status': details.get('operational_status') or ('suspended' if details.get('is_currently_suspended') else None),
        'is_currently_suspended': details.get('is_currently_suspended'),
        'primary_pkd': primary,
        'latest_standalone': ({'period_end': latest_standalone.get('period_to_resolved') or latest_standalone.get('sf_period_to'),
                              'currency': latest_standalone.get('currency'), 'revenue': latest_standalone.get('revenue_total')}
                             if latest_standalone else None),
        'summary': summary, 'summary_pointer': pointer, 'source_sha256': sha,
        'provider_updated_at': details.get('profile_updated_at') or company.get('extracted_at'),
        'activities': parsed['activities'], 'screening': screening,
        'company_info': company_info,
        'profile_details': details,
        'related_companies': payload.get('connections', {}).get('related_companies', []) if isinstance(payload.get('connections'), dict) else [],
        'graph': payload.get('connections', {}).get('graph', {}) if isinstance(payload.get('connections'), dict) else {},
        'roles': payload.get('roles') or [], 'ownership': payload.get('ownership') or [],
        'ownership_family_insight': payload.get('ownershipFamilyInsight'),
        'similar_companies': payload.get('similarCompanies') or [],
        'subsidiary_companies': payload.get('subsidiaryCompanies') or [],
        'change_history': payload.get('changeHistory') or [],
        'statistics': payload.get('statistics'), 'insights_by_year': payload.get('insightsByYear') or {},
        'seo_metric_summaries_by_year': payload.get('seoMetricSummariesByYear') or {},
        'faq': payload.get('faq') or [], 'pkd_rankings': payload.get('pkdRankings') or [],
        'primary_pkd_description': payload.get('primaryPkdDescription'),
        'connections': payload.get('connections'), 'raw_profile': raw_profile,
        'financials': financials, 'financial_notes': issues,
        'source': 'Compabase API · opis dostawcy',
    }


def write_artifact(target, value):
    """Serialize one profile at a time and publish only complete immutable files."""
    descriptor, name = tempfile.mkstemp(prefix='.profile-', dir=target.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8', newline='') as stream:
            if isinstance(value, list):
                stream.write('[')
                for index, item in enumerate(value):
                    if index:
                        stream.write(',')
                    stream.write(dumps(item))
                    if (index + 1) % 1000 == 0:
                        print(f'{target.name}: saved {index + 1}/{len(value)}', flush=True)
                stream.write(']')
            else:
                stream.write(dumps(value))
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, target)
        except FileExistsError:
            if digest_file(target) != digest_file(temporary):
                raise ValueError('Existing artifact does not match; refusing overwrite')
    finally:
        temporary.unlink(missing_ok=True)


def read_bundles(files, source, store, kinds):
    """Overlap disk reads with a bounded batch; retain deterministic file order."""
    def read_one(path):
        contents, sources = {}, {}
        for kind in ('profiles', *kinds):
            location = path if kind == 'profiles' else source.parent / kind / path.name
            if not location.exists():
                continue
            content = location.read_bytes()
            sha = hashlib.sha256(content).hexdigest()
            archive(location, store, sha, len(content))
            contents[kind] = content
            sources[kind] = {'file': kind + '/' + path.name, 'sha256': sha, 'bytes': len(content)}
        return path, contents, sources

    with ThreadPoolExecutor(max_workers=4) as executor:
        for offset in range(0, len(files), 32):
            yield from executor.map(read_one, files[offset:offset + 32])


def run(source, *, publish_postgres=False):
    source = source.resolve()
    if (source / 'raw' / 'profiles').is_dir():
        source = source / 'raw' / 'profiles'
    elif (source / 'profiles').is_dir():
        source = source / 'profiles'
    files = sorted(source.glob('*.json'))
    if not files:
        raise ValueError('No profile JSON files found')
    rows, manifest, rejected, merge_reports = [], [], [], []
    kinds = ('financials', 'connections', 'structure-people')
    names = {path.name for path in files}
    for kind in kinds:
        orphans = {path.name for path in (source.parent / kind).glob('*.json')} - names
        if orphans:
            raise ValueError(f'{kind}: {len(orphans)} files without a base profile; nothing published')
    store = ROOT / 'data/raw/profile_objects'
    for position, (path, contents, sources) in enumerate(read_bundles(files, source, store, kinds), 1):
        sha = sources['profiles']['sha256']
        manifest.extend(sources.values())
        try:
            payload = loads(contents['profiles'])
            supplements = {kind: loads(content) for kind, content in contents.items() if kind != 'profiles'}
            merged, report = merge_bundle(payload, supplements, path.stem)
            row = public_profile(merged, path.stem, sha)
            row['source_files'] = sources
            row['source_merge'] = {'policy': 'profile_values_preserved_fill_missing_v1', 'reports': report}
            # Financial source_pointer addresses the assembled envelope, not a single raw response.
            for record in row['financials']:
                record['source_container'] = 'assembled_profile'
                record['source_files'] = {k: sources[k] for k in ('profiles', 'financials') if k in sources}
            conflicts = sum(len(item['conflicts']) for item in report.values())
            if report.get('financials', {}).get('conflicts'):
                row['financial_notes'].append('Wykryto rozbieżności między odpowiedziami dostawcy. Zachowano wartości profilu; szczegóły zapisano w raporcie importu.')
            rows.append(row)
            merge_reports.append({'krs': path.stem, 'sources': sources, 'reports': report, 'conflicts': conflicts})
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            rejected.append({'file': path.name, 'reason': str(exc), 'sha256': sha})
        if position % 250 == 0:
            print(f'Prepared {position}/{len(files)} profiles', flush=True)
    if rejected:
        # Never switch the user's current collection to a silently incomplete batch.
        rejected_path = ROOT / '.local' / 'profile-import-rejected.json'
        rejected_path.parent.mkdir(exist_ok=True)
        rejected_path.write_text(dumps(rejected), encoding='utf-8')
        raise ValueError(f'{len(rejected)} invalid bundles; nothing published. See {rejected_path}')
    if not rows:
        raise ValueError('No valid profiles; nothing published')
    # An identical brand description on several KRS is not firm-specific evidence.
    descriptions = Counter(r['summary'] for r in rows if r['summary'])
    for row in rows:
        if row['summary'] and descriptions[row['summary']] > 1:
            row['screening']['flags'].append('Identyczny opis występuje przy kilku KRS; sprawdź spółkę i grupę.')
            if row['screening']['status'] == 'developer_candidate':
                row['screening'].update(status='review', reason='Wspólny opis kilku spółek wymaga potwierdzenia roli konkretnego KRS.')
    counts = Counter(r['screening']['status'] for r in rows)
    method_hash = hashlib.sha256((ROOT / 'etl/developer_screening.py').read_bytes() + Path(__file__).read_bytes() +
                                (ROOT / 'etl/compabase_payloads.py').read_bytes() +
                                (ROOT / 'etl/profile_bundle.py').read_bytes()).hexdigest()
    fingerprint = hashlib.sha256(dumps({'manifest': manifest, 'method': method_hash}).encode()).hexdigest()
    collection = uid('profiles', fingerprint)
    overview = {'profiles': len(rows), 'files': len(files), 'rejected': len(rejected),
                'source_files': len(manifest),
                'supplement_files': {kind: sum(kind in item['sources'] for item in merge_reports) for kind in kinds},
                'bundles_with_conflicts': sum(item['conflicts'] > 0 for item in merge_reports),
                'with_summary': sum(bool(r['summary']) for r in rows),
                'counts': {status: counts[status] for status in LABELS},
                'name_signal_missing_summary': sum(r['screening']['status'] == 'missing_summary' and r['screening']['name_signal'] for r in rows),
                'selected_with_financials': sum(r['screening']['status'] == 'developer_candidate' and bool(r['financials']) for r in rows),
                'labels': LABELS, 'rule_version': VERSION, 'research_ready': False,
                'note': 'Automatyczny przesiew opisów dostawcy. Kwalifikacja nie jest niezależnym potwierdzeniem działalności.'}
    report_dir = ROOT / 'data/profiles' / str(collection)
    report_dir.mkdir(parents=True, exist_ok=True)
    # Files are version-addressed; no previously published collection is replaced.
    for filename, value in [('manifest.json', {'files': manifest, 'rejected': rejected, 'method_hash': method_hash}),
                            ('summary.json', overview), ('merge_report.json', merge_reports), ('screening.json', rows)]:
        target = report_dir / filename
        write_artifact(target, value)
    if publish_postgres:
        with psycopg.connect(database_url()) as conn:
            existing = conn.execute('SELECT id FROM core.profile_collection WHERE fingerprint=%s', (fingerprint,)).fetchone()
            if not existing:
                conn.execute('INSERT INTO core.profile_collection(id,fingerprint,rule_version,summary) VALUES (%s,%s,%s,%s)',
                             (collection, fingerprint, VERSION, js(overview)))
                with conn.cursor().copy('COPY core.profile_screening(collection_id,krs,name,city,region,status,profile) FROM STDIN') as cp:
                    for row in rows:
                        cp.write_row((collection, row['krs'], row['name'], row['city'], row['region'], row['screening']['status'], js(row)))

    # The serving database is built from the immutable published artifact.
    # Release the in-memory envelopes first; a large collection can occupy
    # several gigabytes before compression.
    rows.clear()
    merge_reports.clear()
    gc.collect()
    from backend.local_profiles import build_database
    sqlite_result = build_database(report_dir)
    print(json.dumps({'collection_id': str(collection), **overview, 'sqlite': sqlite_result}, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--source', type=Path, default=ROOT / 'firmy_b/raw/profiles')
    parser.add_argument('--postgres', action='store_true',
                        help='Dodatkowo opublikuj zbiór w historycznej bazie PostgreSQL')
    args = parser.parse_args()
    run(args.source, publish_postgres=args.postgres)
