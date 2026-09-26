"""Google Gemini API integration with Google Search Grounding for developer verification."""
import os
import re
import logging
from typing import Any
import httpx

logger = logging.getLogger(__name__)

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")
FALLBACK_MODELS = ["gemini-flash-latest", "gemini-flash-lite-latest", "gemini-3.5-flash"]


def get_api_key(passed_key: str | None = None) -> str | None:
    """Resolve Gemini API key from explicit argument, .env, or system environment."""
    if passed_key and passed_key.strip():
        return passed_key.strip()
    key = os.getenv("GEMINI_API_KEY")
    if key and key.strip():
        return key.strip()
    # Check .env file in workspace root
    env_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if os.path.isfile(env_file):
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("GEMINI_API_KEY="):
                        val = line.split("=", 1)[1].strip().strip('"\'')
                        if val:
                            return val
        except Exception as exc:
            logger.warning("Nie udało się odczytać .env: %s", exc)
    return None


def format_company_prompt(company: dict[str, Any]) -> str:
    """Format prompt for Gemini to check if company is a real estate developer."""
    name = company.get("name") or company.get("company_name") or "Nieznana"
    krs = company.get("krs") or ""
    nip = company.get("nip") or ""

    # Address / city
    address = company.get("address") or {}
    if isinstance(address, dict):
        city = address.get("city") or company.get("city") or ""
        street = address.get("street") or ""
        postal = address.get("postal_code") or ""
        full_address = f"{street}, {postal} {city}".strip(", ")
    else:
        city = company.get("city") or str(address)
        full_address = str(address)

    # PKD / activity description
    pkd = company.get("primary_pkd") or ""
    pkd_desc = company.get("primary_pkd_description") or ""
    screening = company.get("screening") or {}
    screening_desc = ""
    if isinstance(screening, dict):
        screening_desc = screening.get("reason") or screening.get("status") or ""

    summary_text = company.get("summary") or ""
    if isinstance(summary_text, dict):
        summary_text = summary_text.get("note") or ""

    return f"""Jesteś precyzyjnym analitykiem rynku nieruchomości i budownictwa w Polsce.
Twoim zadaniem jest sprawdzenie, czy poniższa firma prowadzi działalność jako deweloper nieruchomości (tzn. buduje, realizuje lub sprzedaje mieszkania, domy, osiedla mieszkaniowe lub obiekty komercyjne).

Dane firmy do weryfikacji:
- Nazwa: {name}
- KRS: {krs}
- NIP: {nip}
- Siedziba / Miejscowość: {city or full_address}
- PKD: {pkd} {pkd_desc}
- Informacje wstępne: {screening_desc or summary_text}

Instrukcje:
1. Zbadaj profil działalności firmy, jej inwestycje mieszkaniowe/komercyjne, zrealizowane projekty lub profil rynkowy.
2. Zwróć uwagę na odróżnienie dewelopera (inwestor budujący/sprzedający lokale) od podwykonawcy budowlanego (np. roboty ziemne, usługi remontowe) lub biura projektowego/pośrednika.
3. Przedstaw odpowiedź w poniższym formacie:

WERDYKT: [TAK / NIE / NIEPEWNE]
CZY_DEWELOPER: [PRAWDA / FAŁSZ / NIEZNANE]
PEWNOŚĆ: [WYSOKA / ŚREDNIA / NISKA]
PODSUMOWANIE: [Jedno lub dwa zwięzłe zdania podsumowujące, np. 'Tak, Pro-Bud prowadzi działalność deweloperską realizując inwestycje mieszkaniowe...']
SZCZEGÓŁY:
- [Konkretny punkt 1, np. zrealizowane inwestycje, profil działalności, miasta]
- [Konkretny punkt 2, np. czy to deweloper, SPV, wykonawca budowlany czy inna branża]
- [Opcjonalny punkt 3, np. dodatkowe uwagi lub powiązania]
"""


