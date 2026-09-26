"""Background task definitions for RQ (Redis Queue).

Each function here is designed to run in a separate worker process.  Tasks
report progress via ``job.meta`` so the API can relay it to the frontend.
"""
from __future__ import annotations

import csv
import io
import json
import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def _update_progress(message: str, percent: int | None = None) -> None:
    """Write progress into the current RQ job's meta dict."""
    try:
        from rq import get_current_job

        job = get_current_job()
        if job is not None:
            job.meta["progress"] = message
            if percent is not None:
                job.meta["percent"] = percent
            job.save_meta()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Export CSV
# ---------------------------------------------------------------------------

def task_export_csv(collection: str, filters: dict) -> dict:
    """Generate a CSV export file in a temporary directory and return its path.

    The result dict contains ``path`` (absolute path to the CSV) and ``rows``
    (number of exported rows).
    """
    _update_progress("Rozpoczynam eksport…", 0)

    from backend.local_profiles import (
        connect,
        filter_clauses,
    )

    clauses, params = filter_clauses(collection, **filters)

    with connect() as conn:
        if not conn.execute(
            "SELECT 1 FROM profile_collection WHERE id=?", (collection,)
        ).fetchone():
            raise KeyError(collection)
        rows = conn.execute(
            """SELECT krs,name,city,region,status,primary_pkd,primary_pkd_description,
                      latest_period,latest_currency,latest_revenue_text AS revenue,
                      segment,name_signal,screening_reason,business_type,is_active,
                      annual_period,annual_revenue,annual_profit,classification_json,
                      (SELECT status FROM company_verification v WHERE v.krs=profile_screening.krs) verification_status
               FROM profile_screening WHERE """
            + " AND ".join(clauses)
            + " ORDER BY krs",
            params,
        ).fetchall()

    _update_progress("Generuję plik CSV…", 50)

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "KRS", "Nazwa", "Miasto", "Województwo", "Status", "PKD główne",
        "Opis PKD", "Ostatni okres", "Waluta", "Przychód", "Segment",
        "Sygnał nazwy", "Uzasadnienie", "Nowa klasyfikacja", "Aktywna",
        "Pełny rok PLN", "Przychód roczny PLN", "Zysk roczny PLN",
        "Reguły i dowody", "Weryfikacja",
    ])
    for row in rows:
        writer.writerow([
            row[key] for key in (
                "krs", "name", "city", "region", "status", "primary_pkd",
                "primary_pkd_description", "latest_period", "latest_currency",
                "revenue", "segment", "name_signal", "screening_reason",
                "business_type", "is_active", "annual_period",
                "annual_revenue", "annual_profit", "classification_json", "verification_status",
            )
        ])

    from etl.config import ROOT

    export_dir = ROOT / ".local" / "exports"
    export_dir.mkdir(parents=True, exist_ok=True)
    csv_bytes = output.getvalue().encode("utf-8-sig")

    fd, path = tempfile.mkstemp(
        prefix="export-", suffix=".csv", dir=export_dir,
    )
    try:
        import os
        os.write(fd, csv_bytes)
    finally:
        import os
        os.close(fd)

    _update_progress("Eksport zakończony.", 100)
    return {"path": path, "rows": len(rows), "size_bytes": len(csv_bytes)}


# ---------------------------------------------------------------------------
# Rebuild SQLite
# ---------------------------------------------------------------------------

def task_rebuild_sqlite(collection_dir: str | None = None) -> dict:
    """Rebuild the local SQLite database from the published screening JSON."""
    _update_progress("Rozpoczynam przebudowę bazy SQLite…", 0)

    from backend.local_profiles import build_database
    from backend.cache import invalidate

    target_dir = Path(collection_dir) if collection_dir else None
    result = build_database(collection_dir=target_dir)

    # Invalidate all cached API responses after a rebuild
    deleted = invalidate("cl:*")
    result["cache_invalidated"] = deleted

    _update_progress("Przebudowa zakończona.", 100)
    return result


# ---------------------------------------------------------------------------
# Research
# ---------------------------------------------------------------------------

def task_run_research(module: str, args: list[str] | None = None) -> dict:
    """Run a research module (leverage_study or developer_questions_study)."""
    import subprocess
    import sys

    _update_progress(f"Uruchamiam moduł badawczy: {module}…", 0)

    allowed = {"research.leverage_study", "research.developer_questions_study"}
    if module not in allowed:
        raise ValueError(f"Nieznany moduł badawczy: {module}")

    cmd = [sys.executable, "-m", module] + (args or [])
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=3600,  # 1-hour safety limit
    )

    _update_progress("Badanie zakończone.", 100)
    return {
        "module": module,
        "returncode": result.returncode,
        "stdout": result.stdout[-2000:] if result.stdout else "",
        "stderr": result.stderr[-2000:] if result.stderr else "",
    }
