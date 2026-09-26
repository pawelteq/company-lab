"""Financial geography index and aggregations for the current profile collection.

The source profile store intentionally keeps complete provider payloads compressed.
This module materialises only the fields needed by the financial atlas into a
small, indexed SQLite sidecar.  Map requests never decompress profiles.
"""
from __future__ import annotations

from collections import defaultdict
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from statistics import fmean, median
from typing import Iterable
import json
import math
import os
import re
import sqlite3
import tempfile
import unicodedata

from backend import local_profiles
from etl.config import ROOT


INDEX_VERSION = "financial-map-v2"
DEFAULT_PATH = ROOT / ".local" / "financial_map.sqlite3"

AGGREGATIONS = {
    "sum": "Suma",
    "mean": "Średnia",
    "median": "Mediana",
    "winsor_mean": "Średnia winsoryzowana",
    "min": "Minimum",
    "max": "Maksimum",
    "regional_ratio": "Wskaźnik zagregowany",
    "company_count": "Liczba firm",
}


def _metric(
    metric_id: str, label: str, category: str, fmt: str,
    aggregations: tuple[str, ...], default: str,
    *, higher: bool | None = None, field: str | None = None,
    numerator: str | None = None, denominator: str | None = None,
    description: str = "",
) -> dict:
    return {
        "id": metric_id,
        "label": label,
        "category": category,
        "format": fmt,
        "available_aggregations": list(aggregations),
        "default_aggregation": default,
        "higher_is_better": higher,
        "field": field or metric_id,
        "numerator_field": numerator,
        "denominator_field": denominator,
        "description": description,
    }


MONEY_AGGS = ("sum", "mean", "median", "winsor_mean", "min", "max")
RATIO_AGGS = ("median", "mean", "winsor_mean", "regional_ratio", "min", "max")
PLAIN_RATIO_AGGS = ("median", "mean", "winsor_mean", "min", "max")

