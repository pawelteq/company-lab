from decimal import Decimal

import pytest

from etl.parsing import dumps
from scripts.import_profiles import read_bundles, write_artifact


def test_streamed_artifact_preserves_exact_json_and_immutable_publication(tmp_path):
    target = tmp_path / 'screening.json'
    data = [{'name': 'Łódź', 'amount': Decimal('12.3400')}, {'financials': []}]
    write_artifact(target, data)
    assert target.read_bytes() == dumps(data).encode('utf-8')
    write_artifact(target, data)
    with pytest.raises(ValueError, match='refusing overwrite'):
        write_artifact(target, [{'different': True}])
    assert target.read_bytes() == dumps(data).encode('utf-8')


def test_failed_serialization_does_not_publish_partial_file(tmp_path):
    target = tmp_path / 'screening.json'
    with pytest.raises(TypeError):
        write_artifact(target, [{'valid': True}, object()])
    assert not target.exists()
    assert list(tmp_path.iterdir()) == []


def test_parallel_bundle_reads_preserve_order_and_source_bytes(tmp_path):
    source = tmp_path / 'raw' / 'profiles'
    source.mkdir(parents=True)
    financials = source.parent / 'financials'
    financials.mkdir()
    for index in range(40):
        (source / f'{index:010}.json').write_bytes(b'{"profile":true}')
    (financials / '0000000003.json').write_bytes(b'{"financials":[]}')
    files = sorted(source.glob('*.json'))
    rows = list(read_bundles(files, source, tmp_path / 'archive', ('financials',)))
    assert [row[0] for row in rows] == files
    assert rows[3][1]['financials'] == b'{"financials":[]}'
    assert list(rows[3][2]) == ['profiles', 'financials']
    assert list(rows[4][2]) == ['profiles']
