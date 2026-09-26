"""Exploratory econometric pilot on the 41 high-priority current profiles.

This is deliberately separate from the published historical panel. Current
profile exports contain standalone financial histories; some observations are
still incomplete. The script records missingness and uses the same balance-
sheet definitions as the analytical feature engine instead of silently
substituting variables.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import json
import math
import platform
import tempfile
import warnings

import numpy as np
import pandas as pd
from linearmodels import PanelOLS, PooledOLS
from linearmodels.panel.utility import AbsorbingEffectError

from backend.app import connection
from etl.developer_screening import NAME_SIGNAL_RE, normalized
from etl.config import ROOT


DEFAULT_COLLECTION = None  # resolve the newest published profile collection
VERSION = "profile-pilot-econometrics-v1.1"


def _text(value) -> str:
    return str(value or "").strip()


def _number(value):
    try:
        return float(value) if value not in (None, "") else np.nan
    except (TypeError, ValueError):
        return np.nan


def _revenue(profile) -> float:
    return _number((profile.get("latest_standalone") or {}).get("revenue"))


def _is_active(profile) -> bool:
    return (_text(profile.get("provider_status")).lower() == "active"
            and not profile.get("is_currently_suspended"))


def select_41(collection: str = DEFAULT_COLLECTION) -> list[dict]:
    """Return the exact 41-company queue used in the UI investigation."""
    with connection() as conn:
        if collection is None:
            collection = conn.execute(
                "SELECT id FROM core.profile_collection ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()["id"]
        rows = conn.execute(
            """SELECT krs, name, profile
               FROM core.profile_screening
               WHERE collection_id=%s AND status='missing_summary'""",
            (collection,),
        ).fetchall()
    selected = []
    for row in rows:
        profile = row["profile"]
        if not isinstance(profile, dict):
            profile = json.loads(profile)
        primary = (profile.get("primary_pkd") or {}).get("code")
        if NAME_SIGNAL_RE.search(normalized(_text(row["name"]))):
            continue
        if primary not in ("41.10.Z", "41.20.Z"):
            continue
        if not profile.get("website") or not _is_active(profile):
            continue
        if not (_revenue(profile) > 250_000):
            continue
        profile = dict(profile)
        profile["_krs"] = row["krs"]
        profile["_name"] = row["name"]
        selected.append(profile)
    return sorted(selected, key=lambda item: item["_krs"])


def build_panel(profiles: list[dict]) -> pd.DataFrame:
    """Flatten annual standalone profile financials and derive pilot fields."""
    rows = []
    for profile in profiles:
        for financial in profile.get("financials") or []:
            if financial.get("consolidation_scope") != "standalone":
                continue
            period = _text(financial.get("period_to_resolved"))
            if len(period) < 4 or not period[:4].isdigit():
                continue
            rows.append({
                "company_id": profile["_krs"],
                "krs": profile["_krs"],
                "name": profile["_name"],
                "year": int(period[:4]),
                "revenue": _number(financial.get("revenue_total")),
                "profit_net": _number(financial.get("profit_net")),
                "total_assets": _number(financial.get("total_assets")),
                "equity": _number(financial.get("equity")),
                "cash": _number(financial.get("cash_and_equivalents")),
                "current_assets": _number(financial.get("current_assets")),
                "short_term_receivables": _number(financial.get("short_term_receivables")),
                "liabilities_and_provisions": _number(financial.get("liabilities_and_provisions")),
                "short_term_liabilities": _number(financial.get("short_term_liabilities")),
                "reported_current_ratio": _number(financial.get("current_ratio")),
                "reported_receivables_to_assets": _number(financial.get("receivables_to_total_assets")),
                "reported_liabilities_to_assets": _number(financial.get("liabilities_to_total_assets")),
            })
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    frame = (frame.drop_duplicates(["company_id", "year"])
             .sort_values(["company_id", "year"])
             .reset_index(drop=True))
    positive_assets = frame["total_assets"] > 0
    frame["log_assets"] = np.where(positive_assets,
                                    np.log(frame["total_assets"]), np.nan)
    # These are the same balance-sheet definitions used by analytics.features;
    # the underlying fields are retained from the provider profile export.
    frame["liabilities_to_assets"] = np.where(
        positive_assets & frame["liabilities_and_provisions"].notna(),
        frame["liabilities_and_provisions"] / frame["total_assets"],
        frame["reported_liabilities_to_assets"])
    frame["current_ratio"] = np.where(
        frame["reported_current_ratio"].notna(), frame["reported_current_ratio"],
        np.where(frame["short_term_liabilities"] > 0,
                 frame["current_assets"] / frame["short_term_liabilities"], np.nan))
    frame["roa"] = np.where(positive_assets,
                            frame["profit_net"] / frame["total_assets"], np.nan)
    frame["net_margin"] = np.where(frame["revenue"] != 0,
                                    frame["profit_net"] / frame["revenue"], np.nan)
    frame["receivables_to_assets"] = np.where(
        positive_assets & frame["short_term_receivables"].notna(),
        frame["short_term_receivables"] / frame["total_assets"],
        frame["reported_receivables_to_assets"])

    # Exact-calendar-year changes only; gaps do not become artificial one-year
    # observations.
    previous = frame[["company_id", "year", "revenue", "net_margin"]].copy()
    previous["year"] += 1
    previous = previous.rename(columns={"revenue": "revenue_previous",
                                        "net_margin": "margin_previous"})
    frame = frame.merge(previous, on=["company_id", "year"], how="left")
    frame["revenue_growth"] = np.where(
        frame["revenue_previous"] > 0,
        frame["revenue"] / frame["revenue_previous"] - 1,
        np.nan)
    frame["delta_margin"] = frame["net_margin"] - frame["margin_previous"]
    return frame


def _prepare(frame: pd.DataFrame, spec: dict, year_from=2017, year_to=2024):
    columns = [spec["exposure"], *spec["controls"]]
    panel = frame.set_index(["company_id", "year"]).sort_index()
    future = panel[[spec["outcome"]]].rename(columns={spec["outcome"]: "outcome"})
    future.index = pd.MultiIndex.from_arrays(
        [future.index.get_level_values("company_id"),
         future.index.get_level_values("year") - 1],
         names=panel.index.names)
    data = panel[columns].join(future, how="left")
    years = data.index.get_level_values("year")
    data = data[(years >= year_from) & (years <= year_to)]
    flow = {"all_panel_rows": int(len(data)),
            "outcome_available": int(data.outcome.notna().sum())}
    data = data.replace([np.inf, -np.inf], np.nan)
    flow["missing_by_variable"] = {c: int(data[c].isna().sum()) for c in data}
    flow["complete_cases"] = int(data.dropna().shape[0])
    data = data.dropna()
    while len(data):
        before = len(data)
        data = data[(data.groupby(level="company_id").outcome.transform("size") >= 2)
                    & (data.groupby(level="year").outcome.transform("size") >= 2)]
        if len(data) == before:
            break
    flow["after_singletons"] = int(len(data))
    flow["removed_singletons"] = flow["complete_cases"] - flow["after_singletons"]
    flow["companies"] = int(data.index.get_level_values("company_id").nunique()) if len(data) else 0
    flow["years"] = sorted(map(int, data.index.get_level_values("year").unique())) if len(data) else []
    return data, flow


def _fit(data: pd.DataFrame, spec: dict, model: str, variant: str):
    if len(data) < 30 or data.index.get_level_values(0).nunique() < 10:
        return {"status": "insufficient_data", "model": model, "variant": variant}
    work = data.copy()
    clipping = {}
    if variant == "winsor_01_99":
        for col in work:
            low, high = work[col].quantile([0.01, 0.99])
            clipping[col] = {"lower": float(low), "upper": float(high),
                             "affected": int(((work[col] < low) | (work[col] > high)).sum())}
            work[col] = work[col].clip(low, high)
    x = work.drop(columns="outcome")
    if spec.get("quadratic"):
        x = x.assign(**{spec["exposure"] + "_squared": x[spec["exposure"]] ** 2})
    x = x.assign(const=1.0)
    if model == "pooled_year_effects":
        years = pd.get_dummies(pd.Series(x.index.get_level_values("year"), index=x.index),
                               prefix="year", drop_first=True, dtype=float)
        x = pd.concat([x, years], axis=1)
    scales = np.sqrt((x * x).mean()).replace(0, 1)
    outcome_scale = float(np.sqrt((work.outcome * work.outcome).mean())) or 1.0
    normalized_x = x / scales
    normalized_y = work.outcome / outcome_scale
    try:
        estimator = (PanelOLS(normalized_y, normalized_x, entity_effects=True,
                              time_effects=True, check_rank=True, drop_absorbed=True)
                     if model == "firm_and_year_fe" else
                     PooledOLS(normalized_y, normalized_x, check_rank=True))
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            fitted = estimator.fit(cov_type="clustered", cluster_entity=True, debiased=True)
    except (ValueError, np.linalg.LinAlgError, ZeroDivisionError, AbsorbingEffectError) as exc:
        return {"status": "failed", "model": model, "variant": variant, "error": str(exc)}
    ci = fitted.conf_int(level=.95)
    finite = lambda value: float(value) if np.isfinite(value) else None
    coefficients = {}
    for name in fitted.params.index:
        coefficients[name] = {
            "coefficient": finite(fitted.params[name] * outcome_scale / scales[name]),
            "standard_error": finite(fitted.std_errors[name] * outcome_scale / scales[name]),
            "ci95_low": finite(ci.loc[name].iloc[0] * outcome_scale / scales[name]),
            "ci95_high": finite(ci.loc[name].iloc[1] * outcome_scale / scales[name]),
            "p_value": finite(fitted.pvalues[name]),
        }
    return {"status": "estimated", "model": model, "variant": variant,
            "n_observations": int(fitted.nobs),
            "n_companies": int(work.index.get_level_values(0).nunique()),
            "years": sorted(map(int, work.index.get_level_values(1).unique())),
            "coefficients": coefficients,
            "r_squared": finite(fitted.rsquared),
            "within_r_squared": finite(getattr(fitted, "rsquared_within", np.nan)),
            "covariance": "clustered_by_company",
            "effects": ["company", "year"] if model == "firm_and_year_fe" else ["year"],
            "warnings": [str(item.message) for item in captured],
            "clipping": clipping}


STUDIES = [
    {"id": "P01", "title": "Zadłużenie/aktywa a przyszły wzrost przychodów",
     "outcome": "revenue_growth", "exposure": "liabilities_to_assets",
     "controls": ["current_ratio", "roa", "log_assets"], "quadratic": False,
     "primary_term": "liabilities_to_assets"},
    {"id": "P02", "title": "Nieliniowość zadłużenia a przyszłe ROA",
     "outcome": "roa", "exposure": "liabilities_to_assets",
     "controls": ["current_ratio", "log_assets"], "quadratic": True,
     "primary_term": "liabilities_to_assets_squared"},
    {"id": "P03", "title": "Nieliniowość płynności a przyszła marża",
     "outcome": "net_margin", "exposure": "current_ratio",
     "controls": ["liabilities_to_assets", "log_assets"], "quadratic": True,
     "primary_term": "current_ratio_squared"},
    {"id": "P04", "title": "Należności/aktywa a przyszła zmiana marży",
     "outcome": "delta_margin", "exposure": "receivables_to_assets",
     "controls": ["liabilities_to_assets", "current_ratio", "log_assets"], "quadratic": False,
     "primary_term": "receivables_to_assets"},
]


def run(collection: str = DEFAULT_COLLECTION) -> dict:
    if collection is None:
        with connection() as conn:
            collection = conn.execute(
                "SELECT id FROM core.profile_collection ORDER BY created_at DESC, id DESC LIMIT 1"
            ).fetchone()["id"]
    profiles = select_41(collection)
    if len(profiles) != 41:
        raise ValueError(f"Expected the 41-company pilot queue, got {len(profiles)}")
    frame = build_panel(profiles)
    code_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    collection = str(collection)
    ident = hashlib.sha256((VERSION + collection + code_hash).encode()).hexdigest()[:16]
    final = ROOT / "data" / "research" / "profile_pilot" / ident
    final.parent.mkdir(parents=True, exist_ok=True)
    if final.exists() and (final / "results.json").exists():
        return json.loads((final / "results.json").read_text(encoding="utf-8"))
    folder = Path(tempfile.mkdtemp(prefix=".profile-pilot-", dir=final.parent))
    results = {
        "run_id": ident, "collection_id": collection, "version": VERSION,
        "selection": {"companies": len(profiles),
                      "rule": "missing summary, no name signal, primary PKD 41.10/41.20, active, website, latest revenue >250000 PLN",
                      "not_verified_developer": True},
        "runtime": {"python": platform.python_version(), "pandas": pd.__version__},
        "inference_class": "exploratory_conditional_association",
        "causal": False,
        "limitations": [
            "41 firm to próba przesiewowa, a nie losowa ani potwierdzona populacja deweloperów.",
            "Wskaźniki są liczone z pól bilansowych dostawcy (zobowiązania, aktywa obrotowe i należności); nie są to dane skonsolidowane z innym źródłem.",
            "Roczny wynik wymaga dokładnie kolejnego roku kalendarzowego; luki są pomijane.",
        ],
        "studies": [],
    }
    frame.to_parquet(folder / "profile_panel.parquet", index=False)
    selection = [{"krs": p["_krs"], "name": p["_name"], "website": p.get("website"),
                  "primary_pkd": (p.get("primary_pkd") or {}).get("code"),
                  "latest_revenue": _revenue(p),
                  "latest_period": (p.get("latest_standalone") or {}).get("period_end")}
                 for p in profiles]
    (folder / "selection.json").write_text(json.dumps(selection, ensure_ascii=False, indent=2), encoding="utf-8")
    for spec in STUDIES:
        sample, flow = _prepare(frame, spec)
        study = {"id": spec["id"], "title": spec["title"], "specification": spec,
                 "sample_flow": flow, "estimates": []}
        for variant in ("untrimmed", "winsor_01_99"):
            for model in ("pooled_year_effects", "firm_and_year_fe"):
                study["estimates"].append(_fit(sample, spec, model, variant))
        results["studies"].append(study)
    (folder / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    lines = ["# Pilotaż ekonometryczny — 41 firm", "", f"Run: `{ident}`", "",
             "To jest eksploracyjna analiza warunkowych zależności, nie dowód przyczynowości.", "",
             "## Próba", "", f"- Firmy: **{len(profiles)}**",
             f"- Obserwacje roczne: **{len(frame)}**",
             f"- Lata: **{int(frame.year.min())}–{int(frame.year.max())}**", "",
             "## Wyniki FE firmy + roku (wariant bez winsoryzacji)", "",
             "| Badanie | Obserwacje | Firmy | Główna zmienna | Współczynnik | p | R² within |",
             "|---|---:|---:|---|---:|---:|---:|"]
    for study in results["studies"]:
        estimate = next(item for item in study["estimates"]
                         if item["model"] == "firm_and_year_fe" and item["variant"] == "untrimmed")
        term = study["specification"]["primary_term"]
        coef = estimate.get("coefficients", {}).get(term, {})
        lines.append(f"| {study['id']} — {study['title']} | {estimate.get('n_observations', '—')} | "
                     f"{estimate.get('n_companies', '—')} | {term} | "
                     f"{coef.get('coefficient', '—')} | {coef.get('p_value', '—')} | "
                     f"{estimate.get('within_r_squared', '—')} |")
    lines += ["", "## Ograniczenia", "", *[f"- {item}" for item in results["limitations"]], ""]
    (folder / "report.md").write_text("\n".join(lines), encoding="utf-8")
    folder.rename(final)
    return results


if __name__ == "__main__":
    output = run()
    print(json.dumps({"run_id": output["run_id"],
                      "studies": [(s["id"], s["sample_flow"]) for s in output["studies"]]},
                     ensure_ascii=False, indent=2))