def parse_gemini_response(data: dict[str, Any]) -> dict[str, Any]:
    """Extract structured verdict, text, and grounding metadata from Gemini response."""
    candidates = data.get("candidates") or []
    if not candidates:
        raise ValueError("Model Gemini nie zwrócił żadnej odpowiedzi (brak kandydatów).")

    candidate = candidates[0]
    content = candidate.get("content") or {}
    parts = content.get("parts") or []
    raw_text = "".join(part.get("text", "") for part in parts if isinstance(part, dict))

    # Parse grounding metadata
    grounding = candidate.get("groundingMetadata") or {}
    search_queries = grounding.get("webSearchQueries") or []
    chunks = grounding.get("groundingChunks") or []

    sources = []
    seen_urls = set()
    for chunk in chunks:
        web = chunk.get("web") or {}
        uri = web.get("uri") or ""
        title = web.get("title") or uri
        if uri and uri not in seen_urls:
            seen_urls.add(uri)
            sources.append({"title": title, "url": uri})

    # Parse structured fields from text
    verdict = "NIEPEWNE"
    is_developer = None
    confidence = "ŚREDNIA"
    summary = ""
    details: list[str] = []

    # Regex search for fields (tolerant to markdown bold/asterisks)
    v_match = re.search(r"\*{0,2}WERDYKT:\*{0,2}\s*\[?(TAK|NIE|NIEPEWNE)\]?", raw_text, re.IGNORECASE)
    if v_match:
        val = v_match.group(1).upper()
        verdict = val
        if val == "TAK":
            is_developer = True
        elif val == "NIE":
            is_developer = False
        else:
            is_developer = None

    dev_match = re.search(r"\*{0,2}CZY_DEWELOPER:\*{0,2}\s*\[?(PRAWDA|FAŁSZ|NIEZNANE)\]?", raw_text, re.IGNORECASE)
    if dev_match:
        val = dev_match.group(1).upper()
        if val == "PRAWDA":
            is_developer = True
        elif val == "FAŁSZ":
            is_developer = False

    conf_match = re.search(r"\*{0,2}PEWNOŚĆ:\*{0,2}\s*\[?(WYSOKA|ŚREDNIA|NISKA)\]?", raw_text, re.IGNORECASE)
    if conf_match:
        confidence = conf_match.group(1).upper()

    sum_match = re.search(r"\*{0,2}PODSUMOWANIE:\*{0,2}\s*([^\n]+)", raw_text, re.IGNORECASE)
    if sum_match and sum_match.group(1).strip():
        summary = sum_match.group(1).strip()
    else:
        # Fallback summary: first non-empty line that isn't a header or key
        for line in raw_text.splitlines():
            clean = line.strip().strip("*").strip()
            if clean and not any(clean.upper().startswith(k) for k in ("WERDYKT", "CZY_DEWELOPER", "PEWNOŚĆ", "PODSUMOWANIE", "SZCZEGÓŁY", "#")):
                summary = clean
                break

    # Extract bullet points (ignore bullet points that are actually keys like *WERDYKT: or *CZY_DEWELOPER:)
    detail_lines = re.findall(r"^\s*[-•*]\s*(.+)$", raw_text, re.MULTILINE)
    if detail_lines:
        for line in detail_lines:
            clean = line.strip().strip("*").strip()
            if clean and not any(clean.upper().startswith(k) for k in ("WERDYKT", "CZY_DEWELOPER", "PEWNOŚĆ", "PODSUMOWANIE", "SZCZEGÓŁY")):
                details.append(line.strip())

    return {
        "verdict": verdict,
        "is_developer": is_developer,
        "confidence": confidence,
        "summary": summary,
        "details": details,
        "sources": sources,
        "search_queries": search_queries,
        "raw_text": raw_text,
    }


_grounding_disabled = False


def verify_company(company: dict[str, Any], api_key: str | None = None, model: str = DEFAULT_MODEL, use_search: bool = True) -> dict[str, Any]:
    """Execute Gemini API query to verify company with Google Search Grounding or direct knowledge fallback."""
    global _grounding_disabled
    resolved_key = get_api_key(api_key)
    if not resolved_key:
        raise ValueError(
            "Brak klucza Gemini API. Pobierz bezpłatny klucz w Google AI Studio "
            "(https://aistudio.google.com/) i skonfiguruj go w aplikacji."
        )

    prompt = format_company_prompt(company)
    models_to_try = [model] + [m for m in FALLBACK_MODELS if m != model]

    # Mode 1: Try with Google Search Grounding first (if enabled and not previously exhausted)
    if use_search and not _grounding_disabled:
        for m in models_to_try:
            url = GEMINI_API_URL.format(model=m)
            payload = {
                "contents": [{"parts": [{"text": prompt}]}],
                "tools": [{"googleSearch": {}}],
            }
            try:
                with httpx.Client(timeout=25.0) as client:
                    resp = client.post(
                        url,
                        params={"key": resolved_key},
                        json=payload,
                        headers={"Content-Type": "application/json"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        result = parse_gemini_response(data)
                        result["model_used"] = f"{m} (Google Search)"
                        return result

                    # Check if invalid key
                    if resp.status_code == 403:
                        err_msg = resp.json().get("error", {}).get("message", "Nieprawidłowy klucz")
                        raise ValueError(f"Nieprawidłowy klucz Gemini API lub brak uprawnień: {err_msg}")

                    # If 429 on Search tool, disable search for future calls to preserve free-tier quota
                    if resp.status_code == 429:
                        _grounding_disabled = True
                        break
            except ValueError:
                raise
            except Exception as exc:
                logger.debug("Search Grounding niedostępne dla %s: %s", m, exc)

    # Mode 2: Direct model reasoning without search tool (free tier friendly)
    last_error: Exception | None = None
    for m in models_to_try:
        url = GEMINI_API_URL.format(model=m)
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
        }
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    url,
                    params={"key": resolved_key},
                    json=payload,
                    headers={"Content-Type": "application/json"},
                )
                if resp.status_code == 200:
                    data = resp.json()
                    result = parse_gemini_response(data)
                    result["model_used"] = f"{m} (Analiza AI)"
                    return result

                err_body = resp.text
                if resp.status_code == 403:
                    err_msg = resp.json().get("error", {}).get("message", "Nieprawidłowy klucz")
                    raise ValueError(f"Nieprawidłowy klucz Gemini API: {err_msg}")

                logger.warning("Błąd modelu %s: %d, treść: %s", m, resp.status_code, err_body[:200])
                last_error = ValueError(f"Błąd Gemini API ({m}): status {resp.status_code}")
        except ValueError:
            raise
        except Exception as exc:
            last_error = exc
            logger.warning("Wyjątek modelu %s: %s", m, exc)

    if last_error:
        raise last_error
    raise RuntimeError("Nie udało się uzyskać odpowiedzi z żadnego modelu Gemini.")