METRICS: dict[str, dict] = {
    item["id"]: item for item in (
        _metric("revenue_total", "Przychody razem", "Przychody", "currency", MONEY_AGGS, "sum", field="revenue_total"),
        _metric("revenue_operating", "Przychody operacyjne", "Przychody", "currency", MONEY_AGGS, "sum"),
        _metric("revenue_net_sales_products", "Przychody netto ze sprzedaży", "Przychody", "currency", MONEY_AGGS, "sum"),
        _metric("other_oper_income", "Pozostałe przychody operacyjne", "Przychody", "currency", MONEY_AGGS, "sum"),
        _metric("financial_income", "Przychody finansowe", "Przychody", "currency", MONEY_AGGS, "sum"),
        _metric("profit_net", "Zysk netto", "Wynik", "currency", MONEY_AGGS, "sum", higher=True),
        _metric("profit_sales", "Zysk ze sprzedaży", "Wynik", "currency", MONEY_AGGS, "sum", higher=True),
        _metric("profit_gross", "Wynik brutto", "Wynik", "currency", MONEY_AGGS, "sum", higher=True),
        _metric("ebit", "EBIT", "Wynik", "currency", MONEY_AGGS, "sum", higher=True),
        _metric("ebitda", "EBITDA", "Wynik", "currency", MONEY_AGGS, "sum", higher=True),
        _metric("operating_costs_total", "Koszty operacyjne", "Koszty", "currency", MONEY_AGGS, "sum"),
        _metric("cost_materials_energy", "Materiały i energia", "Koszty", "currency", MONEY_AGGS, "sum"),
        _metric("cost_external_services", "Usługi obce", "Koszty", "currency", MONEY_AGGS, "sum"),
        _metric("cost_wages", "Wynagrodzenia", "Koszty", "currency", MONEY_AGGS, "sum"),
        _metric("cost_social_security_other", "Świadczenia pracownicze", "Koszty", "currency", MONEY_AGGS, "sum"),
        _metric("cost_amortization", "Amortyzacja", "Koszty", "currency", MONEY_AGGS, "sum"),
        _metric("financial_costs", "Koszty finansowe", "Koszty", "currency", MONEY_AGGS, "sum"),
        _metric("total_assets", "Aktywa razem", "Aktywa", "currency", MONEY_AGGS, "sum"),
        _metric("fixed_assets", "Aktywa trwałe", "Aktywa", "currency", MONEY_AGGS, "sum"),
        _metric("current_assets", "Aktywa obrotowe", "Aktywa", "currency", MONEY_AGGS, "sum"),
        _metric("inventories", "Zapasy", "Aktywa", "currency", MONEY_AGGS, "sum"),
        _metric("short_term_receivables", "Należności krótkoterminowe", "Aktywa", "currency", MONEY_AGGS, "sum"),
        _metric("cash_and_equivalents", "Środki pieniężne", "Aktywa", "currency", MONEY_AGGS, "sum"),
        _metric("equity", "Kapitał własny", "Pasywa", "currency", MONEY_AGGS, "sum"),
        _metric("liabilities_and_provisions", "Zobowiązania i rezerwy", "Pasywa", "currency", MONEY_AGGS, "sum"),
        _metric("short_term_liabilities", "Zobowiązania krótkoterminowe", "Pasywa", "currency", MONEY_AGGS, "sum"),
        _metric("long_term_liabilities", "Zobowiązania długoterminowe", "Pasywa", "currency", MONEY_AGGS, "sum"),
        _metric("roa", "ROA", "Rentowność", "percent", RATIO_AGGS, "median", higher=True,
                numerator="profit_net", denominator="total_assets",
                description="Mediana firm lub wynik regionu: suma zysku netto / suma aktywów."),
        _metric("roe", "ROE", "Rentowność", "percent", RATIO_AGGS, "median", higher=True,
                numerator="profit_net", denominator="equity",
                description="Mediana firm lub wynik regionu: suma zysku netto / suma kapitału własnego."),
        _metric("net_margin", "Marża netto", "Rentowność", "percent", RATIO_AGGS, "median", higher=True,
                numerator="profit_net", denominator="revenue_total"),
        _metric("ebit_margin", "Marża EBIT", "Rentowność", "percent", RATIO_AGGS, "median", higher=True,
                numerator="ebit", denominator="revenue_total"),
        _metric("ebitda_margin", "Marża EBITDA", "Rentowność", "percent", RATIO_AGGS, "median", higher=True,
                numerator="ebitda", denominator="revenue_total"),
        _metric("gross_margin", "Marża brutto", "Rentowność", "percent", RATIO_AGGS, "median", higher=True,
                numerator="profit_gross", denominator="revenue_total"),
        _metric("liabilities_to_total_assets", "Zobowiązania / aktywa", "Zadłużenie", "percent", RATIO_AGGS, "median",
                numerator="liabilities_and_provisions", denominator="total_assets"),
        _metric("debt_to_equity", "Zobowiązania / kapitał własny", "Zadłużenie", "ratio", RATIO_AGGS, "median", higher=False,
                numerator="liabilities_and_provisions", denominator="equity"),
        _metric("equity_to_assets", "Kapitał własny / aktywa", "Zadłużenie", "percent", RATIO_AGGS, "median", higher=True,
                numerator="equity", denominator="total_assets"),
        _metric("current_ratio", "Płynność bieżąca", "Płynność", "ratio", RATIO_AGGS, "median", numerator="current_assets", denominator="short_term_liabilities"),
        _metric("quick_ratio", "Płynność szybka", "Płynność", "ratio", PLAIN_RATIO_AGGS, "median"),
        _metric("cash_ratio", "Płynność gotówkowa", "Płynność", "ratio", RATIO_AGGS, "median", numerator="cash_and_equivalents", denominator="short_term_liabilities"),
        _metric("asset_turnover", "Rotacja aktywów", "Efektywność", "ratio", RATIO_AGGS, "median", numerator="revenue_total", denominator="total_assets"),
    )
}

SOURCE_FIELDS = tuple(dict.fromkeys(
    [m["field"] for m in METRICS.values()]
    + [m["numerator_field"] for m in METRICS.values() if m["numerator_field"]]
    + [m["denominator_field"] for m in METRICS.values() if m["denominator_field"]]
    + ["inventories"]
))

REGION_NAMES = {
    "02": "Dolnośląskie", "04": "Kujawsko-pomorskie", "06": "Lubelskie", "08": "Lubuskie",
    "10": "Łódzkie", "12": "Małopolskie", "14": "Mazowieckie", "16": "Opolskie",
    "18": "Podkarpackie", "20": "Podlaskie", "22": "Pomorskie", "24": "Śląskie",
    "26": "Świętokrzyskie", "28": "Warmińsko-mazurskie", "30": "Wielkopolskie", "32": "Zachodniopomorskie",
}
REGION_BY_KEY = {
    "dolnoslaskie": "02", "kujawsko-pomorskie": "04", "lubelskie": "06", "lubuskie": "08",
    "lodzkie": "10", "malopolskie": "12", "mazowieckie": "14", "opolskie": "16",
    "podkarpackie": "18", "podlaskie": "20", "pomorskie": "22", "slaskie": "24",
    "swietokrzyskie": "26", "warminsko-mazurskie": "28", "wielkopolskie": "30", "zachodniopomorskie": "32",
}


def index_path() -> Path:
    configured = os.environ.get("FINANCIAL_MAP_SQLITE_PATH")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_PATH


@contextmanager
def connect(path: Path | None = None, *, readonly: bool = True):
    target = (path or index_path()).resolve()
    if readonly:
        if not target.is_file():
            raise FileNotFoundError(target)
        conn = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _ensure_verification_column(connection: sqlite3.Connection) -> None:
    columns = {row["name"] for row in connection.execute("PRAGMA table_info(company)")}
    if "verification_status" not in columns:
        connection.execute("ALTER TABLE company ADD COLUMN verification_status TEXT")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_map_company_verification ON company(collection_id,verification_status,krs)"
    )


