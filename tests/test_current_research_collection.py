import json

import pytest

from research import leverage_study
from scripts import publish_developer_questions, publish_leverage_study
from tests.test_local_profiles import build_sample


def test_research_and_publishers_use_served_sqlite_collection(tmp_path, monkeypatch):
    collection, _, _ = build_sample(tmp_path, monkeypatch)

    def forbidden_postgres():
        raise AssertionError('Research must use the collection served by the app')

    monkeypatch.setattr(leverage_study, 'connection', forbidden_postgres)
    monkeypatch.setattr(publish_leverage_study, 'connection', forbidden_postgres)
    monkeypatch.setattr(leverage_study, 'build', lambda rows: [r['krs'] for r in rows])
    loaded, source, profiles = leverage_study.load_current_panel()
    assert loaded == collection
    assert source == 'local_sqlite'
    assert profiles == ['0000000001', '0000000002']
    assert publish_leverage_study.latest_collection_id() == collection

    folder = tmp_path / 'study'
    folder.mkdir()
    (folder / 'results.json').write_text(json.dumps({'collection_id': 'old'}))
    for publisher in (publish_leverage_study, publish_developer_questions):
        with pytest.raises(ValueError, match='older collection'):
            publisher.publish(folder)
