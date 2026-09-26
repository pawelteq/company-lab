r"""Automated company verification using Google Gemini AI.

Fetches developer verification for companies that have not been checked yet,
respecting the Google Gemini free-tier rate limits:
- 15 requests per minute (paced at ~14 RPM / ~4.3s delay)
- 1500 requests per day (configurable via --limit)
- Starts with companies needing verification ('review' -> 'developer_candidate' -> others)
- Automatically saves results to SQLite (company_verification) so they immediately
  appear in the frontend UI with full details, verdicts, bullet points, and sources.

Usage:
    .venv\Scripts\python.exe -m scripts.auto_verify_gemini
    .venv\Scripts\python.exe -m scripts.auto_verify_gemini --limit 50
    .venv\Scripts\python.exe -m scripts.auto_verify_gemini --status review
    .venv\Scripts\python.exe -m scripts.auto_verify_gemini --county poznanski
    .venv\Scripts\python.exe -m scripts.auto_verify_gemini --dry-run
"""
from __future__ import annotations

import argparse
import logging
import signal
import sqlite3
import sys
import time
from collections import deque
from datetime import datetime
from typing import Any

from backend.cache import invalidate as cache_invalidate
from backend.gemini_grounding import get_api_key, verify_company
from backend.local_profiles import connect as sqlite_connect, list_collections, normalize_search, profile_detail
from backend.verification_db import get_verification, save_gemini_verification

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("auto_verify")

_stop_requested = False


def _signal_handler(signum, frame):
    global _stop_requested
    if not _stop_requested:
        print("\n\n[!] Zatrzymywanie... Kończę bieżące zadanie (Ctrl+C ponownie by wymusić wyjście).")
        _stop_requested = True
    else:
        sys.exit(1)


def fetch_unverified_companies(
    collection_id: str,
    status_filter: str | None = None,
    county_filter: str | None = None,
    limit: int = 1500,
) -> list[dict[str, Any]]:
    """Fetch companies that do NOT exist in company_verification yet.

    Orders them by priority:
    1. 'review' (Do sprawdzenia w UI)
    2. 'developer_candidate' (Kandydaci na dewelopera)
    3. others
    """
    with sqlite_connect(readonly=True) as conn:
        query = """
            SELECT 
                p.krs,
                p.name,
                p.status,
                p.city,
                p.county,
                p.primary_pkd,
                p.primary_pkd_description,
                p.latest_revenue_number,
                CASE p.status
                    WHEN 'review' THEN 1
                    WHEN 'developer_candidate' THEN 2
                    WHEN 'other_activity' THEN 3
                    WHEN 'missing_summary' THEN 4
                    ELSE 5
                END AS priority
            FROM profile_screening p
            LEFT JOIN company_verification v ON p.krs = v.krs
            WHERE p.collection_id = ?
              AND v.krs IS NULL
        """
        params: list[Any] = [collection_id]

        if status_filter and status_filter.lower() != "all":
            query += " AND p.status = ?"
            params.append(status_filter)

        if county_filter and county_filter.strip():
            counties = [c.strip() for c in county_filter.split(",") if c.strip()]
            c_clauses = []
            for c in counties:
                c_norm = normalize_search(c).replace("powiat", "").strip()
                c_clauses.append("(geo_norm(p.county) = ? OR instr(geo_norm(p.county), ?) > 0)")
                params.extend([c_norm, c_norm])
            if c_clauses:
                query += f" AND ({' OR '.join(c_clauses)})"

        query += """
            ORDER BY priority ASC, p.latest_revenue_number DESC NULLS LAST, p.name ASC
            LIMIT ?
        """
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]


class RatePacer:
    """Enforces maximum requests per minute (RPM) using a sliding window."""

    def __init__(self, target_rpm: int = 14, min_delay: float = 4.2):
        self.target_rpm = target_rpm
        self.min_delay = min_delay
        self.timestamps: deque[float] = deque()
        self.last_request_time = 0.0

    def wait(self):
        now = time.time()

        # 1. Enforce minimum delay between calls
        elapsed_since_last = now - self.last_request_time
        if elapsed_since_last < self.min_delay:
            sleep_time = self.min_delay - elapsed_since_last
            time.sleep(sleep_time)
            now = time.time()

        # 2. Enforce sliding window (target_rpm per 60 seconds)
        cutoff = now - 60.0
        while self.timestamps and self.timestamps[0] <= cutoff:
            self.timestamps.popleft()

        if len(self.timestamps) >= self.target_rpm:
            # Wait until oldest timestamp drops out of 60s window
            oldest = self.timestamps[0]
            wait_seconds = max(0.1, (oldest + 60.5) - now)
            logger.info("Limit tempa: oczekiwanie %.1fs na zwolnienie okna 15 RPM...", wait_seconds)
            time.sleep(wait_seconds)
            now = time.time()
            cutoff = now - 60.0
            while self.timestamps and self.timestamps[0] <= cutoff:
                self.timestamps.popleft()

        self.timestamps.append(now)
        self.last_request_time = now