def sync_verifications(source: Path | None = None, target: Path | None = None) -> dict:
    """Synchronize all saved decisions without rebuilding financial observations."""
    source = (source or local_profiles.database_path()).resolve()
    target = (target or index_path()).resolve()
    if not source.is_file() or not target.is_file():
        return {"updated": 0, "available": False}
    with local_profiles.connect(source) as profiles, connect(target, readonly=False) as atlas:
        _ensure_verification_column(atlas)
        atlas.execute("UPDATE company SET verification_status=NULL")
        table_exists = profiles.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='company_verification'"
        ).fetchone()
        rows = profiles.execute(
            "SELECT krs,status FROM company_verification WHERE status IN ('confirmed','rejected')"
        ).fetchall() if table_exists else []
        atlas.executemany(
            "UPDATE company SET verification_status=? WHERE krs=?",
            ((row["status"], row["krs"]) for row in rows),
        )
        atlas.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('version',?)", (INDEX_VERSION,))
        atlas.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('source_size',?)", (str(source.stat().st_size),))
        atlas.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('source_mtime_ns',?)", (str(source.stat().st_mtime_ns),))
        atlas.commit()
    return {"updated": len(rows), "available": True}


def set_verification_status(krs: str, status: str | None, target: Path | None = None) -> int:
    """Update one company decision so map calculations change on the next request."""
    target = (target or index_path()).resolve()
    if not target.is_file():
        return 0
    with connect(target, readonly=False) as atlas:
        _ensure_verification_column(atlas)
        cursor = atlas.execute(
            "UPDATE company SET verification_status=? WHERE krs=?",
            (status if status in ("confirmed", "rejected") else None, krs),
        )
        source = local_profiles.database_path()
        if source.is_file():
            atlas.execute("INSERT OR REPLACE INTO meta(key,value) VALUES ('source_size',?)", (str(source.stat().st_size),))
            atlas.execute(
                "INSERT OR REPLACE INTO meta(key,value) VALUES ('source_mtime_ns',?)",
                (str(source.stat().st_mtime_ns),),
            )
        atlas.commit()
        return cursor.rowcount


def _norm(value: object) -> str:
    text = str(value or "").casefold().replace("ł", "l")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"^(wojewodztwo|woj\.?|powiat|gmina|miasto|m\.)\s+", "", text)
    text = re.sub(r"\s+county$", "", text)
    text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    return {"warsaw": "warszawa", "lodz": "lodz"}.get(text, text)


def _geo_lookups() -> tuple[dict, dict, dict]:
    maps = ROOT / "frontend" / "public" / "maps"
    province_by_name = {_norm(name): code for code, name in REGION_NAMES.items()}
    province_by_name.update({_norm(key): code for key, code in REGION_BY_KEY.items()})
    counties: dict[tuple[str, str], tuple[str, str]] = {}
    municipalities: dict[tuple[str, str], tuple[str, str]] = {}
    for feature in json.loads((maps / "powiaty.json").read_text(encoding="utf-8"))["features"]:
        props = feature["properties"]
        code, name = str(props["code"]), str(props["name"])
        counties[(code[:2], _norm(name))] = (code, name)
    for feature in json.loads((maps / "gminy.json").read_text(encoding="utf-8"))["features"]:
        props = feature["properties"]
        code, name = str(props["code"]), str(props["name"])
        municipalities[(code[:4], _norm(name))] = (code, name)
    return province_by_name, counties, municipalities


def _unique_lookup(mapping: dict, name: str) -> tuple[str, str] | None:
    matches = {value for key, value in mapping.items() if key[1] == name}
    return next(iter(matches)) if len(matches) == 1 else None


def _number(value: object) -> float | None:
    if value is None or isinstance(value, (bool, dict, list)):
        return None
    try:
        number = float(str(value).replace(" ", "").replace(",", "."))
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _year(record: dict) -> int | None:
    raw = str(record.get("period_to_resolved") or record.get("sf_period_to") or "")
    match = re.match(r"(19|20)\d{2}", raw)
    return int(match.group(0)) if match else None


def _record_score(record: dict) -> tuple:
    start = str(record.get("period_from_resolved") or record.get("sf_period_from") or "")[:10]
    end = str(record.get("period_to_resolved") or record.get("sf_period_to") or "")[:10]
    annual = 0
    try:
        annual = int((date.fromisoformat(end) - date.fromisoformat(start)).days >= 300)
    except ValueError:
        pass
    scope = str(record.get("consolidation_scope") or "").casefold()
    standalone = int("standalone" in scope or "jednost" in scope or not scope)
    completeness = sum(_number(record.get(field)) is not None for field in SOURCE_FIELDS)
    return annual, standalone, completeness, str(record.get("extracted_at") or "")


