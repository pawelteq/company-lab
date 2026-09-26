"""HTTP API for the financial atlas."""
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from backend.cache import cached_response
from backend import financial_map


router = APIRouter(prefix="/api/analytics/map", tags=["financial-map"])


def _unavailable(exc: Exception) -> HTTPException:
    return HTTPException(
        503,
        "Indeks mapy finansowej nie jest gotowy. Uruchom: "
        ".venv\\Scripts\\python.exe scripts\\build_financial_map.py",
    )


@router.get("/metadata")
def map_metadata(collection: UUID):
    try:
        params = {"collection": str(collection)}
        result, from_cache = cached_response(
            "financial-map-metadata-v2", params,
            lambda: financial_map.metadata(str(collection)),
            ttl=1800,
        )
        response = JSONResponse(result)
        response.headers["X-Cache"] = "HIT" if from_cache else "MISS"
        return response
    except KeyError as exc:
        raise HTTPException(404, "Nie znaleziono danych finansowych dla tego zbioru") from exc
    except (FileNotFoundError, OSError, ValueError) as exc:
        raise _unavailable(exc) from exc


@router.get("")
def financial_map_data(
    collection: UUID,
    level: Literal["voivodeship", "county", "municipality"] = "voivodeship",
    year: int = Query(..., ge=1900, le=2200),
    metric: str = Query("revenue_total", max_length=80),
    aggregation: str = Query("sum", max_length=40),
    pkd: str = Query("", max_length=20),
    pkd_mode: Literal["primary", "all"] = "primary",
    min_companies: int = Query(5, ge=1, le=500),
    view: Literal["value", "change"] = "value",
    compare_year: int | None = Query(None, ge=1900, le=2200),
):
    if metric not in financial_map.METRICS:
        raise HTTPException(422, "Nieznana metryka finansowa")
    params = dict(
        collection=str(collection), level=level, year=year, metric_id=metric,
        aggregation=aggregation, pkd=pkd, pkd_mode=pkd_mode,
        min_companies=min_companies, view=view, compare_year=compare_year,
    )
    try:
        result, from_cache = cached_response(
            "financial-map-v2", params,
            lambda: financial_map.map_data(**params),
            ttl=1800,
        )
        response = JSONResponse(result)
        response.headers["X-Cache"] = "HIT" if from_cache else "MISS"
        return response
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (FileNotFoundError, OSError) as exc:
        raise _unavailable(exc) from exc


@router.get("/regions/{region_id}")
def financial_map_region(
    region_id: str,
    collection: UUID,
    level: Literal["voivodeship", "county", "municipality"] = "voivodeship",
    year: int = Query(..., ge=1900, le=2200),
    metric: str = Query("revenue_total", max_length=80),
    aggregation: str = Query("sum", max_length=40),
    pkd: str = Query("", max_length=20),
    pkd_mode: Literal["primary", "all"] = "primary",
    min_companies: int = Query(5, ge=1, le=500),
):
    if metric not in financial_map.METRICS:
        raise HTTPException(422, "Nieznana metryka finansowa")
    params = dict(collection=str(collection), region_id=region_id, level=level, year=year,
                  metric_id=metric, aggregation=aggregation, pkd=pkd, pkd_mode=pkd_mode,
                  min_companies=min_companies)
    try:
        result, from_cache = cached_response(
            "financial-map-region-v2", params,
            lambda: financial_map.region_detail(**params),
            ttl=1800,
        )
        response = JSONResponse(result)
        response.headers["X-Cache"] = "HIT" if from_cache else "MISS"
        return response
    except KeyError as exc:
        raise HTTPException(404, "Nie znaleziono regionu dla bieżących filtrów") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (FileNotFoundError, OSError) as exc:
        raise _unavailable(exc) from exc


@router.get("/compare/regions")
def financial_map_comparison(
    collection: UUID,
    region_ids: str = Query(..., min_length=1, max_length=120),
    level: Literal["voivodeship", "county", "municipality"] = "voivodeship",
    year: int = Query(..., ge=1900, le=2200),
    pkd: str = Query("", max_length=20),
    pkd_mode: Literal["primary", "all"] = "primary",
    min_companies: int = Query(5, ge=1, le=500),
):
    ids = [value.strip() for value in region_ids.split(",") if value.strip()][:5]
    params = dict(collection=str(collection), region_ids=ids, level=level, year=year, pkd=pkd,
                  pkd_mode=pkd_mode, min_companies=min_companies)
    try:
        result, from_cache = cached_response(
            "financial-map-comparison-v2", params,
            lambda: financial_map.compare_regions(**params),
            ttl=1800,
        )
        response = JSONResponse(result)
        response.headers["X-Cache"] = "HIT" if from_cache else "MISS"
        return response
    except (FileNotFoundError, OSError) as exc:
        raise _unavailable(exc) from exc
