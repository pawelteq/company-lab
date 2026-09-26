import json
import sqlite3
from contextlib import closing

from backend import local_profiles


def sample_profile(krs, name, status, revenue):
    return {
        "krs": krs,
        "name": name,
        "city": "Łódź",
        "region": "Łódzkie",
        "summary": f"{name} buduje mieszkania.",
        "primary_pkd": {"code": "41.10.Z", "description": "Realizacja projektów budowlanych"},
        "screening": {
            "status": status,
            "segment": "residential",
            "name_signal": "Development" in name,
            "reason": "Opis wskazuje działalność deweloperską.",
        },
        "financials": [{
            "period_to_resolved": "2024-12-31",
            "currency": "PLN",
            "revenue_total": revenue,
            "private_detail": "pozostaje tylko w pełnym profilu",
        }],
        "raw_profile": {"large": "source"},
    }


def build_sample(tmp_path, monkeypatch):
    collection = tmp_path / "11111111-1111-1111-1111-111111111111"
    collection.mkdir()
    profiles = [
        sample_profile("0000000001", "Łódź Development", "developer_candidate", "200,5"),
        sample_profile("0000000002", "Zwykła Firma", "missing_summary", None),
    ]
    (collection / "summary.json").write_text(json.dumps({
        "profiles": 2,
        "rule_version": "test-v1",
        "counts": {"developer_candidate": 1, "missing_summary": 1},
    }), encoding="utf-8")
    (collection / "screening.json").write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
    database = tmp_path / "profiles.sqlite3"
    result = local_profiles.build_database(collection, database)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(database))
    return collection.name, database, result


def test_build_search_sort_and_detail(tmp_path, monkeypatch):
    collection, database, result = build_sample(tmp_path, monkeypatch)
    assert result["profiles"] == 2
    page = local_profiles.catalog(
        collection, q="lodz", status="all", segment="all", sort="revenue",
        direction="desc", limit=25, offset=0,
    )
    assert page["total"] == 2
    assert page["items"][0]["krs"] == "0000000001"
    assert "financials" not in page["items"][0]
    assert page["items"][0]["financial_history"]["periods"] == 1

    detail = local_profiles.profile_detail(collection, "0000000001")
    assert detail["financials"][0]["private_detail"].startswith("pozostaje")
    assert detail["raw_profile"] == {"large": "source"}

    with sqlite3.connect(database) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_name_signal_and_export(tmp_path, monkeypatch):
    collection, database, _ = build_sample(tmp_path, monkeypatch)
    page = local_profiles.catalog(
        collection, q="", status="name_signal", segment="all", sort="krs",
        direction="asc", limit=25, offset=0,
    )
    assert page["total"] == 0
    exported = local_profiles.export_rows(
        collection, q="development", status="all", segment="all"
    )
    assert len(exported) == 1
    assert exported[0]["primary_pkd"] == "41.10.Z"


def test_verification_filter_and_rebuild_preserve_decisions(tmp_path, monkeypatch):
    collection, database, _ = build_sample(tmp_path, monkeypatch)
    with closing(sqlite3.connect(database)) as connection:
        connection.execute(
            """INSERT INTO company_verification
               (krs,collection_id,status,source,updated_at)
               VALUES (?,?,?,?,?)""",
            ("0000000001", collection, "confirmed", "user", "2026-09-26T12:00:00+00:00"),
        )
        connection.commit()

    confirmed = local_profiles.catalog(
        collection, q="", status="all", segment="all", verification="confirmed",
        sort="krs", direction="asc", limit=25, offset=0,
    )
    unverified = local_profiles.catalog(
        collection, q="", status="all", segment="all", verification="unverified",
        sort="krs", direction="asc", limit=25, offset=0,
    )
    assert confirmed["total"] == 1
    assert confirmed["items"][0]["verification_status"] == "confirmed"
    assert unverified["total"] == 1
    assert unverified["items"][0]["krs"] == "0000000002"

    local_profiles.build_database(tmp_path / collection, database)
    with closing(sqlite3.connect(database)) as connection:
        saved = connection.execute(
            "SELECT status,source FROM company_verification WHERE krs='0000000001'"
        ).fetchone()
    assert saved == ("confirmed", "user")