def _derived_value(field: str, values: dict[str, float | None]) -> float | None:
    def ratio(numerator: str, denominator: str, factor: float = 1.0) -> float | None:
        n, d = values.get(numerator), values.get(denominator)
        return n / d * factor if n is not None and d not in (None, 0) else None
    if field == "roa": return values.get(field) if values.get(field) is not None else ratio("profit_net", "total_assets", 100)
    if field == "roe": return values.get(field) if values.get(field) is not None else ratio("profit_net", "equity", 100)
    if field == "net_margin": return values.get(field) if values.get(field) is not None else ratio("profit_net", "revenue_total", 100)
    if field == "ebit_margin": return ratio("ebit", "revenue_total", 100)
    if field == "ebitda_margin": return ratio("ebitda", "revenue_total", 100)
    if field == "gross_margin": return ratio("profit_gross", "revenue_total", 100)
    if field == "liabilities_to_total_assets": return values.get(field) if values.get(field) is not None else ratio("liabilities_and_provisions", "total_assets", 100)
    if field == "debt_to_equity": return ratio("liabilities_and_provisions", "equity")
    if field == "equity_to_assets": return ratio("equity", "total_assets", 100)
    if field == "current_ratio": return ratio("current_assets", "short_term_liabilities")
    if field == "cash_ratio": return ratio("cash_and_equivalents", "short_term_liabilities")
    if field == "asset_turnover": return ratio("revenue_total", "total_assets")
    if field == "quick_ratio":
        current, inventory, liabilities = values.get("current_assets"), values.get("inventories"), values.get("short_term_liabilities")
        return (current - inventory) / liabilities if current is not None and inventory is not None and liabilities not in (None, 0) else None
    return values.get(field)


