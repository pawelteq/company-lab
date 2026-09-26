from copy import deepcopy
from pathlib import Path
import pytest
from etl.config import ROOT
from etl.parsing import loads
from etl.compabase_payloads import financial_candidates,profile,numeric_comparison,collection_requests


def test_real_reference_profile_preserves_pkd_versions_and_source():
    raw=loads((ROOT/'referencja/0000023958 (2).json').read_bytes())
    before=deepcopy(raw)
    parsed=profile(raw)
    assert parsed['krs']=='0000023958' and parsed['attributes']['nip']=='7120157618'
    codes={(a['code'],a['version']):a for a in parsed['activities']}
    assert codes[('41.10.Z','2007')]['is_primary'] is True
    assert codes[('41.20.Z','2007')]['is_primary'] is False
    assert parsed['developer_classification'] is None
    assert parsed['historical_validity_known'] is False
    assert raw==before


def test_real_financial_mirrors_not_double_counted_or_year_collapsed():
    raw=loads((ROOT/'referencja/0000023958 (2).json').read_bytes())
    all_rows=list(financial_candidates(raw));preferred=[r for r in all_rows if r.preferred_container]
    assert len(all_rows)==12 and len(preferred)==6
    assert sum(str(r.payload.get('period_to_resolved'))[:4]=='2020' for r in preferred)==2
    assert all(r.staging_payload()['krs']=='0000023958' for r in preferred)
    assert all(r.pointer.startswith('/financialsDetail/metrics/') for r in preferred)


def test_unknown_pkd_version_and_primary_are_not_inferred():
    raw={'company':{'registry_number':'0000023958','activities':[{'code_full':'68.12.A','is_primary':'true'}]}}
    a=profile(raw)['activities'][0]
    assert a['version'] is None and a['is_primary'] is None and not a['target_match']


def test_numeric_comparison_preserves_null_and_decimal_precision():
    result=numeric_comparison({'x':'0.03','y':None,'z':'1.00000000000000000001'},
                              {'x':0.03,'y':0,'z':'1.00000000000000000002'},['x','y','z'])
    assert result['equal']==['x'] and result['different']==['z'] and result['missing_one_side']==['y']


def test_collection_uses_four_separate_primary_code_queries():
    requests=collection_requests()
    assert len(requests)==4
    assert all(r['params']['primary_only']=='true' and 'status_active' not in r['params'] for r in requests)
    assert {r['expected_pkd_version'] for r in requests}=={'2007','2025'}


def test_conflicting_nested_identity_rejected():
    raw={'company':{'registry_number':'0000023958'},'financialsDetail':{'metrics':[{'krs':'0000994050'}]}}
    with pytest.raises(ValueError,match='conflicts'):
        list(financial_candidates(raw))


def test_source_catalog_does_not_expose_reference_payloads_or_keys():
    from backend.app import source_catalog
    result=source_catalog()
    assert result['provider']=='Compabase API'
    assert len(result['collection'])==4
    assert result['reference_audit']['financial_records']==6
    assert 'archive' not in str(result) and 'API_KEY' not in str(result)
