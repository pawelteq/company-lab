from copy import deepcopy
import pytest
from etl.profile_bundle import merge_bundle


def test_financial_merge_preserves_conflicts_and_distinct_same_year_records():
    base = {'financialsDetail': {'metrics': [{'id': 'a', 'revenue_total': 100, 'ebit': None}]}}
    original = deepcopy(base)
    merged, report = merge_bundle(base, {'financials': {'metrics': [
        {'id': 'a', 'revenue_total': 120, 'ebit': 5, 'cost_selling': 8},
        {'id': 'b', 'revenue_total': 200},
    ]}}, '0000000001')
    assert base == original
    assert merged['financialsDetail']['metrics'] == [
        {'id': 'a', 'revenue_total': 100, 'ebit': 5, 'cost_selling': 8},
        {'id': 'b', 'revenue_total': 200},
    ]
    assert report['financials']['conflicts'] == ['/financialsDetail/metrics/0/revenue_total']


def test_reordered_records_merge_by_id_not_position():
    base = {'financialsDetail': {'metrics': [{'id': 'b'}, {'id': 'a'}]}}
    merged, _ = merge_bundle(base, {'financials': {'metrics': [{'id': 'a', 'ebit': 1}, {'id': 'b', 'ebit': 2}]}}, '0000000001')
    assert [r['ebit'] for r in merged['financialsDetail']['metrics']] == [2, 1]


@pytest.mark.parametrize('extra', [
    {'metrics': [{'id': 'a', 'krs': '0000000002'}]},
    {'metrics': [{'id': 'a'}, {'id': 'a'}]},
    {'metrics': 'broken'},
])
def test_invalid_financial_response_is_rejected(extra):
    with pytest.raises(ValueError):
        merge_bundle({}, {'financials': extra}, '0000000001')


def test_structure_conflict_is_retained_and_reported_without_positional_merge():
    base = {'roles': [{'party': {'name': 'A'}, 'role_name': 'Director'}], 'ownership': []}
    extra = {'roles': [{'party': {'name': {'en': 'A'}}, 'role_name': 'Director'}], 'ownership': [{'owner': {'name': 'B'}}]}
    merged, report = merge_bundle(base, {'structure-people': extra}, '0000000001')
    assert merged['roles'] == base['roles']
    assert merged['ownership'] == extra['ownership']
    assert report['structure-people']['conflicts'] == ['/roles']


def test_connections_identity_and_pagination_warning():
    with pytest.raises(ValueError, match='KRS mismatch'):
        merge_bundle({}, {'connections': {'registry_number': '0000000002', 'graph': {}}}, '0000000001')
    merged, _ = merge_bundle({'financialsDetail': {'metrics': [], 'pagination': {'hasMore': False}}},
                             {'financials': {'metrics': [], 'pagination': {'hasMore': True}}}, '0000000001')
    assert merged['financialsDetail']['pagination']['hasMore'] is True


def test_ambiguous_unidentified_financial_record_is_rejected():
    base = {'financialsDetail': {'metrics': [{'sf_period_to': '2025-12-31', 'revenue_total': 1}]}}
    with pytest.raises(ValueError, match='ambiguous'):
        merge_bundle(base, {'financials': {'metrics': [{'sf_period_to': '2025-12-31', 'revenue_total': 2}]}}, '0000000001')