def build_index(source: Path | None = None, target: Path | None = None) -> dict:
    source = (source or local_profiles.database_path()).resolve()
    target = (target or index_path()).resolve()
    province_by_name, counties, municipalities = _geo_lookups()
    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix="financial-map-", suffix=".sqlite3", dir=target.parent)
    os.close(descriptor)
    temporary = Path(temporary_name)
    profiles = observations = matched_counties = matched_municipalities = 0
    available = set()
    try:
        with local_profiles.connect(source) as source_conn, connect(temporary, readonly=False) as out:
            metric_columns = ",\n".join(f'"{field}" REAL' for field in SOURCE_FIELDS)
            out.executescript(f"""
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=NORMAL;
                PRAGMA temp_store=MEMORY;
                CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE company (
                    collection_id TEXT NOT NULL, krs TEXT NOT NULL, name TEXT,
                    region_id TEXT, region_name TEXT, county_id TEXT, county_name TEXT,
                    municipality_id TEXT, municipality_name TEXT, primary_pkd TEXT,
                    business_type TEXT, verification_status TEXT,
                    PRIMARY KEY(collection_id,krs)
                );
                CREATE TABLE company_pkd (
                    collection_id TEXT NOT NULL, krs TEXT NOT NULL, code TEXT NOT NULL,
                    is_primary INTEGER NOT NULL, target_match INTEGER NOT NULL,
                    PRIMARY KEY(collection_id,krs,code,is_primary)
                );
                CREATE TABLE observation (
                    collection_id TEXT NOT NULL, krs TEXT NOT NULL, year INTEGER NOT NULL,
                    currency TEXT NOT NULL, {metric_columns},
                    PRIMARY KEY(collection_id,krs,year)
                );
            """)
            company_sql = "INSERT INTO company VALUES (?,?,?,?,?,?,?,?,?,?,?,?)"
            pkd_sql = "INSERT OR IGNORE INTO company_pkd VALUES (?,?,?,?,?)"
            fields_sql = ",".join(f'"{field}"' for field in SOURCE_FIELDS)
            placeholders = ",".join("?" for _ in range(4 + len(SOURCE_FIELDS)))
            observation_sql = f"INSERT INTO observation(collection_id,krs,year,currency,{fields_sql}) VALUES ({placeholders})"
            source_columns = {row["name"] for row in source_conn.execute("PRAGMA table_info(profile_screening)")}
            county_sql = "s.county" if "county" in source_columns else "NULL AS county"
            municipality_sql = "s.municipality" if "municipality" in source_columns else "NULL AS municipality"
            business_sql = "s.business_type" if "business_type" in source_columns else "NULL AS business_type"
            has_verifications = source_conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='company_verification'"
            ).fetchone()
            verification_sql = "v.status" if has_verifications else "NULL"
            verification_join = "LEFT JOIN company_verification v ON v.krs=s.krs" if has_verifications else ""
            rows = source_conn.execute(f"""SELECT s.collection_id,s.krs,s.name,s.region,{county_sql},{municipality_sql},
                s.primary_pkd,{business_sql},s.profile_json_zlib,{verification_sql} verification_status
                FROM profile_screening s {verification_join}""")
            for row in rows:
                profile = local_profiles.decompress_json(row["profile_json_zlib"])
                region_id = province_by_name.get(_norm(row["region"]))
                region_name = REGION_NAMES.get(region_id, row["region"])
                county_match = counties.get((region_id or "", _norm(row["county"])))
                if not county_match:
                    county_match = _unique_lookup(counties, _norm(row["county"]))
                county_id = county_match[0] if county_match else None
                county_name = row["county"] or (county_match[1] if county_match else None)
                if county_id: matched_counties += 1
                municipality_match = municipalities.get((county_id or "", _norm(row["municipality"])))
                if not municipality_match:
                    municipality_match = municipalities.get((county_id or "", _norm(profile.get("city"))))
                if not municipality_match:
                    municipality_match = _unique_lookup(municipalities, _norm(row["municipality"]))
                municipality_id = municipality_match[0] if municipality_match else None
                municipality_name = row["municipality"] or (municipality_match[1] if municipality_match else None)
                if municipality_id: matched_municipalities += 1
                out.execute(company_sql, (
                    row["collection_id"], row["krs"], row["name"], region_id, region_name,
                    county_id, county_name, municipality_id, municipality_name,
                    row["primary_pkd"], row["business_type"], row["verification_status"],
                ))
                activities = profile.get("activities") if isinstance(profile.get("activities"), list) else []
                if not activities and row["primary_pkd"]:
                    activities = [{"code": row["primary_pkd"], "is_primary": True, "target_match": False}]
                for activity in activities:
                    code = str(activity.get("code") or "").strip().upper()
                    if code:
                        out.execute(pkd_sql, (
                            row["collection_id"], row["krs"], code,
                            int(bool(activity.get("is_primary"))), int(bool(activity.get("target_match"))),
                        ))
                best: dict[int, dict] = {}
                for record in profile.get("financials") or []:
                    if not isinstance(record, dict): continue
                    year = _year(record)
                    if year is None: continue
                    current = best.get(year)
                    if current is None or _record_score(record) > _record_score(current):
                        best[year] = record
                for year, record in best.items():
                    currency = str(record.get("currency") or "PLN").upper()
                    raw = {field: _number(record.get(field)) for field in SOURCE_FIELDS}
                    values = {field: _derived_value(field, raw) for field in SOURCE_FIELDS}
                    available.update(field for field, value in values.items() if value is not None)
                    out.execute(observation_sql, (
                        row["collection_id"], row["krs"], year, currency,
                        *(values[field] for field in SOURCE_FIELDS),
                    ))
                    observations += 1
                profiles += 1
                if profiles % 500 == 0:
                    out.commit()
                    print(f"Mapa finansowa: {profiles} firm, {observations} obserwacji", flush=True)
            out.executescript("""
                CREATE INDEX idx_map_company_region ON company(collection_id,region_id);
                CREATE INDEX idx_map_company_county ON company(collection_id,county_id);
                CREATE INDEX idx_map_company_municipality ON company(collection_id,municipality_id);
                CREATE INDEX idx_map_company_verification ON company(collection_id,verification_status,krs);
                CREATE INDEX idx_map_pkd ON company_pkd(collection_id,code,is_primary,target_match,krs);
                CREATE INDEX idx_map_pkd_primary ON company_pkd(collection_id,is_primary,code,krs);
                CREATE INDEX idx_map_pkd_target ON company_pkd(collection_id,target_match,is_primary,krs);
                CREATE INDEX idx_map_pkd_target_company ON company_pkd(collection_id,target_match,krs);
                CREATE INDEX idx_map_observation_year ON observation(collection_id,year,krs);
            """)
            out.executemany("INSERT INTO meta VALUES (?,?)", (
                ("version", INDEX_VERSION), ("source_path", str(source)),
                ("source_size", str(source.stat().st_size)),
                ("source_mtime_ns", str(source.stat().st_mtime_ns)),
                ("available_metrics", json.dumps(sorted(available))),
            ))
            out.commit()
            if out.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise RuntimeError("Kontrola indeksu mapy finansowej nie powiodła się")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "path": str(target), "version": INDEX_VERSION, "profiles": profiles,
        "observations": observations, "county_matches": matched_counties,
        "municipality_matches": matched_municipalities,
    }


def status() -> dict:
    with connect() as conn:
        meta = {row["key"]: row["value"] for row in conn.execute("SELECT key,value FROM meta")}
        result = {
            "path": str(index_path()), "version": meta.get("version"),
            "profiles": conn.execute("SELECT count(*) FROM company").fetchone()[0],
            "observations": conn.execute("SELECT count(*) FROM observation").fetchone()[0],
        }
    source = local_profiles.database_path().resolve()
    result["current"] = (
        meta.get("version") == INDEX_VERSION
        and meta.get("source_size") == str(source.stat().st_size)
        and meta.get("source_mtime_ns") == str(source.stat().st_mtime_ns)
    ) if source.exists() else False
    return result


