"""Exploratory developer research stated as plain-language questions."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
from statsmodels.stats.multitest import multipletests

from etl.config import ROOT
from research.leverage_study import load_current_panel, estimate, shifted, SIGNIFICANCE_LEVEL, CONFIDENCE_LEVEL


PROTOCOL = {
    "version": "developer-questions-2-alpha-10",
    "significance_level": SIGNIFICANCE_LEVEL,
    "confidence_level": CONFIDENCE_LEVEL,
    "selection": "same transparent developer screen as leverage study: active, description candidate or explicit name signal, at least five usable annual PLN reports and latest revenue above PLN 250,000",
    "questions": "predeclared exploratory associations; company and year fixed effects, firm-clustered standard errors; no causal claims",
    "horizon": "one following full year except revenue growth, which is already defined from year t to t+1",
}


def stability(frame):
    work = frame.copy()
    work["ebit_margin"] = work.ebit / work.revenue_total.where(work.revenue_total > 0)
    firm = work.replace([np.inf, -np.inf], np.nan).groupby(level=0).agg(
        years=("roa", "count"),
        roa_volatility=("roa", "std"),
        margin_volatility=("ebit_margin", "std"),
        top_assets_q4=("top_assets_q4", "first"),
    )
    firm = firm[firm.years >= 5]
    result = {}
    for label, flag in [("największa 1/4", True), ("pozostałe 3/4", False)]:
        part = firm[firm.top_assets_q4 == flag]
        result[label] = {
            "companies": int(len(part)),
            "median_roa_volatility": float(part.roa_volatility.median()),
            "median_ebit_margin_volatility": float(part.margin_volatility.median()),
        }
    return result


def run():
    collection, data_source, (frame, selected, audit, exclusions, fields) = load_current_panel()

    frame["operating_roa"] = frame.ebit / frame.avg_total_assets.where(frame.avg_total_assets > 0)
    frame["receivables_assets"] = frame.short_term_receivables / frame.total_assets
    forward_revenue = shifted(frame[["revenue_total"]], 1).reindex(frame.index).revenue_total
    # A log change is less dominated by a single small-base year.  We retain
    # only established revenue observations on both sides of the year pair.
    frame["log_revenue_growth_next_year"] = (np.log(forward_revenue) - np.log(frame.revenue_total)).where(
        (forward_revenue > 250000) & (frame.revenue_total > 250000)
    )

    specs = [
        {
            "id": "inventory_revenue",
            "question": "Czy większe zapasy dziś poprzedzają szybszy wzrost przychodu w kolejnym roku?",
            "exposure": "inventory_assets", "outcome": "log_revenue_growth_next_year",
            "controls": ["log_assets", "cash_assets"], "outcome_at_t": True,
        },
        {
            "id": "inventory_margin",
            "question": "Czy większe zapasy dziś wiążą się z wyższą rentownością operacyjną aktywów w kolejnym roku?",
            "exposure": "inventory_assets", "outcome": "operating_roa",
            "controls": ["log_assets", "cash_assets"], "outcome_at_t": False,
        },
        {
            "id": "cash_roa",
            "question": "Czy większa gotówka dziś wiąże się z wyższym ROA w kolejnym roku?",
            "exposure": "cash_assets", "outcome": "roa",
            "controls": ["log_assets", "inventory_assets"], "outcome_at_t": False,
        },
        {
            "id": "receivables_roa",
            "question": "Czy większe należności dziś wiążą się z niższym ROA w kolejnym roku?",
            "exposure": "receivables_assets", "outcome": "roa",
            "controls": ["log_assets", "cash_assets", "inventory_assets"], "outcome_at_t": False,
        },
    ]
    results = []
    terms = []
    for spec in specs:
        for variant in ["raw", "winsor_01_99"]:
            model = estimate(
                frame, 1, spec["exposure"], outcome=spec["outcome"], variant=variant,
                controls=spec["controls"], outcome_at_t=spec["outcome_at_t"],
            )
            model.update(id=spec["id"], question=spec["question"])
            results.append(model)
            coefficient = model.get("coefficients", {}).get(spec["exposure"])
            if coefficient:
                terms.append(coefficient)
    if terms:
        for term, q in zip(terms, multipletests([term["p"] for term in terms], method="fdr_bh")[1]):
            term["q_bh"] = float(q)

    output = {
        "run_id": hashlib.sha256((collection + Path(__file__).read_text(encoding="utf-8")).encode()).hexdigest()[:16],
        "collection_id": collection,
        "data_source": data_source,
        "protocol": PROTOCOL,
        "audit": audit,
        "exclusions": exclusions,
        "questions": results,
        "stability": stability(frame),
        "years": sorted(map(int, frame.index.get_level_values("year").unique())),
        "limitations": [
            "To są zależności obserwacyjne, a nie dowód, że zmiana wskaźnika spowodowała późniejszy wynik.",
            "Zapasy mogą oznaczać etap projektu, a nie tylko lepszą lub gorszą decyzję firmy.",
            "Wynik, przychód i marża dewelopera bywają rozpoznawane nierównomiernie między latami.",
            "Wariant ograniczający skrajności jest kontrolą odporności; oba wyniki pokazujemy bez wybierania korzystniejszego.",
        ],
    }
    folder = ROOT / "data/research/developer_questions" / output["run_id"]
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "protocol.json").write_text(json.dumps(PROTOCOL, ensure_ascii=False, indent=2), encoding="utf-8")
    (folder / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    lines = ["# Pytania o cykl deweloperski", "", f"Próba: {audit['selected_companies']} firm, {audit['selected_company_years']} obserwacji.", ""]
    for result in results:
        c = result.get("coefficients", {}).get(result["exposure"])
        if c:
            lines.append(f"## {result['question']}")
            lines.append(f"{result['variant']}: {result['companies']} firm, {result['n']} obserwacji; współczynnik {c['value']:.5f}; {CONFIDENCE_LEVEL:.0%} CI [{c['lo']:.5f}; {c['hi']:.5f}]; p={c['p']:.4f}; q BH={c.get('q_bh', 1):.4f}.")
    lines += ["", "## Ograniczenia", *["- " + item for item in output["limitations"]], ""]
    (folder / "report.md").write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"folder": str(folder), "run_id": output["run_id"], "audit": audit}, ensure_ascii=False))
    return output


if __name__ == "__main__":
    run()
