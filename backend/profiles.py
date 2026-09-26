"""Read-only profile endpoints backed by the local compressed SQLite index."""
from typing import Literal
from uuid import UUID
import csv
import io

import simplejson
from fastapi import APIRouter, HTTPException, Query, Depends, Header, Body
from fastapi.responses import Response, JSONResponse

from backend import local_profiles
from backend.cache import cached_response, redis_available
from backend.gemini_grounding import verify_company, get_api_key
from backend.verification_db import (
    save_gemini_verification,
    save_user_verification,
    get_verification,
    list_verifications,
)


class DecimalJSONResponse(JSONResponse):
    """JSONResponse subclass that handles Decimal via simplejson."""
    def render(self, content) -> bytes:
        return simplejson.dumps(
            content, use_decimal=True, ensure_ascii=False,
        ).encode("utf-8")


router = APIRouter(prefix="/api/profiles")


def unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        503,
        "Lokalna baza SQLite nie jest jeszcze gotowa. Uruchom: "
        ".venv\\Scripts\\python.exe scripts\\build_sqlite.py",
    )



def extra_filters(
    business_type: Literal['all','developer','spv','contractor','other','review','needs_web_grounding']='all',
    activity: Literal['all','active','inactive']='all',
    verification: Literal['all','verified','confirmed','rejected','unverified']='all',
    revenue_min: float | None=Query(None,allow_inf_nan=False), revenue_max: float | None=Query(None,allow_inf_nan=False),
    profit_min: float | None=Query(None,allow_inf_nan=False), profit_max: float | None=Query(None,allow_inf_nan=False),
):
    for low,high in [(revenue_min,revenue_max),(profit_min,profit_max)]:
        if low is not None and high is not None and low>high:
            raise HTTPException(422,'Dolna granica nie może być większa od górnej.')
    return dict(business_type=business_type,activity=activity,verification=verification,revenue_min=revenue_min,revenue_max=revenue_max,profit_min=profit_min,profit_max=profit_max)

@router.get("/collections")
def collections():
    try:
        return local_profiles.list_collections()
    except (FileNotFoundError, OSError) as exc:
        raise unavailable(exc) from exc


@router.get("")
def catalog(
    collection: UUID,
    filters: dict = Depends(extra_filters),
    q: str = Query("", max_length=120),
    city: str = Query("", max_length=180),
    region: str = Query("", max_length=100),
    county: str = Query("", max_length=100),
    municipality: str = Query("", max_length=100),
    status: Literal[
        "developer_candidate", "other_activity", "review", "missing_summary", "name_signal", "all"
    ] = "developer_candidate",
    segment: Literal["all", "residential", "commercial", "mixed", "unknown"] = "all",
    sort: Literal["krs", "name", "revenue", "year"] = "krs",
    direction: Literal["asc", "desc"] = "asc",
    limit: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0, le=100000),
):
    try:
        params = dict(
            collection=str(collection), q=q, status=status, segment=segment,
            sort=sort, direction=direction, limit=limit, offset=offset,
            city=city, region=region, county=county, municipality=municipality,
            **filters,
        )
        result, from_cache = cached_response(
            "profiles", params,
            lambda: local_profiles.catalog(
                str(collection), q=q, status=status, segment=segment,
                sort=sort, direction=direction, limit=limit, offset=offset,
                city=city, region=region, county=county, municipality=municipality,
                **filters,
            ),
        )
        response = DecimalJSONResponse(content=result)
        response.headers["X-Cache"] = "HIT" if from_cache else "MISS"
        return response
    except KeyError as exc:
        raise HTTPException(404, "Nie znaleziono zbioru profili") from exc
    except (FileNotFoundError, OSError) as exc:
        raise unavailable(exc) from exc


@router.get("/export.csv")
def export_catalog(
    collection: UUID,
    filters: dict = Depends(extra_filters),
    q: str = Query("", max_length=120),
    city: str = Query("", max_length=180),
    region: str = Query("", max_length=100),
    county: str = Query("", max_length=100),
    municipality: str = Query("", max_length=100),
    status: Literal[
        "developer_candidate", "other_activity", "review", "missing_summary", "name_signal", "all"
    ] = "developer_candidate",
    segment: Literal["all", "residential", "commercial", "mixed", "unknown"] = "all",
):
    try:
        rows = local_profiles.export_rows(
            str(collection), q=q, status=status, segment=segment, city=city, region=region,
            county=county, municipality=municipality, **filters
        )
    except KeyError as exc:
        raise HTTPException(404, "Nie znaleziono zbioru profili") from exc
    except (FileNotFoundError, OSError) as exc:
        raise unavailable(exc) from exc

    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerow([
        "KRS", "Nazwa", "Miasto", "Województwo", "Status", "PKD główne",
        "Opis PKD", "Ostatni okres", "Waluta", "Przychód", "Segment",
        "Sygnał nazwy", "Uzasadnienie", "Nowa klasyfikacja", "Aktywna", "Pełny rok PLN", "Przychód roczny PLN", "Zysk roczny PLN", "Reguły i dowody", "Weryfikacja",
    ])
    for row in rows:
        writer.writerow([
            row.get(key) for key in (
                "krs", "name", "city", "region", "status", "primary_pkd",
                "primary_pkd_description", "latest_period", "latest_currency",
                "revenue", "segment", "name_signal", "screening_reason", "business_type", "is_active", "annual_period", "annual_revenue", "annual_profit", "classification_json", "verification_status",
            )
        ])
    return Response(
        output.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="company-lab-profile-export.csv"'},
    )