def metadata(collection: str) -> dict:
    with connect() as conn:
        years = [row[0] for row in conn.execute(
            "SELECT DISTINCT year FROM observation WHERE collection_id=? ORDER BY year DESC", (collection,)
        )]
        if not years:
            raise KeyError(collection)
        availability = conn.execute(
            "SELECT " + ",".join(f'max(\"{field}\" IS NOT NULL) AS \"{field}\"' for field in SOURCE_FIELDS)
            + " FROM observation WHERE collection_id=?", (collection,),
        ).fetchone()
        available = {field for field in SOURCE_FIELDS if availability[field]}
        pkd = [dict(row) for row in conn.execute("""SELECT code,count(DISTINCT krs) company_count
            FROM company_pkd WHERE collection_id=? GROUP BY code ORDER BY company_count DESC,code""", (collection,))]
        collection_profiles = conn.execute("SELECT count(*) FROM company WHERE collection_id=?", (collection,)).fetchone()[0]
        collection_observations = conn.execute("SELECT count(*) FROM observation WHERE collection_id=?", (collection,)).fetchone()[0]
    metrics = []
    for item in METRICS.values():
        required = {item["field"], item.get("numerator_field"), item.get("denominator_field")} - {None}
        if item["field"] in available or required <= available:
            metrics.append({key: value for key, value in item.items() if key != "field"})
    return {
        "collection": collection, "years": years, "metrics": metrics,
        "aggregations": [{"id": key, "label": value} for key, value in AGGREGATIONS.items()],
        "pkd": pkd, "levels": ["voivodeship", "county", "municipality"],
        "index": {**status(), "profiles": collection_profiles, "observations": collection_observations},
    }


def _filters(collection: str, pkd: str, pkd_mode: str, verification: str = "all") -> tuple[str, list]:
    clauses = ["c.collection_id=?"]
    params: list = [collection]
    if pkd:
        if pkd == "developer":
            conditions = ["p.target_match=1"]
        else:
            conditions = ["p.code=?"]
            params.append(pkd.upper())
        if pkd_mode == "primary":
            conditions.append("p.is_primary=1")
        clauses.append("EXISTS (SELECT 1 FROM company_pkd p WHERE p.collection_id=c.collection_id AND p.krs=c.krs AND " + " AND ".join(conditions) + ")")
    if verification == "verified":
        clauses.append("c.verification_status IN ('confirmed','rejected')")
    elif verification == "unverified":
        clauses.append("c.verification_status IS NULL")
    elif verification in ("confirmed", "rejected"):
        clauses.append("c.verification_status=?")
        params.append(verification)
    return " AND ".join(clauses), params


def _region_columns(level: str) -> tuple[str, str]:
    return {
        "voivodeship": ("region_id", "region_name"),
        "county": ("county_id", "county_name"),
        "municipality": ("municipality_id", "municipality_name"),
    }[level]


def _percentile(values: list[float], q: float) -> float | None:
    if not values: return None
    ordered = sorted(values)
    pos = (len(ordered) - 1) * q
    low, high = math.floor(pos), math.ceil(pos)
    return ordered[low] if low == high else ordered[low] + (ordered[high] - ordered[low]) * (pos - low)


def _winsor_mean(values: list[float]) -> float | None:
    if not values: return None
    low, high = _percentile(values, .05), _percentile(values, .95)
    assert low is not None and high is not None
    return fmean(min(high, max(low, value)) for value in values)


def _aggregate(values: list[float], aggregation: str, numerator: list[float], denominator: list[float], fmt: str) -> float | None:
    if aggregation == "company_count": return float(len(values))
    if not values: return None
    if aggregation == "sum": return sum(values)
    if aggregation == "mean": return fmean(values)
    if aggregation == "median": return median(values)
    if aggregation == "winsor_mean": return _winsor_mean(values)
    if aggregation == "min": return min(values)
    if aggregation == "max": return max(values)
    if aggregation == "regional_ratio":
        denominator_sum = sum(denominator)
        if not denominator or denominator_sum == 0: return None
        factor = 100.0 if fmt == "percent" else 1.0
        return sum(numerator) / denominator_sum * factor
    raise ValueError(aggregation)