def run_auto_verification(
    limit: int = 1500,
    rpm: int = 14,
    min_delay: float = 4.2,
    status_filter: str | None = None,
    county_filter: str | None = None,
    dry_run: bool = False,
    collection_id: str | None = None,
):
    global _stop_requested
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    signal.signal(signal.SIGINT, _signal_handler)

    # 1. Check API key
    api_key = get_api_key()
    if not api_key:
        logger.error(
            "Brak klucza Gemini API! Ustaw zmienną GEMINI_API_KEY w pliku .env lub środowisku."
        )
        sys.exit(1)

    # 2. Resolve collection
    collections = list_collections()
    if not collections:
        logger.error("Brak aktywnych zbiorów danych w bazie SQLite.")
        sys.exit(1)

    active_col = collection_id or collections[0]["id"]
    logger.info("Używany zbiór danych: %s", active_col)

    # 3. Find candidates
    candidates = fetch_unverified_companies(
        active_col,
        status_filter=status_filter,
        county_filter=county_filter,
        limit=limit,
    )
    total_found = len(candidates)

    if total_found == 0:
        logger.info("Brak firm do weryfikacji spełniających kryteria! Wszystkie firmy są już sprawdzone.")
        return

    filter_desc = []
    if status_filter:
        filter_desc.append(f"status='{status_filter}'")
    if county_filter:
        filter_desc.append(f"powiat='{county_filter}'")
    filter_info = f" [{', '.join(filter_desc)}]" if filter_desc else ""

    logger.info(
        "Znaleziono %d firm do sprawdzenia%s (limit tej sesji: %d, tempo: %d RPM / min_delay=%.1fs)",
        total_found,
        filter_info,
        limit,
        rpm,
        min_delay,
    )

    if dry_run:
        print("\n--- TRYB TESTOWY (DRY-RUN) - Pierwsze 10 firm w kolejce ---")
        for i, c in enumerate(candidates[:10], start=1):
            loc = f"{c.get('city') or ''} ({c.get('county') or ''})".strip()
            print(f"{i:2d}. KRS: {c['krs']} | Status: {c['status']:20s} | {loc:25s} | {c['name'][:40]}")
        print(f"\nŁącznie do sprawdzenia: {total_found} firm. Uruchom bez --dry-run aby rozpocząć.")
        return

    pacer = RatePacer(target_rpm=rpm, min_delay=min_delay)

    stats = {
        "processed": 0,
        "confirmed": 0,
        "rejected": 0,
        "review": 0,
        "errors": 0,
    }

    start_time = time.time()
    print("\n" + "=" * 70)
    print(" ROZPOCZĘTO AUTOMATYCZNĄ WERYFIKACJĘ AI (GEMINI)")
    powiat_banner = f" | Powiat: {county_filter}" if county_filter else ""
    print(f" Kolejka: {total_found} firm{powiat_banner} | Maksymalnie na dobę: {limit} | Pacing: {rpm} RPM")
    print(" Naciśnij Ctrl+C w dowolnym momencie, aby bezpiecznie przerwać.")
    print("=" * 70 + "\n")

    for idx, item in enumerate(candidates, start=1):
        if _stop_requested:
            break

        krs = item["krs"]
        company_name = item.get("name") or "Nieznana"
        orig_status = item.get("status")

        # Double check if already verified in the meantime
        if get_verification(krs):
            logger.info("[%d/%d] KRS %s został już zweryfikowany w bazie — pomijam.", idx, total_found, krs)
            continue

        # Load complete profile
        profile = profile_detail(active_col, krs)
        if not profile:
            logger.warning("[%d/%d] Brak pełnego profilu dla KRS %s", idx, total_found, krs)
            stats["errors"] += 1
            continue

        # Wait according to rate limiter
        pacer.wait()
        if _stop_requested:
            break

        # Execute Gemini verification with retry logic for 429
        max_retries = 3
        result = None
        for attempt in range(1, max_retries + 1):
            try:
                result = verify_company(profile, api_key=api_key)
                break
            except Exception as exc:
                err_str = str(exc)
                if "429" in err_str or "quota" in err_str.lower() or "ResourceExhausted" in err_str:
                    backoff = attempt * 30
                    logger.warning(
                        "Osiągnięto limit Gemini API (429/quota). Odczekuję %d sekund przed ponowieniem (próba %d/%d)...",
                        backoff, attempt, max_retries
                    )
                    time.sleep(backoff)
                else:
                    logger.error("[%d/%d] Błąd dla KRS %s (%s): %s", idx, total_found, krs, company_name[:30], exc)
                    if attempt == max_retries:
                        stats["errors"] += 1
                    time.sleep(2.0)

        if not result:
            continue

        # Save result to SQLite
        try:
            saved = save_gemini_verification(krs, active_col, result)
            stats["processed"] += 1

            verdict = result.get("verdict", "NIEPEWNE")
            is_dev = result.get("is_developer")
            conf = result.get("confidence", "ŚREDNIA")
            summary = result.get("summary", "")

            if is_dev is True:
                stats["confirmed"] += 1
                tag = "[TAK] DEWELOPER"
            elif is_dev is False:
                stats["rejected"] += 1
                tag = "[NIE] INNA BRANZA"
            else:
                stats["review"] += 1
                tag = "[?] NIEPEWNE"

            print(f"[{idx:4d}/{total_found}] KRS {krs} ({company_name[:38]:<38}) -> {tag:<18} [{conf}]")
            if summary:
                print(f"       Opis: {summary[:100]}...")

        except Exception as exc:
            logger.error("Błąd zapisu weryfikacji do SQLite dla KRS %s: %s", krs, exc)
            stats["errors"] += 1

    # Invalidate cache so frontend immediately sees all new verifications
    try:
        cache_invalidate("cl:detail:*")
        cache_invalidate("cl:locations:*")
    except Exception:
        pass

    elapsed = time.time() - start_time
    mins = int(elapsed // 60)
    secs = int(elapsed % 60)

    print("\n" + "=" * 70)
    print(" PODSUMOWANIE PROCESU AUTOMATYCZNEJ WERYFIKACJI")
    print(f" Czas trwania:            {mins}m {secs}s")
    print(f" Przetworzono łącznie:    {stats['processed']}")
    print(f"   - Potwierdzeni (TAK):  {stats['confirmed']}")
    print(f"   - Odrzuceni (NIE):     {stats['rejected']}")
    print(f"   - Niejednoznaczni:     {stats['review']}")
    print(f" Błędy / pominięte:       {stats['errors']}")
    print(" Wszystkie wyniki są zapisane w bazie SQLite i widoczne w interfejsie!")
    print("=" * 70 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Automatyczna weryfikacja firm z Google Gemini AI (15 RPM / 1500 na dobę)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1500,
        help="Maksymalna liczba firm do sprawdzenia w tej sesji (domyślnie 1500)",
    )
    parser.add_argument(
        "--rpm",
        type=int,
        default=14,
        help="Liczba zapytań na minutę (domyślnie 14, by zachować bezpieczny margines poniżej 15 RPM)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=4.2,
        help="Minimalny odstęp w sekundach między zapytaniami (domyślnie 4.2s)",
    )
    parser.add_argument(
        "--status",
        type=str,
        default=None,
        help="Filtr statusu (np. 'review' dla firm 'Do sprawdzenia', 'developer_candidate', lub brak = wszystkie priorytetyzowane)",
    )
    parser.add_argument(
        "--county",
        "--powiat",
        type=str,
        default=None,
        dest="county",
        help="Filtr powiatu (np. 'poznański' lub 'powiat poznański')",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=None,
        help="Identyfikator kolekcji (opcjonalny, domyślnie najnowsza)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Tylko wylistuj pierwsze firmy w kolejce bez wysyłania zapytań do Gemini",
    )

    args = parser.parse_args()
    run_auto_verification(
        limit=args.limit,
        rpm=args.rpm,
        min_delay=args.delay,
        status_filter=args.status,
        county_filter=args.county,
        dry_run=args.dry_run,
        collection_id=args.collection,
    )


if __name__ == "__main__":
    main()