@router.get("/locations")
def locations(
    collection: UUID,
    filters: dict = Depends(extra_filters),
    q: str = Query("", max_length=120),
    status: Literal["developer_candidate", "other_activity", "review", "missing_summary", "name_signal", "all"] = "all",
    segment: Literal["all", "residential", "commercial", "mixed", "unknown"] = "all",
    county: str = Query("", max_length=100),
    municipality: str = Query("", max_length=100),
):
    from backend.geography import locations as locate
    try:
        params = dict(
            collection=str(collection), q=q, status=status, segment=segment,
            county=county, municipality=municipality, **filters,
        )
        result, from_cache = cached_response(
            "locations", params,
            lambda: locate(
                str(collection), q=q, status=status, segment=segment,
                county=county, municipality=municipality, **filters,
            ),
        )
        response = DecimalJSONResponse(content=result)
        response.headers["X-Cache"] = "HIT" if from_cache else "MISS"
        return response
    except KeyError as exc:
        raise HTTPException(404, "Nie znaleziono zbioru profili") from exc
    except (FileNotFoundError, OSError) as exc:
        raise unavailable(exc) from exc



@router.get('/segmented-research')
def segmented_research():
    import json
    from etl.config import ROOT
    path=ROOT/'data/research/segmented/latest.json'
    if not path.exists():
        raise HTTPException(404,'Nowe badanie nie jest jeszcze gotowe.')
    return json.loads(path.read_text(encoding='utf-8'))


@router.get("/gemini/status")
def gemini_status():
    has_key = bool(get_api_key())
    return {"has_key": has_key}


@router.post("/gemini/key")
def save_gemini_key(payload: dict = Body(...)):
    import os
    from etl.config import ROOT
    key = (payload.get("api_key") or "").strip()
    if not key:
        raise HTTPException(400, "Klucz API nie może być pusty.")
    if not key.startswith("AIza"):
        raise HTTPException(400, "Klucz Gemini API powinien zaczynać się od 'AIza'. Sprawdź poprawność klucza.")

    env_file = ROOT / ".env"
    existing_lines = []
    if env_file.is_file():
        existing_lines = env_file.read_text(encoding="utf-8").splitlines()

    found = False
    new_lines = []
    for line in existing_lines:
        if line.strip().startswith("GEMINI_API_KEY="):
            new_lines.append(f"GEMINI_API_KEY={key}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"GEMINI_API_KEY={key}")

    env_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    os.environ["GEMINI_API_KEY"] = key
    return {"status": "ok", "message": "Klucz Gemini API został pomyślnie zapisany."}


@router.get("/verifications")
def get_all_verifications():
    return list_verifications()


@router.post("/{krs}/verification")
def set_company_verification(krs: str, payload: dict = Body(...)):
    if len(krs) != 10 or not krs.isascii() or not krs.isdigit():
        raise HTTPException(422, "KRS musi zawierać 10 cyfr")
    status = payload.get("status")
    if status not in ("confirmed", "rejected", None):
        raise HTTPException(400, "Nieprawidłowy status: dopuszczalne 'confirmed', 'rejected' lub null")
    notes = payload.get("notes")
    saved = save_user_verification(krs, status, notes)
    return {"krs": krs, "verification": saved}


@router.post("/{krs}/verify-gemini")
def verify_profile_gemini(
    krs: str,
    collection: UUID | None = None,
    x_gemini_key: str | None = Header(None, alias="X-Gemini-Key"),
    payload: dict | None = Body(None),
):
    if len(krs) != 10 or not krs.isascii() or not krs.isdigit():
        raise HTTPException(422, "KRS musi zawierać 10 cyfr")

    # Resolve collection if not provided
    col_str = str(collection) if collection else None
    if not col_str:
        cols = local_profiles.list_collections()
        if cols:
            col_str = cols[0]["id"]
        else:
            raise HTTPException(503, "Brak aktywnych zbiorów danych.")

    try:
        profile = local_profiles.profile_detail(col_str, krs)
        if not profile:
            raise HTTPException(404, "Nie znaleziono firmy o podanym KRS")
    except KeyError as exc:
        raise HTTPException(404, "Nie znaleziono zbioru profili") from exc
    except (FileNotFoundError, OSError) as exc:
        raise unavailable(exc) from exc

    passed_key = None
    if payload and isinstance(payload, dict):
        passed_key = payload.get("api_key")
    if not passed_key and x_gemini_key:
        passed_key = x_gemini_key

    try:
        result = verify_company(profile, api_key=passed_key)
        # Persist Gemini verification to SQLite database
        saved = save_gemini_verification(krs, col_str, result)
        result["saved_verification"] = saved
        return result
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, f"Błąd weryfikacji w Gemini API: {exc}") from exc


@router.get("/{krs}")
def detail(krs: str, collection: UUID):
    if len(krs) != 10 or not krs.isascii() or not krs.isdigit():
        raise HTTPException(422, "KRS musi zawierać 10 cyfr")
    try:
        params = dict(collection=str(collection), krs=krs)
        result, from_cache = cached_response(
            "detail", params,
            lambda: local_profiles.profile_detail(str(collection), krs),
        )
        if result is None:
            raise HTTPException(404, "Firma nie należy do tego zbioru profili")
        # Attach stored verification from SQLite if present
        verif = get_verification(krs)
        if verif:
            result["verification"] = verif
        response = DecimalJSONResponse(content=result)
        response.headers["X-Cache"] = "HIT" if from_cache else "MISS"
        return response
    except KeyError as exc:
        raise HTTPException(404, "Nie znaleziono zbioru profili") from exc
    except (FileNotFoundError, OSError) as exc:
        raise unavailable(exc) from exc