def _format(value: float | None, fmt: str, *, change: bool = False) -> str:
    if value is None: return "Brak danych"
    sign = "+" if change and value > 0 else ""
    if fmt == "currency" and not change:
        absolute = abs(value); prefix = "−" if value < 0 else ""
        if absolute >= 1_000_000_000_000: return f"{prefix}{absolute/1_000_000_000_000:.2f}".replace(".", ",") + " bln"
        if absolute >= 1_000_000_000: return f"{prefix}{absolute/1_000_000_000:.2f}".replace(".", ",") + " mld"
        if absolute >= 1_000_000: return f"{prefix}{absolute/1_000_000:.2f}".replace(".", ",") + " mln"
        if absolute >= 1_000: return f"{prefix}{absolute/1_000:.1f}".replace(".", ",") + " tys."
        return f"{value:,.0f}".replace(",", " ") + " zł"
    suffix = " p.p." if change and fmt == "percent" else "%" if fmt == "percent" or change else "x" if fmt == "ratio" else ""
    return f"{sign}{value:.2f}".replace(".", ",") + suffix


def _raw_regions(conn, collection: str, level: str, year: int, metric: dict, aggregation: str, pkd: str, pkd_mode: str, verification: str = "all") -> tuple[dict, dict]:
    region_id, region_name = _region_columns(level)
    where, params = _filters(collection, pkd, pkd_mode, verification)
    counts = {
        row["region_id"]: {"company_count": row["company_count"], "region_name": row["region_name"]}
        for row in conn.execute(f"""SELECT c.{region_id} region_id,min(c.{region_name}) region_name,count(*) company_count
        FROM company c WHERE {where} AND c.{region_id} IS NOT NULL GROUP BY c.{region_id}""", params)
    }
    field = metric["field"]
    numerator_field, denominator_field = metric.get("numerator_field"), metric.get("denominator_field")
    selected = [field]
    if numerator_field: selected.append(numerator_field)
    if denominator_field: selected.append(denominator_field)
    selected_sql = ",".join(f'o."{item}"' for item in dict.fromkeys(selected))
    rows = conn.execute(f"""SELECT c.{region_id} region_id,c.{region_name} region_name,o.krs,{selected_sql}
        FROM observation o JOIN company c ON c.collection_id=o.collection_id AND c.krs=o.krs
        WHERE {where} AND o.year=? AND o.currency='PLN' AND c.{region_id} IS NOT NULL""", [*params, year])
    grouped: dict[str, dict] = {}
    for row in rows:
        group = grouped.setdefault(row["region_id"], {"name": row["region_name"], "values": [], "numerator": [], "denominator": []})
        value = row[field]
        if value is not None: group["values"].append(float(value))
        if numerator_field and denominator_field and row[numerator_field] is not None and row[denominator_field] not in (None, 0):
            group["numerator"].append(float(row[numerator_field])); group["denominator"].append(float(row[denominator_field]))
    result = {}
    for key, group in grouped.items():
        values = group["values"]
        result[key] = {
            "region_id": key, "region_name": group["name"], "company_count": counts.get(key, {}).get("company_count", 0),
            "metric_company_count": len(values),
            "value": _aggregate(values, aggregation, group["numerator"], group["denominator"], metric["format"]),
            "mean": fmean(values) if values else None, "median": median(values) if values else None,
            "winsor_mean": _winsor_mean(values), "min": min(values) if values else None,
            "max": max(values) if values else None, "p25": _percentile(values, .25),
            "p75": _percentile(values, .75), "p90": _percentile(values, .90),
            "regional_ratio": _aggregate(values, "regional_ratio", group["numerator"], group["denominator"], metric["format"])
                if numerator_field and denominator_field else None,
        }
    for key, count in counts.items():
        result.setdefault(key, {"region_id": key, "region_name": count["region_name"], "company_count": count["company_count"], "metric_company_count": 0, "value": None,
            "mean": None, "median": None, "winsor_mean": None, "min": None, "max": None, "p25": None, "p75": None, "p90": None, "regional_ratio": None})
    return result, counts


COMPARISON_METRICS = (
    ("revenue_total", "sum"),
    ("profit_net", "sum"),
    ("roa", "median"),
    ("roe", "median"),
    ("ebit_margin", "median"),
)


def compare_regions(collection: str, region_ids: list[str], *, level: str, year: int,
                    pkd: str = "", pkd_mode: str = "primary", min_companies: int = 5,
                    verification: str = "all") -> dict:
    """Return a stable five-column comparison for at most five regions."""
    wanted = list(dict.fromkeys(region_ids))[:5]
    if not wanted:
        return {"level": level, "year": year, "regions": []}
    rows = {region_id: {"region_id": region_id, "region_name": region_id, "metrics": {}} for region_id in wanted}
    with connect() as conn:
        for metric_id, aggregation in COMPARISON_METRICS:
            metric = METRICS[metric_id]
            regions, _ = _raw_regions(conn, collection, level, year, metric, aggregation, pkd, pkd_mode, verification)
            for region_id in wanted:
                item = regions.get(region_id)
                if item:
                    rows[region_id]["region_name"] = item["region_name"]
                    value = item["value"] if item["metric_company_count"] >= min_companies else None
                    rows[region_id]["metrics"][metric_id] = {
                        "value": value,
                        "formatted_value": _format(value, metric["format"]),
                        "company_count": item["metric_company_count"],
                    }
                else:
                    rows[region_id]["metrics"][metric_id] = {
                        "value": None, "formatted_value": "Brak danych", "company_count": 0,
                    }
    return {"level": level, "year": year, "regions": list(rows.values())}


