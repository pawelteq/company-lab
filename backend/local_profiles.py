"""Compressed SQLite store for the current Compabase profile collection.

The published screening JSON remains the immutable source artifact.  SQLite is
only a local, rebuildable serving index: list fields are stored in columns and
the complete profile is kept as a compressed JSON blob.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Iterator
import json
import os
import re
import sqlite3
import tempfile
import unicodedata
import zlib

import simplejson

from etl.config import ROOT
from etl.parsing import dumps, no_duplicate_keys


DEFAULT_PATH = ROOT / ".local" / "company_lab.sqlite3"
CATALOG_OMIT = {
    "financials", "raw_profile", "company_info", "profile_details",
    "connections", "related_companies", "graph", "roles", "ownership",
    "statistics", "insights_by_year", "seo_metric_summaries_by_year", "faq",
    "pkd_rankings", "similar_companies", "subsidiary_companies",
    "change_history", "ownership_family_insight",
}
NUMBER_RE = re.compile(r"^-?[0-9]+(?:[.,][0-9]+)?$")
POLISH_SEARCH_TRANSLATION = str.maketrans({"ł": "l", "Ł": "l"})


def database_path() -> Path:
    configured = os.environ.get("LOCAL_SQLITE_PATH")
    return Path(configured).expanduser().resolve() if configured else DEFAULT_PATH


def available(path: Path | None = None) -> bool:
    return (path or database_path()).is_file()


@contextmanager
def connect(path: Path | None = None, *, readonly: bool = True):
    target = (path or database_path()).resolve()
    if readonly:
        if not target.is_file():
            raise FileNotFoundError(
                f"Brak lokalnej bazy SQLite: {target}. Uruchom scripts/build_sqlite.py."
            )
        conn = sqlite3.connect(f"file:{target.as_posix()}?mode=ro", uri=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target)
    conn.row_factory = sqlite3.Row
    conn.create_function("geo_norm", 1, lambda value: normalize_search(value).strip(), deterministic=True)
    try:
        yield conn
    finally:
        conn.close()


def normalize_search(value: object) -> str:
    text = str(value or "").casefold().translate(POLISH_SEARCH_TRANSLATION)
    text = unicodedata.normalize("NFKD", text)
    return "".join(char for char in text if not unicodedata.combining(char))


def _numeric(value: object) -> float | None:
    if value is None or isinstance(value, (bool, list, dict)):
        return None
    text = str(value).strip().replace(" ", "")
    if not NUMBER_RE.fullmatch(text):
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def _latest_financial(profile: dict) -> tuple[int, int, str | None, str | None, object, float | None]:
    records = profile.get("financials")
    records = records if isinstance(records, list) else []
    valid = []
    revenue_periods = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        revenue = record.get("revenue_total")
        if revenue in (None, ""):
            revenue = record.get("revenue_operating")
        number = _numeric(revenue)
        if number is None:
            continue
        revenue_periods += 1
        period = record.get("period_to_resolved") or record.get("sf_period_to")
        valid.append((str(period or ""), record, revenue, number))

    latest = profile.get("latest_standalone")
    latest = latest if isinstance(latest, dict) else {}
    latest_number = _numeric(latest.get("revenue"))
    if latest_number is not None:
        return (
            len(records), revenue_periods,
            latest.get("period_end"), latest.get("currency"),
            latest.get("revenue"), latest_number,
        )
    if valid:
        _, record, revenue, number = max(valid, key=lambda item: item[0])
        return (
            len(records), revenue_periods,
            record.get("period_to_resolved") or record.get("sf_period_to"),
            record.get("currency"), revenue, number,
        )
    return len(records), revenue_periods, None, None, None, None


def _compress(value: object) -> bytes:
    return zlib.compress(dumps(value).encode("utf-8"), level=6)


def decompress_json(blob: bytes) -> dict:
    return simplejson.loads(zlib.decompress(blob), use_decimal=True)


def iter_json_array(path: Path, *, chunk_size: int = 1024 * 1024) -> Iterator[dict]:
    """Stream a top-level JSON array without loading a multi-GB file into RAM."""
    decoder = simplejson.JSONDecoder(parse_float=Decimal, object_pairs_hook=no_duplicate_keys)
    with path.open("r", encoding="utf-8") as source:
        buffer = ""
        position = 0
        started = False
        finished = False
        eof = False
        while not finished:
            if position >= len(buffer) and not eof:
                buffer = source.read(chunk_size)
                position = 0
                eof = not buffer
            while position < len(buffer) and buffer[position].isspace():
                position += 1
            if not started:
                if position >= len(buffer):
                    if eof:
                        raise ValueError("Pusty plik JSON")
                    continue
                if buffer[position] != "[":
                    raise ValueError("Oczekiwano tablicy JSON")
                position += 1
                started = True
                continue

            while True:
                while position < len(buffer) and (buffer[position].isspace() or buffer[position] == ","):
                    position += 1
                if position < len(buffer):
                    break
                if eof:
                    raise ValueError("Nieoczekiwany koniec tablicy JSON")
                buffer = source.read(chunk_size)
                position = 0
                eof = not buffer
            if buffer[position] == "]":
                position += 1
                finished = True
                continue

            while True:
                try:
                    value, end = decoder.raw_decode(buffer, position)
                    break
                except simplejson.JSONDecodeError:
                    if eof:
                        raise
                    # Keep only the unparsed object and append the next chunk.
                    buffer = buffer[position:] + source.read(chunk_size)
                    position = 0
                    eof = source.tell() == path.stat().st_size
            if not isinstance(value, dict):
                raise ValueError("Każdy element zbioru profili musi być obiektem JSON")
            yield value
            buffer = buffer[end:]
            position = 0


def latest_collection_dir(root: Path | None = None) -> Path:
    base = root or ROOT / "data" / "profiles"
    candidates = [
        path for path in base.iterdir()
        if path.is_dir() and (path / "summary.json").is_file() and (path / "screening.json").is_file()
    ] if base.is_dir() else []
    if not candidates:
        raise FileNotFoundError(f"Brak opublikowanych profili w {base}")
    return max(candidates, key=lambda path: (path / "summary.json").stat().st_mtime_ns)


def build_database(collection_dir: Path | None = None, target: Path | None = None) -> dict:
    collection_dir = (collection_dir or latest_collection_dir()).resolve()
    target = (target or database_path()).resolve()
    source = collection_dir / "screening.json"
    summary_path = collection_dir / "summary.json"
    summary = simplejson.loads(summary_path.read_bytes(), use_decimal=True)
    collection_id = collection_dir.name
    expected = int(summary.get("profiles") or 0)
    created_at = datetime.fromtimestamp(summary_path.stat().st_mtime, timezone.utc).isoformat()

    target.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix="company-lab-", suffix=".sqlite3", dir=target.parent
    )
    os.close(descriptor)
    temporary = Path(temporary_name)
    count = 0
    try:
        with connect(temporary, readonly=False) as conn:
            conn.executescript("""
                PRAGMA journal_mode=DELETE;
                PRAGMA synchronous=NORMAL;
                PRAGMA temp_store=MEMORY;
                PRAGMA page_size=4096;
                CREATE TABLE profile_collection (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    rule_version TEXT NOT NULL,
                    summary_json TEXT NOT NULL,
                    source_path TEXT NOT NULL,
                    source_size INTEGER NOT NULL,
                    source_mtime_ns INTEGER NOT NULL
                );
                CREATE TABLE profile_screening (
                    collection_id TEXT NOT NULL,
                    krs TEXT NOT NULL,
                    name TEXT,
                    city TEXT,
                    region TEXT,
                    status TEXT NOT NULL,
                    segment TEXT NOT NULL,
                    name_signal INTEGER NOT NULL,
                    search_text TEXT NOT NULL,
                    summary_text TEXT,
                    primary_pkd TEXT,
                    primary_pkd_description TEXT,
                    screening_reason TEXT,
                    latest_period TEXT,
                    latest_currency TEXT,
                    latest_revenue_text TEXT,
                    latest_revenue_number REAL,
                    financial_periods INTEGER NOT NULL,
                    financial_revenue_periods INTEGER NOT NULL,
                    catalog_json_zlib BLOB NOT NULL,
                    profile_json_zlib BLOB NOT NULL,
                    PRIMARY KEY (collection_id, krs),
                    FOREIGN KEY (collection_id) REFERENCES profile_collection(id)
                );
                CREATE INDEX idx_profile_status_segment ON profile_screening(collection_id, status, segment);
                CREATE INDEX idx_profile_name ON profile_screening(collection_id, name COLLATE NOCASE);
                CREATE INDEX idx_profile_revenue ON profile_screening(collection_id, latest_revenue_number);
                CREATE INDEX idx_profile_period ON profile_screening(collection_id, latest_period);
            """)
            conn.execute(
                "INSERT INTO profile_collection VALUES (?,?,?,?,?,?,?)",
                (
                    collection_id, created_at, str(summary.get("rule_version") or ""),
                    dumps(summary), str(source), source.stat().st_size, source.stat().st_mtime_ns,
                ),
            )
            insert = """INSERT INTO profile_screening (
                collection_id,krs,name,city,region,status,segment,name_signal,
                search_text,summary_text,primary_pkd,primary_pkd_description,
                screening_reason,latest_period,latest_currency,latest_revenue_text,
                latest_revenue_number,financial_periods,financial_revenue_periods,
                catalog_json_zlib,profile_json_zlib
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"""
            for profile in iter_json_array(source):
                krs = str(profile.get("krs") or "")
                screening = profile.get("screening")
                screening = screening if isinstance(screening, dict) else {}
                financial = _latest_financial(profile)
                primary = profile.get("primary_pkd")
                primary = primary if isinstance(primary, dict) else {}
                catalog = {key: value for key, value in profile.items() if key not in CATALOG_OMIT}
                catalog["financial_history"] = {
                    "periods": financial[0],
                    "revenue_periods": financial[1],
                    "latest_revenue_period": financial[2],
                    "latest_revenue_currency": financial[3],
                    "latest_revenue": financial[4],
                }
                summary_text = profile.get("summary")
                search = normalize_search(" ".join(str(value or "") for value in (
                    krs, profile.get("name"), profile.get("city"), summary_text,
                )))
                conn.execute(insert, (
                    collection_id, krs, profile.get("name"), profile.get("city"),
                    profile.get("region"), screening.get("status") or "missing_summary",
                    screening.get("segment") or "unknown", int(bool(screening.get("name_signal"))),
                    search, summary_text, primary.get("code"), primary.get("description"),
                    screening.get("reason"), financial[2], financial[3],
                    None if financial[4] is None else str(financial[4]), financial[5],
                    financial[0], financial[1], _compress(catalog), _compress(profile),
                ))
                count += 1
                if count % 250 == 0:
                    conn.commit()
                    print(f"SQLite: zapisano {count}/{expected or '?'} profili", flush=True)
            conn.commit()
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
            if result != "ok":
                raise RuntimeError(f"Kontrola SQLite nie powiodła się: {result}")
        if expected and count != expected:
            raise RuntimeError(f"Oczekiwano {expected} profili, zapisano {count}")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)
    from backend.profile_enrichment import enrich_database
    enrich_database(target, publish=target==database_path().resolve())
    return {
        "path": str(target), "collection_id": collection_id, "profiles": count,
        "size_bytes": target.stat().st_size, "source_size_bytes": source.stat().st_size,
    }


def list_collections() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(
            "SELECT id,created_at,rule_version,summary_json FROM profile_collection ORDER BY created_at DESC,id DESC"
        ).fetchall()
    result = [{"id": row["id"], "created_at": row["created_at"], "rule_version": row["rule_version"],
               "summary": simplejson.loads(row["summary_json"], use_decimal=True)} for row in rows]
    with connect() as conn:
        has_new = 'business_type' in {r['name'] for r in conn.execute('PRAGMA table_info(profile_screening)')}
        if has_new:
            for item in result:
                item['summary']['business_counts'] = {r[0]:r[1] for r in conn.execute('SELECT business_type,count(*) FROM profile_screening WHERE collection_id=? GROUP BY business_type',(item['id'],)) if r[0]}
    return result


def require_collection(collection: str) -> None:
    with connect() as conn:
        exists = conn.execute("SELECT 1 FROM profile_collection WHERE id=?", (collection,)).fetchone()
    if not exists:
        raise KeyError(collection)


def filter_clauses(collection, *, q='', status='all', segment='all', city='', region='', county='', municipality='', business_type='all', activity='all', revenue_min=None, revenue_max=None, profit_min=None, profit_max=None):
    clauses = ["collection_id=?"]
    params: list[object] = [collection]
    if status == "name_signal":
        clauses.extend(["status='missing_summary'", "name_signal=1"])
    elif status != "all":
        clauses.append("status=?")
        params.append(status)
    if segment != "all":
        clauses.append("segment=?")
        params.append(segment)
    normalized = normalize_search(q).strip()
    if normalized:
        clauses.append("instr(search_text, ?) > 0")
        params.append(normalized)
    if city == '__missing__':
        clauses.append("(geo_norm(city)='' OR geo_norm(region)='')")
    else:
        if city:
            cities = [c.strip() for c in city.split(',') if c.strip()]
            if len(cities) == 1:
                clauses.append("geo_norm(city)=?")
                params.append(normalize_search(cities[0]).strip())
            elif len(cities) > 1:
                placeholders = ','.join('?' for _ in cities)
                clauses.append(f"geo_norm(city) IN ({placeholders})")
                params.extend(normalize_search(c).strip() for c in cities)
        if region:
            regions = [r.strip() for r in region.split(',') if r.strip()]
            if len(regions) == 1:
                clauses.append("geo_norm(region)=?")
                params.append(normalize_search(regions[0]).strip())
            elif len(regions) > 1:
                placeholders = ','.join('?' for _ in regions)
                clauses.append(f"geo_norm(region) IN ({placeholders})")
                params.extend(normalize_search(r).strip() for r in regions)
        if county:
            counties = [c.strip() for c in county.split(',') if c.strip()]
            if len(counties) == 1:
                c_norm = normalize_search(counties[0]).strip()
                clauses.append("(geo_norm(county)=? OR instr(geo_norm(county), ?)>0 OR instr(?, geo_norm(county))>0)")
                params.extend([c_norm, c_norm, c_norm])
            elif len(counties) > 1:
                c_clauses = []
                for c in counties:
                    c_norm = normalize_search(c).strip()
                    c_clauses.append("(geo_norm(county)=? OR instr(geo_norm(county), ?)>0 OR instr(?, geo_norm(county))>0)")
                    params.extend([c_norm, c_norm, c_norm])
                clauses.append(f"({' OR '.join(c_clauses)})")
        if municipality:
            municipalities = [m.strip() for m in municipality.split(',') if m.strip()]
            if len(municipalities) == 1:
                m_norm = normalize_search(municipalities[0]).strip()
                clauses.append("(geo_norm(municipality)=? OR instr(geo_norm(municipality), ?)>0 OR instr(?, geo_norm(municipality))>0)")
                params.extend([m_norm, m_norm, m_norm])
            elif len(municipalities) > 1:
                m_clauses = []
                for m in municipalities:
                    m_norm = normalize_search(m).strip()
                    m_clauses.append("(geo_norm(municipality)=? OR instr(geo_norm(municipality), ?)>0 OR instr(?, geo_norm(municipality))>0)")
                    params.extend([m_norm, m_norm, m_norm])
                clauses.append(f"({' OR '.join(m_clauses)})")
    if business_type != 'all':
        clauses.append("business_type=?")
        params.append(business_type)
    if activity != 'all':
        clauses.append("is_active=?")
        params.append(1 if activity=='active' else 0)
    for field, low, high in [('annual_revenue',revenue_min,revenue_max),('annual_profit',profit_min,profit_max)]:
        if low is not None:
            clauses.append(field+'>=?'); params.append(low)
        if high is not None:
            clauses.append(field+'<=?'); params.append(high)
    return clauses, params


def catalog(
    collection: str, *, q: str, status: str, segment: str, sort: str,
    direction: str, limit: int, offset: int, city: str = "", region: str = "",
    county: str = "", municipality: str = "", **filters,
) -> dict:
    clauses, params = filter_clauses(collection, q=q, status=status, segment=segment, city=city, region=region, county=county, municipality=municipality, **filters)
    where = " WHERE " + " AND ".join(clauses)
    order_column = {
        "krs": "krs", "name": "name COLLATE NOCASE",
        "revenue": "latest_revenue_number", "year": "latest_period",
    }[sort]
    order = "DESC" if direction == "desc" else "ASC"
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM profile_collection WHERE id=?", (collection,)).fetchone():
            raise KeyError(collection)
        total = conn.execute("SELECT count(*) AS total FROM profile_screening" + where, params).fetchone()["total"]
        rows = conn.execute(
            "SELECT catalog_json_zlib FROM profile_screening" + where
            + f" ORDER BY ({order_column}) IS NULL, {order_column} {order}, krs ASC LIMIT ? OFFSET ?",
            [*params, limit, offset],
        ).fetchall()
    return {
        "items": [decompress_json(row["catalog_json_zlib"]) for row in rows],
        "total": total, "limit": limit, "offset": offset, "sort": sort, "direction": direction,
    }


def export_rows(collection: str, *, q: str, status: str, segment: str, city: str = "", region: str = "", county: str = "", municipality: str = "", **filters) -> list[dict]:
    clauses, params = filter_clauses(collection, q=q, status=status, segment=segment, city=city, region=region, county=county, municipality=municipality, **filters)
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM profile_collection WHERE id=?", (collection,)).fetchone():
            raise KeyError(collection)
        rows = conn.execute(
            """SELECT krs,name,city,region,status,primary_pkd,primary_pkd_description,
                      latest_period,latest_currency,latest_revenue_text AS revenue,
                      segment,name_signal,screening_reason,business_type,is_active,annual_period,annual_revenue,annual_profit,classification_json
               FROM profile_screening WHERE """ + " AND ".join(clauses) + " ORDER BY krs",
            params,
        ).fetchall()
    return [dict(row) for row in rows]



def profile_detail(collection: str, krs: str) -> dict | None:
    with connect() as conn:
        if not conn.execute("SELECT 1 FROM profile_collection WHERE id=?", (collection,)).fetchone():
            raise KeyError(collection)
        row = conn.execute(
            "SELECT profile_json_zlib FROM profile_screening WHERE collection_id=? AND krs=?",
            (collection, krs),
        ).fetchone()
    if not row:
        return None
    profile = decompress_json(row['profile_json_zlib'])
    from etl.business_classification import classify_profile
    profile['classification'] = classify_profile(profile)
    return profile


def status() -> dict:
    path = database_path()
    with connect(path) as conn:
        collection = conn.execute(
            "SELECT id,source_path,source_size FROM profile_collection ORDER BY created_at DESC LIMIT 1"
        ).fetchone()
        profiles = conn.execute("SELECT count(*) AS count FROM profile_screening").fetchone()["count"]
        integrity = conn.execute("PRAGMA quick_check").fetchone()[0]
    return {
        "path": str(path), "size_bytes": path.stat().st_size, "profiles": profiles,
        "collection_id": collection["id"], "source_path": collection["source_path"],
        "source_size_bytes": collection["source_size"], "integrity": integrity,
    }
