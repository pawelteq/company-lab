"""Combine archived responses conservatively; conflicting values stay in the profile."""
from copy import deepcopy


def merge_fields(base, extra, path, report):
    if base is None:
        if extra is not None:
            report['added'].append(path)
        return deepcopy(extra)
    if isinstance(base, dict) and isinstance(extra, dict):
        result = deepcopy(base)
        for key, value in extra.items():
            pointer = path + '/' + key.replace('~', '~0').replace('/', '~1')
            if key not in base:
                result[key] = deepcopy(value)
                report['added'].append(pointer)
            else:
                result[key] = merge_fields(base[key], value, pointer, report)
        return result
    if base != extra and extra is not None:
        # Arrays without a stable identity are never zipped or appended by position.
        report['conflicts'].append(path)
    return deepcopy(base)


def merge_bundle(payload, supplements, krs):
    result = deepcopy(payload)
    reports = {}
    for source, extra in supplements.items():
        if not isinstance(extra, dict):
            raise ValueError(f'{source}: expected an object')
        own = extra.get('registry_number') or extra.get('krs')
        if own and own != krs:
            raise ValueError(f'{source}: KRS mismatch')
        report = {'added': [], 'conflicts': []}
        reports[source] = report
        if source == 'financials':
            if not isinstance(extra.get('metrics'), list):
                raise ValueError('financials: missing metrics')
            base = result.get('financialsDetail') or {}
            records = deepcopy(base.get('metrics') or [])
            for record in records + extra['metrics']:
                if not isinstance(record, dict) or (record.get('krs') and record['krs'] != krs):
                    raise ValueError('financials: invalid record or KRS mismatch')
            def identity(record):
                # Record IDs preserve different statements for the same year.
                return record.get('id')
            for source_records in (records, extra['metrics']):
                ids = [identity(record) for record in source_records if identity(record)]
                if len(ids) != len(set(ids)):
                    raise ValueError('financials: duplicate record ID')
            index = {identity(record): i for i, record in enumerate(records) if identity(record)}
            for i, record in enumerate(extra['metrics']):
                rid = identity(record)
                if rid and rid in index:
                    pos = index[rid]
                    records[pos] = merge_fields(records[pos], record, f'/financialsDetail/metrics/{pos}', report)
                elif record not in records:
                    # Without an ID, an ambiguous same-period record is not silently duplicated.
                    period = record.get('period_to_resolved') or record.get('sf_period_to')
                    ambiguous = [r for r in records if (r.get('period_to_resolved') or r.get('sf_period_to')) == period
                                 and r.get('currency') == record.get('currency')
                                 and r.get('consolidation_scope') == record.get('consolidation_scope')
                                 and (not rid or not identity(r))]
                    if ambiguous:
                        raise ValueError('financials: ambiguous record without ID')
                    report['added'].append(f'/financialsDetail/metrics/{len(records)}')
                    records.append(deepcopy(record))
            result['financialsDetail'] = merge_fields(base, {k: v for k, v in extra.items() if k != 'metrics'}, '/financialsDetail', report)
            result['financialsDetail']['metrics'] = records
            # A warning from either response must survive a metadata disagreement.
            if (extra.get('pagination') or {}).get('hasMore'):
                result['financialsDetail'].setdefault('pagination', {})['hasMore'] = True
        elif source == 'connections':
            if not isinstance(extra.get('graph'), dict):
                raise ValueError('connections: missing graph')
            result['connections'] = merge_fields(result.get('connections'), extra, '/connections', report)
        elif source == 'structure-people':
            if not isinstance(extra.get('roles'), list) or not isinstance(extra.get('ownership'), list):
                raise ValueError('structure-people: missing roles or ownership')
            for key, value in extra.items():
                # The profile contains display-ready names; retain these on disagreement.
                if result.get(key) == [] and value:
                    result[key] = deepcopy(value)
                    report['added'].append('/' + key)
                else:
                    result[key] = merge_fields(result.get(key), value, '/' + key, report)
    return result, reports