def map_data(collection: str, *, level: str, year: int, metric_id: str, aggregation: str,
             pkd: str = "", pkd_mode: str = "primary", min_companies: int = 5,
             view: str = "value", compare_year: int | None = None,
             verification: str = "all") -> dict:
    metric = METRICS[metric_id]
    if aggregation not in metric["available_aggregations"]:
        raise ValueError("Ta agregacja nie jest dostępna dla wybranej metryki")
    with connect() as conn:
        current, _ = _raw_regions(conn, collection, level, year, metric, aggregation, pkd, pkd_mode, verification)
        comparison = {}
        if view == "change":
            comparison, _ = _raw_regions(conn, collection, level, compare_year or year - 1, metric, aggregation, pkd, pkd_mode, verification)
    eligible = []
    for item in current.values():
        raw_value = item["value"]
        item["insufficient_data"] = item["metric_company_count"] < min_companies
        if item["insufficient_data"]:
            item["value"] = None
        if view == "change":
            comparison_item = comparison.get(item["region_id"], {})
            previous = comparison_item.get("value") if comparison_item.get("metric_company_count", 0) >= min_companies else None
            item["comparison_value"] = previous
            if item["value"] is None or previous is None:
                item["value"] = None
            elif metric["format"] == "percent":
                item["value"] = item["value"] - previous
            elif previous == 0:
                item["value"] = None
            else:
                item["value"] = (item["value"] - previous) / abs(previous) * 100
        item["formatted_value"] = _format(item["value"], metric["format"], change=view == "change")
        item["raw_value"] = None if item["insufficient_data"] else raw_value
        if item["insufficient_data"]:
            for key in ("mean", "median", "winsor_mean", "min", "max", "p25", "p75", "p90", "regional_ratio"):
                item[key] = None
        if item["value"] is not None: eligible.append(item)
    reverse = metric.get("higher_is_better") is not False
    eligible.sort(key=lambda item: item["value"], reverse=reverse)
    for rank, item in enumerate(eligible, 1):
        item["rank"], item["rank_total"] = rank, len(eligible)
    return {
        "level": level, "year": year, "compare_year": compare_year or (year - 1 if view == "change" else None),
        "view": view, "metric": {key: value for key, value in metric.items() if key != "field"},
        "aggregation": aggregation, "pkd": pkd, "pkd_mode": pkd_mode,
        "verification": verification,
        "min_companies": min_companies, "regions": list(current.values()),
    }


def region_detail(collection: str, region_id: str, *, level: str, year: int, metric_id: str,
                  aggregation: str, pkd: str = "", pkd_mode: str = "primary", min_companies: int = 1,
                  verification: str = "all") -> dict:
    payload = map_data(collection, level=level, year=year, metric_id=metric_id, aggregation=aggregation,
                       pkd=pkd, pkd_mode=pkd_mode, min_companies=min_companies, verification=verification)
    region = next((item for item in payload["regions"] if item["region_id"] == region_id), None)
    if not region: raise KeyError(region_id)
    if region["insufficient_data"]:
        return {**payload, "region": region, "trend": [], "top_revenue": [], "top_metric": [], "suppressed": True}
    metric = METRICS[metric_id]
    region_col, _ = _region_columns(level)
    where, params = _filters(collection, pkd, pkd_mode, verification)
    with connect() as conn:
        select_metric = f'o."{metric["field"]}"'
        common = f"""FROM observation o JOIN company c ON c.collection_id=o.collection_id AND c.krs=o.krs
            WHERE {where} AND o.year=? AND o.currency='PLN' AND c.{region_col}=?"""
        top_revenue = [dict(row) for row in conn.execute(f"""SELECT c.krs,c.name,o.revenue_total value {common}
            AND o.revenue_total IS NOT NULL ORDER BY o.revenue_total DESC LIMIT 8""", [*params, year, region_id])]
        top_metric = [dict(row) for row in conn.execute(f"""SELECT c.krs,c.name,{select_metric} value {common}
            AND {select_metric} IS NOT NULL ORDER BY {select_metric} DESC LIMIT 8""", [*params, year, region_id])]
        trend = []
        for trend_year in range(year - 4, year + 1):
            year_map, _ = _raw_regions(conn, collection, level, trend_year, metric, aggregation, pkd, pkd_mode, verification)
            item = year_map.get(region_id)
            trend.append({"year": trend_year, "value": item["value"] if item and item["metric_company_count"] >= min_companies else None})
    return {**payload, "region": region, "trend": trend, "top_revenue": top_revenue, "top_metric": top_metric, "suppressed": False}
