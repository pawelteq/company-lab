import json

import pytest

from backend import financial_map, local_profiles


COLLECTION = "22222222-2222-2222-2222-222222222222"


def _profile(krs: str, revenue_2025, profit_2025, assets_2025, equity_2025):
    return {
        "krs": krs,
        "name": f"Firma {krs}",
        "city": "Łódź",
        "region": "Łódzkie",
        "summary": "Realizacja projektów budowlanych.",
        "primary_pkd": {"code": "41.10.Z", "description": "Realizacja projektów budowlanych"},
        "activities": [{"code": "41.10.Z", "is_primary": True, "target_match": True}],
        "screening": {"status": "developer_candidate", "segment": "residential"},
        "financials": [
            {
                "period_from_resolved": "2024-01-01", "period_to_resolved": "2024-12-31", "currency": "PLN",
                "revenue_total": 100, "profit_net": 10, "ebit": 12, "total_assets": 200, "equity": 100,
            },
            {
                "period_from_resolved": "2025-01-01", "period_to_resolved": "2025-12-31", "currency": "PLN",
                "revenue_total": revenue_2025, "profit_net": profit_2025, "ebit": profit_2025,
                "total_assets": assets_2025, "equity": equity_2025,
            },
        ],
    }


@pytest.fixture()
def map_database(tmp_path, monkeypatch):
    collection = tmp_path / COLLECTION
    collection.mkdir()
    profiles = [
        _profile("0000000001", 0, 0, 100, 100),
        _profile("0000000002", 200, 20, 200, 100),
        _profile("0000000003", 10_000, None, 400, 200),
    ]
    (collection / "summary.json").write_text(json.dumps({"profiles": 3, "rule_version": "test"}), encoding="utf-8")
    (collection / "screening.json").write_text(json.dumps(profiles, ensure_ascii=False), encoding="utf-8")
    source = tmp_path / "profiles.sqlite3"
    target = tmp_path / "financial_map.sqlite3"
    local_profiles.build_database(collection, source)
    financial_map.build_index(source, target)
    monkeypatch.setenv("LOCAL_SQLITE_PATH", str(source))
    monkeypatch.setenv("FINANCIAL_MAP_SQLITE_PATH", str(target))
    return target


def test_map_keeps_zero_excludes_null_and_calculates_change(map_database):
    revenue = financial_map.map_data(
        COLLECTION, level="voivodeship", year=2025, metric_id="revenue_total",
        aggregation="sum", min_companies=1,
    )["regions"][0]
    assert revenue["value"] == 10_200
    assert revenue["metric_company_count"] == 3

    profit = financial_map.map_data(
        COLLECTION, level="voivodeship", year=2025, metric_id="profit_net",
        aggregation="mean", min_companies=1,
    )["regions"][0]
    assert profit["value"] == 10
    assert profit["metric_company_count"] == 2

    change = financial_map.map_data(
        COLLECTION, level="voivodeship", year=2025, metric_id="revenue_total",
        aggregation="sum", min_companies=1, view="change", compare_year=2024,
    )["regions"][0]
    assert change["value"] == pytest.approx(3300)


def test_ratio_filters_minimum_and_fixed_comparison(map_database):
    roa = financial_map.map_data(
        COLLECTION, level="voivodeship", year=2025, metric_id="roa",
        aggregation="regional_ratio", pkd="41.10.Z", min_companies=2,
    )["regions"][0]
    assert roa["value"] == pytest.approx(20 / 300 * 100)
    assert roa["insufficient_data"] is False

    hidden = financial_map.map_data(
        COLLECTION, level="voivodeship", year=2025, metric_id="profit_net",
        aggregation="median", min_companies=3,
    )["regions"][0]
    assert hidden["value"] is None
    assert hidden["insufficient_data"] is True
    assert hidden["raw_value"] is None
    assert hidden["median"] is None

    suppressed = financial_map.region_detail(
        COLLECTION, "10", level="voivodeship", year=2025, metric_id="profit_net",
        aggregation="median", min_companies=3,
    )
    assert suppressed["suppressed"] is True
    assert suppressed["top_revenue"] == []
    assert suppressed["top_metric"] == []

    comparison = financial_map.compare_regions(
        COLLECTION, ["10"], level="voivodeship", year=2025, min_companies=2,
    )
    row = comparison["regions"][0]
    assert row["region_name"] == "Łódzkie"
    assert row["metrics"]["revenue_total"]["value"] == 10_200
    assert row["metrics"]["ebit_margin"]["value"] is None
    assert row["metrics"]["ebit_margin"]["company_count"] == 1
