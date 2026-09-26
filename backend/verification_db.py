"""Database persistence for AI and manual company verifications in SQLite."""
from __future__ import annotations
import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any
from backend.local_profiles import database_path

logger = logging.getLogger(__name__)


def _refresh_dependants(krs: str, status: str | None) -> None:
    """Make filters and live aggregations observe a decision immediately."""
    try:
        from backend.financial_map import set_verification_status
        set_verification_status(krs, status)
    except (FileNotFoundError, OSError, sqlite3.DatabaseError) as exc:
        logger.warning("Nie udało się zsynchronizować weryfikacji z mapą: %s", exc)
    try:
        from backend.cache import invalidate
        invalidate("cl:*")
    except Exception as exc:
        logger.debug("Nie udało się wyczyścić cache po weryfikacji: %s", exc)


def get_connection() -> sqlite3.Connection:
    path = database_path()
    conn = sqlite3.connect(path, timeout=15.0)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.row_factory = sqlite3.Row
    return conn


def init_verification_table():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS company_verification (
                krs TEXT PRIMARY KEY,
                collection_id TEXT,
                status TEXT NOT NULL, -- 'confirmed' | 'rejected' | 'review'
                source TEXT NOT NULL, -- 'gemini' | 'user'
                verdict TEXT,         -- 'TAK' | 'NIE' | 'NIEPEWNE'
                confidence TEXT,
                summary TEXT,
                details_json TEXT,
                sources_json TEXT,
                raw_text TEXT,
                model_used TEXT,
                updated_at TEXT NOT NULL
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_comp_verif_status ON company_verification(status)")


def save_gemini_verification(krs: str, collection_id: str | None, result: dict[str, Any]) -> dict[str, Any]:
    init_verification_table()
    is_dev = result.get("is_developer")
    status = "confirmed" if is_dev is True else "rejected" if is_dev is False else "review"
    now_iso = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        conn.execute("""
            INSERT INTO company_verification (
                krs, collection_id, status, source, verdict, confidence,
                summary, details_json, sources_json, raw_text, model_used, updated_at
            ) VALUES (?, ?, ?, 'gemini', ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(krs) DO UPDATE SET
                collection_id=excluded.collection_id,
                status=excluded.status,
                source='gemini',
                verdict=excluded.verdict,
                confidence=excluded.confidence,
                summary=excluded.summary,
                details_json=excluded.details_json,
                sources_json=excluded.sources_json,
                raw_text=excluded.raw_text,
                model_used=excluded.model_used,
                updated_at=excluded.updated_at
        """, (
            krs,
            collection_id or "",
            status,
            result.get("verdict"),
            result.get("confidence"),
            result.get("summary"),
            json.dumps(result.get("details") or [], ensure_ascii=False),
            json.dumps(result.get("sources") or [], ensure_ascii=False),
            result.get("raw_text") or "",
            result.get("model_used") or "",
            now_iso,
        ))
    _refresh_dependants(krs, status)
    ret = get_verification(krs)
    return ret or {}


def save_user_verification(krs: str, status: str | None, notes: str | None = None) -> dict[str, Any] | None:
    init_verification_table()
    if not status:
        with get_connection() as conn:
            conn.execute("DELETE FROM company_verification WHERE krs=?", (krs,))
        _refresh_dependants(krs, None)
        return None

    now_iso = datetime.now(timezone.utc).isoformat()
    with get_connection() as conn:
        existing = conn.execute("SELECT * FROM company_verification WHERE krs=?", (krs,)).fetchone()
        if existing:
            conn.execute("""
                UPDATE company_verification 
                SET status=?, source='user', updated_at=?
                WHERE krs=?
            """, (status, now_iso, krs))
        else:
            conn.execute("""
                INSERT INTO company_verification (krs, status, source, updated_at)
                VALUES (?, ?, 'user', ?)
            """, (krs, status, now_iso))
    _refresh_dependants(krs, status)
    return get_verification(krs)


def get_verification(krs: str) -> dict[str, Any] | None:
    init_verification_table()
    with get_connection() as conn:
        row = conn.execute("SELECT * FROM company_verification WHERE krs=?", (krs,)).fetchone()
        if not row:
            return None
        d = dict(row)
        if d.get("details_json"):
            try:
                d["details"] = json.loads(d["details_json"])
            except Exception:
                d["details"] = []
        else:
            d["details"] = []
        if d.get("sources_json"):
            try:
                d["sources"] = json.loads(d["sources_json"])
            except Exception:
                d["sources"] = []
        else:
            d["sources"] = []
        return d


def list_verifications() -> dict[str, dict[str, Any]]:
    init_verification_table()
    with get_connection() as conn:
        rows = conn.execute("SELECT * FROM company_verification").fetchall()
        result = {}
        for r in rows:
            d = dict(r)
            if d.get("details_json"):
                try:
                    d["details"] = json.loads(d["details_json"])
                except Exception:
                    d["details"] = []
            else:
                d["details"] = []
            if d.get("sources_json"):
                try:
                    d["sources"] = json.loads(d["sources_json"])
                except Exception:
                    d["sources"] = []
            else:
                d["sources"] = []
            result[d["krs"]] = d
        return result
