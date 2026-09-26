"""Unit tests for research.credit_study module."""
import json
import numpy as np
import pandas as pd
import pytest

from research.credit_study import (
    calculate_yearly_cyclical_trends,
    estimate_panel_models,
    num,
)


def test_num_conversion():
    assert num("123.45") == 123.45
    assert num(100) == 100.0
    assert np.isnan(num("invalid"))
    assert np.isnan(num(None))


def test_yearly_cyclical_trends():
    """Test yearly trends calculation, boom/lean year detection, and debt subgroups."""
    data = [
        # 2021 (boom)
        {"company_id": "1", "year": 2021, "revenue": 1000000.0, "profit": 150000.0, "assets": 2000000.0, "debt": 500000.0, "equity": 500000.0, "ebit": 180000.0, "has_debt": True, "debt_assets": 0.25, "roa": 0.075, "roe": 0.30, "ebit_margin": 0.18, "net_margin": 0.15, "is_profitable": True},
        {"company_id": "2", "year": 2021, "revenue": 800000.0, "profit": 80000.0, "assets": 1500000.0, "debt": 0.0, "equity": 1000000.0, "ebit": 90000.0, "has_debt": False, "debt_assets": 0.0, "roa": 0.053, "roe": 0.08, "ebit_margin": 0.11, "net_margin": 0.10, "is_profitable": True},
        # 2022 (lean/shock)
        {"company_id": "1", "year": 2022, "revenue": 600000.0, "profit": -20000.0, "assets": 2000000.0, "debt": 600000.0, "equity": 480000.0, "ebit": 30000.0, "has_debt": True, "debt_assets": 0.30, "roa": -0.01, "roe": -0.04, "ebit_margin": 0.05, "net_margin": -0.03, "is_profitable": False},
        {"company_id": "2", "year": 2022, "revenue": 750000.0, "profit": 50000.0, "assets": 1500000.0, "debt": 0.0, "equity": 1050000.0, "ebit": 60000.0, "has_debt": False, "debt_assets": 0.0, "roa": 0.033, "roe": 0.048, "ebit_margin": 0.08, "net_margin": 0.067, "is_profitable": True},
    ]
    df = pd.DataFrame(data)
    trends = calculate_yearly_cyclical_trends(df, min_revenue=250000.0)

    assert 2021 in trends
    assert 2022 in trends
    assert trends[2021]["is_boom_year"] is True
    assert trends[2022]["is_lean_year"] is True
    assert trends[2021]["total_companies"] == 2
    assert trends[2022]["total_companies"] == 2

    # In 2021, indebted company ROE (0.30) > unindebted (0.08)
    assert trends[2021]["indebted_group"]["median_roe"] > trends[2021]["unindebted_group"]["median_roe"]


def test_estimate_panel_models_synthetic():
    """Test PanelOLS estimation on synthetic multi-firm, multi-year data."""
    records = []
    for i in range(30):
        for year in range(2018, 2024):
            debt_ratio = 0.10 + (i % 5) * 0.03 + (year - 2018) * 0.01
            log_assets = 14.0 + (i % 3) + (year - 2018) * 0.05
            is_boom = 1.0 if year in (2021, 2023) else 0.0
            roe = 0.10 + 0.15 * debt_ratio * is_boom - 0.05 * debt_ratio * (1 - is_boom) + np.random.normal(0, 0.01)
            roa = 0.04 - 0.02 * debt_ratio + np.random.normal(0, 0.005)
            records.append({
                "company_id": f"firm_{i}",
                "year": year,
                "debt_assets": debt_ratio,
                "roa": roa,
                "roe": roe,
                "log_assets": log_assets,
            })
    df = pd.DataFrame(records)
    models = estimate_panel_models(df)

    assert "model_future_roa" in models
    assert "model_leverage_boom" in models
    assert models["model_future_roa"]["status"] == "estimated"
    assert models["model_leverage_boom"]["status"] == "estimated"
    assert "coefficient" in models["model_future_roa"]
    assert "boom_interaction_coefficient" in models["model_leverage_boom"]
