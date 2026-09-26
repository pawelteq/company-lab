"""Single-base-year cross-sectional analysis for the 41-company pilot.

Unlike the profile panel pilot, this module never shifts an outcome to a
future year and never includes firm or time fixed effects. It compares firms
within one calendar year, with HC3 heteroskedasticity-robust standard errors.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import platform
import tempfile

import numpy as np
import pandas as pd
import statsmodels.api as sm
from scipy.stats import spearmanr

from etl.config import ROOT
from research.profile_pilot import DEFAULT_COLLECTION, build_panel, select_41


VERSION = "profile-cross-section-v1"
BASE_YEAR = 2024


def _fit(frame: pd.DataFrame, outcome: str, predictors: list[str], *, winsor=False):
    cols = [outcome, *predictors]
    data = frame.dropna(subset=cols).copy()
    if winsor:
        for col in cols:
            low, high = data[col].quantile([0.01, 0.99])
            data[col] = data[col].clip(low, high)
    if len(data) < len(predictors) + 8:
        return {"status": "insufficient_data", "n": int(len(data))}
    y = data[outcome]
    x = sm.add_constant(data[predictors], has_constant="add")
    fitted = sm.OLS(y, x).fit(cov_type="HC3")
    coefficients = {}
    for name in fitted.params.index:
        coefficients[name] = {
            "coefficient": float(fitted.params[name]),
            "standard_error": float(fitted.bse[name]),
            "ci95_low": float(fitted.conf_int().loc[name, 0]),
            "ci95_high": float(fitted.conf_int().loc[name, 1]),
            "p_value": float(fitted.pvalues[name]),
        }
    return {"status": "estimated", "n": int(fitted.nobs),
            "r_squared": float(fitted.rsquared),
            "adjusted_r_squared": float(fitted.rsquared_adj),
            "f_p_value": float(fitted.f_pvalue),
            "covariance": "HC3", "coefficients": coefficients}


def run(collection: str | None = DEFAULT_COLLECTION, base_year: int = BASE_YEAR) -> dict:
    profiles = select_41(collection)
    if len(profiles) != 41:
        raise ValueError(f"Expected the 41-company pilot queue, got {len(profiles)}")
    # select_41 resolves the latest collection when collection is None. Read it
    # back for a stable result identifier and provenance.
    if collection is None:
        from backend.app import connection
        with connection() as conn:
            collection = str(conn.execute(
                "SELECT id FROM core.profile_collection ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()["id"])
    else:
        collection = str(collection)
    panel = build_panel(profiles)
    cross = panel[panel["year"] == base_year].copy()
    cross["log_revenue"] = np.log(cross["revenue"].where(cross["revenue"] > 0))
    cross["log_assets"] = np.log(cross["total_assets"].where(cross["total_assets"] > 0))

    predictors = ["liabilities_to_assets", "current_ratio", "log_assets"]
    outcomes = [
        ("log_revenue", "log przychodów"),
        ("roa", "ROA"),
        ("net_margin", "marża netto"),
    ]
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ident = hashlib.sha256((VERSION + collection + str(base_year) + code_hash).encode()).hexdigest()[:16]
    final = ROOT / "data" / "research" / "profile_cross_section" / ident
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists() and (final / "results.json").exists():
        return json.loads((final / "results.json").read_text(encoding="utf-8"))
    folder = Path(tempfile.mkdtemp(prefix=".profile-cross-section-", dir=final.parent))
    results = {
        "run_id": ident, "collection_id": collection, "version": VERSION,
        "selection": {"pilot_companies": 41, "base_year": base_year,
                      "firms_with_base_year": int(cross["krs"].nunique()),
                      "rule": "the same 41-company screening queue; no future-year shift",
                      "not_verified_developer": True},
        "runtime": {"python": platform.python_version(), "pandas": pd.__version__,
                    "statsmodels": sm.__version__},
        "inference_class": "exploratory_cross_sectional_association",
        "causal": False,
        "predictors": predictors,
        "studies": [],
        "limitations": [
            "Jeden rok pokazuje różnice między firmami, ale nie rozstrzyga kierunku przyczynowości.",
            "Próba 41 firm jest selektywna i nie jest potwierdzoną populacją deweloperów.",
            "Braki wskaźników płynności i należności zmniejszają liczbę obserwacji modelowych.",
            "Wyniki są wrażliwe na wielkość i obserwacje skrajne; HC3 koryguje błędy standardowe, nie usuwa obserwacji.",
        ],
    }
    for outcome, label in outcomes:
        study = {"id": "C" + str(len(results["studies"]) + 1).zfill(2),
                 "title": f"Różnice firm w {label} w roku {base_year}",
                 "outcome": outcome, "predictors": predictors,
                 "ols_hc3": _fit(cross, outcome, predictors),
                 "ols_hc3_winsor_01_99": _fit(cross, outcome, predictors, winsor=True)}
        results["studies"].append(study)
    corr_cols = ["liabilities_to_assets", "current_ratio", "log_assets", "log_revenue", "roa", "net_margin"]
    correlations = {}
    for left in corr_cols:
        correlations[left] = {}
        for right in corr_cols:
            data = cross[[left, right]].dropna()
            if len(data) >= 5:
                if left == right:
                    rho, p = 1.0, 0.0
                else:
                    rho, p = spearmanr(data[left], data[right])
                correlations[left][right] = {"rho": float(rho), "p_value": float(p), "n": int(len(data))}
    results["spearman"] = correlations
    cross.to_parquet(folder / "base_year_2024.parquet", index=False)
    (folder / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")

    lines = [f"# Analiza przekrojowa — rok {base_year}", "", f"Run: `{ident}`", "",
             "Porównanie firm w jednym roku bazowym; bez trendów, lagów i efektów firm/lat.", "",
             "## Pokrycie", "", f"- Kolejka: **41 firm**", f"- Dane w {base_year}: **{cross['krs'].nunique()} firm**",
             f"- Obserwacje kompletne dla modelu: **{results['studies'][0]['ols_hc3'].get('n', '—')}**", "",
             "## OLS przekrojowy z odpornymi błędami HC3", "",
             "| Model | N | R² | p testu łącznego | p głównej zmiennej: zadłużenie/aktywa |",
             "|---|---:|---:|---:|---:|"]
    for study in results["studies"]:
        fit = study["ols_hc3"]
        debt = fit.get("coefficients", {}).get("liabilities_to_assets", {})
        lines.append(f"| {study['id']} — {study['title']} | {fit.get('n', '—')} | "
                     f"{fit.get('r_squared', '—')} | {fit.get('f_p_value', '—')} | "
                     f"{debt.get('p_value', '—')} |")
    lines += ["", "## Ograniczenia", "", *[f"- {item}" for item in results["limitations"]], ""]
    (folder / "report.md").write_text("\n".join(lines), encoding="utf-8")
    folder.rename(final)
    return results


if __name__ == "__main__":
    output = run()
    print(json.dumps({"run_id": output["run_id"], "base_year": output["selection"]["base_year"],
                      "studies": [(s["id"], s["ols_hc3"].get("n")) for s in output["studies"]]},
                     ensure_ascii=False, indent=2))
