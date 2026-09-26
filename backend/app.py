"""Local, read-only API over immutable analytical datasets. Never exposes RAW files."""
from contextlib import asynccontextmanager, contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Literal
from uuid import UUID
import logging
import os

from fastapi.middleware.cors import CORSMiddleware
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import set_json_loads
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from etl.config import ROOT, database_url
from etl.parsing import loads
from analytics.lineage import feature_trace
from backend import local_profiles
from backend.cache import get_redis, redis_available, invalidate as cache_invalidate
from backend.rate_limit import check_rate_limit, get_client_ip, get_rate_limit

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: probe Redis
    client = get_redis()
    if client:
        logger.info("Redis cache aktywny.")
    else:
        logger.warning("Redis niedostępny — cache wyłączony, kolejka zadań niedostępna.")
    try:
        from backend.financial_map import sync_verifications
        result = sync_verifications()
        if result.get("available"):
            logger.info("Mapa: zsynchronizowano %s zapisanych weryfikacji.", result["updated"])
    except Exception as exc:
        logger.warning("Nie udało się zsynchronizować weryfikacji z mapą: %s", exc)
    yield
    # Shutdown: nothing to clean up

app = FastAPI(title='Company Intelligence · Research Lab', version='0.3.0', lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost",
        "https://localhost",
        "capacitor://localhost",
        "http://127.0.0.1",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://26.34.13.91",
        "http://26.34.13.91:5173",
        "http://26.34.13.91:8000",
    ],
    allow_origin_regex=r"http(s)?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: https: blob:; "
        "connect-src 'self' http://localhost:* http://127.0.0.1:* http://26.34.13.91:* ws://localhost:* ws://127.0.0.1:* ws://26.34.13.91:* ws: wss:; "
        "frame-ancestors 'self';"
    )
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path in ("/", "/index.html") or request.url.path.endswith(".html"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path != "/api/health":
        client_ip = get_client_ip(request)
        limit = get_rate_limit()
        allowed, remaining, retry_after = check_rate_limit(client_ip, limit=limit)
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Zbyt wiele zapytań (Rate limit przekroczony). Spróbuj ponownie za chwilę."},
                headers={
                    "Retry-After": str(retry_after),
                    "X-RateLimit-Limit": str(limit),
                    "X-RateLimit-Remaining": "0",
                },
            )
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response

    return await call_next(request)

@contextmanager
def connection():
    with psycopg.connect(database_url(api=True),
                         connect_timeout=5, row_factory=dict_row) as conn:
        conn.read_only = True
        conn.execute("SET LOCAL statement_timeout = '10s'")
        set_json_loads(loads, conn)
        yield conn


@app.exception_handler(psycopg.Error)
async def database_error(request, exc):
    return JSONResponse(status_code=503, content={'detail': 'Baza danych jest chwilowo niedostępna. Spróbuj ponownie.'})


def dataset_exists(conn, dataset):
    if not conn.execute('SELECT 1 FROM analytics.dataset WHERE id=%s', (dataset,)).fetchone():
        raise HTTPException(404, 'Nie znaleziono wersji danych')


@app.get('/api/health')
def health():
    result: dict = {}
    if local_profiles.available():
        result.update(status='ok', mode='local_sqlite', **local_profiles.status())
    else:
        with connection() as conn:
            conn.execute('SELECT 1')
        result.update(status='ok', mode='local_read_only')
    result['redis'] = 'connected' if redis_available() else 'unavailable'
    return result


@app.get('/api/datasets')
def datasets():
    # Bieżąca aplikacja korzysta z profili. Gdy lokalna baza SQLite jest
    # dostępna, nie pokazujemy dawnego archiwum PostgreSQL w interfejsie.
    if local_profiles.available():
        return []
    with connection() as conn:
        return conn.execute('SELECT id,batch_id,maturity,research_ready,created_at FROM analytics.dataset ORDER BY created_at DESC,id LIMIT 100').fetchall()


@lru_cache(maxsize=16)
def dataset_summary(dataset):
    with connection() as conn:
        dataset_exists(conn, dataset)
        total = conn.execute('''SELECT count(*) observations,count(DISTINCT company_id) companies,
            min(year) first_year,max(year) last_year,
            count(*) FILTER(WHERE selection_status<>'selected_unique') unresolved_observations
            FROM analytics.company_year WHERE dataset_id=%s''', (dataset,)).fetchone()
        total['years'] = conn.execute('''SELECT year,count(*) observations,count(*) FILTER(WHERE selection_status='selected_unique') selected
            FROM analytics.company_year WHERE dataset_id=%s GROUP BY year ORDER BY year''', (dataset,)).fetchall()
        total['cohorts'] = conn.execute('''SELECT count(DISTINCT company_id) FILTER(WHERE panel_3plus) panel_3plus,
            count(DISTINCT company_id) FILTER(WHERE panel_5plus) panel_5plus,
            count(DISTINCT company_id) FILTER(WHERE panel_long) panel_long
            FROM analytics.company_year WHERE dataset_id=%s''', (dataset,)).fetchone()
        return total


@app.get('/api/datasets/{dataset}/summary')
def summary(dataset: UUID):
    return dataset_summary(dataset)


@app.get('/api/datasets/{dataset}/features')
def features(dataset: UUID):
    with connection() as conn:
        dataset_exists(conn, dataset)
        return conn.execute('SELECT name,definition FROM analytics.feature_definition WHERE dataset_id=%s ORDER BY name', (dataset,)).fetchall()


@app.get('/api/companies')
def companies(dataset: UUID, q: str = Query('', max_length=120),
              cohort: Literal['full','3plus','5plus','long'] = 'full',
              limit: int = Query(25, ge=1, le=100), offset: int = Query(0, ge=0, le=100000)):
    # Identifier is chosen exclusively from a fixed allow-list, user values are bound.
    flag = {'full':'panel_full','3plus':'panel_3plus','5plus':'panel_5plus','long':'panel_long'}[cohort]
    escaped = q.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
    pattern = '%'+escaped+'%'
    query = f'''WITH catalog AS (
        SELECT c.company_id,c.krs,s.name,s.legal_form,p.years,p.first_year,p.last_year
        FROM core.company c
        JOIN LATERAL (SELECT count(*) years,min(year) first_year,max(year) last_year
            FROM analytics.company_year WHERE company_id=c.company_id AND dataset_id=%s AND {flag}) p ON p.years>0
        LEFT JOIN LATERAL (SELECT name,legal_form FROM core.company_snapshot WHERE company_id=c.company_id
            AND name IS NOT NULL ORDER BY observed_at DESC,id DESC LIMIT 1) s ON true
        WHERE (%s='' OR c.krs ILIKE %s OR s.name ILIKE %s)) '''
    with connection() as conn:
        dataset_exists(conn, dataset)
        params = (dataset,q,pattern,pattern)
        total = conn.execute(query+'SELECT count(*) total FROM catalog', params).fetchone()['total']
        items = conn.execute(query+'SELECT * FROM catalog ORDER BY krs LIMIT %s OFFSET %s', params+(limit,offset)).fetchall()
    return {'items':items,'total':total,'limit':limit,'offset':offset}


@app.get('/api/companies/{krs}')
def company(krs: str, dataset: UUID):
    if len(krs)!=10 or not krs.isascii() or not krs.isdigit():
        raise HTTPException(422, 'KRS musi zawierać 10 cyfr')
    with connection() as conn:
        dataset_exists(conn, dataset)
        result = conn.execute('SELECT company_id,krs FROM core.company WHERE krs=%s', (krs,)).fetchone()
        if not result:
            raise HTTPException(404, 'Nie znaleziono firmy')
        result['identity_snapshots'] = conn.execute('''SELECT name,legal_form,website,source_kind,observed_at
            FROM core.company_snapshot WHERE company_id=%s ORDER BY observed_at DESC,id DESC''', (result['company_id'],)).fetchall()
        result['years'] = conn.execute('''SELECT year,selection_status,n_years,n_annual_years,features,missing_reasons,quality_codes
            FROM analytics.company_year WHERE dataset_id=%s AND company_id=%s ORDER BY year''', (dataset,result['company_id'])).fetchall()
        result['identity_note'] = 'Identyfikacja pochodzi z bieżących snapshotów; nie jest historyczną informacją dostępną w danym roku.'
        result['unit_note'] = 'Skala i waluta danych dostawcy nie są niezależnie potwierdzone. Wskaźniki obliczone są ułamkami.'
        result['maturity'] = 'exploratory_reported'
        return result


@app.get('/api/companies/{krs}/lineage')
def lineage(krs: str, dataset: UUID, year: int = Query(ge=1900, le=2200), feature: str = Query(max_length=100)):
    try:
        result = feature_trace(database_url(api=True),dataset,krs,year,feature)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    def redact(node):
        if isinstance(node,dict):
            return {k:redact(v) for k,v in node.items() if k!='archive_path'}
        if isinstance(node,list):
            return [redact(v) for v in node]
        return node
    return redact(result)


@app.get('/api/research')
def research_runs(dataset: UUID):
    with connection() as conn:
        dataset_exists(conn, dataset)
        return conn.execute('''SELECT id,dataset_id,inference_class,created_at,
            results->'causal' causal,results->'out_of_sample_validated' out_of_sample_validated
            FROM research.run WHERE dataset_id=%s ORDER BY created_at DESC,id LIMIT 100''', (dataset,)).fetchall()


@app.get('/api/research/{run}')
def research_result(run: UUID):
    with connection() as conn:
        row = conn.execute('SELECT results FROM research.run WHERE id=%s', (run,)).fetchone()
        if not row:
            raise HTTPException(404, 'Nie znaleziono badania')
        return row['results']


@app.get('/api/research/{run}/diagnostics')
def diagnostic_versions(run: UUID):
    with connection() as conn:
        if not conn.execute('SELECT 1 FROM research.run WHERE id=%s',(run,)).fetchone():
            raise HTTPException(404, 'Nie znaleziono badania')
        return conn.execute('''SELECT id,research_run_id,created_at FROM research.diagnostic_run
            WHERE research_run_id=%s ORDER BY created_at DESC,id LIMIT 100''',(run,)).fetchall()


def diagnostic_result(conn, diagnostic):
    row=conn.execute('SELECT results FROM research.diagnostic_run WHERE id=%s',(diagnostic,)).fetchone()
    if not row:
        raise HTTPException(404, 'Nie znaleziono diagnostyki')
    return row['results']


@app.get('/api/diagnostics/{diagnostic}')
def diagnostic_summary(diagnostic: UUID):
    with connection() as conn:
        result=diagnostic_result(conn,diagnostic)
    studies=[]
    for study in result['studies']:
        cases=[]
        for case in study['cases']:
            sensitivity=case['sensitivity']
            trigger=next(v for v in case['variables'] if v['variable']==case['trigger_variable'])
            cases.append({k:case[k] for k in ['rank','krs','name','origin_year','status']} | {
                'trigger_feature':trigger['feature'],'trigger_year':trigger['year'],'trigger_value':trigger['value'],
                'small_denominators':sum(d['small_denominator_flag'] for v in case['variables'] for d in v['denominators']),
                'coefficient_without_company':sensitivity['estimate'].get('coefficients',{}).get(study['primary_term'],{}).get('coefficient'),
                'change_in_baseline_se':sensitivity.get('change_in_baseline_se')})
        studies.append({k:study[k] for k in ['id','title','primary_term','baseline_reproduced','distributions']} | {
            'baseline_coefficient':study['baseline']['coefficients'][study['primary_term']]['coefficient'], 'cases':cases})
    return {k:result[k] for k in ['id','research_run_id','dataset_id','protocol','maturity','research_ready']} | {'studies':studies}


@app.get('/api/diagnostics/{diagnostic}/cases/{study_id}/{krs}')
def diagnostic_case(diagnostic: UUID, study_id: str, krs: str):
    with connection() as conn:
        result=diagnostic_result(conn,diagnostic)
    for study in result['studies']:
        if study['id']==study_id:
            for case in study['cases']:
                if case['krs']==krs:
                    return {'diagnostic_id':str(diagnostic),'dataset_id':result['dataset_id'],
                            'study_id':study_id,'primary_term':study['primary_term'],
                            'baseline_coefficient':study['baseline']['coefficients'][study['primary_term']],**case}
    raise HTTPException(404, 'Nie znaleziono przypadku diagnostycznego')


@app.get('/api/sources')
def source_catalog():
    from etl.compabase_payloads import TARGET_PKD
    import json
    audits=sorted((ROOT/'data/audit/references').glob('*/audit.json'),key=lambda p:p.stat().st_mtime,reverse=True)
    reference=None
    if audits:
        report=json.loads(audits[0].read_text(encoding='utf-8'))
        reference={'files':len(report['files']),'companies':report['profile_companies'],
                   'financial_records':report['distinct_provider_financial_ids'],
                   'representations':report['financial_representations'],
                   'numeric_conflicts':sum(bool(c['different']) for c in report['comparisons'])}
    return {'provider':'Compabase API','documentation_url':'https://github.com/ContentWriterco/Compabase-API',
            'collection':list(TARGET_PKD),'reference_audit':reference,'production_collection_status':'user_collecting'}


from backend.profiles import router as profile_router
app.include_router(profile_router)

from backend.financial_map_api import router as financial_map_router
app.include_router(financial_map_router)


# ---------------------------------------------------------------------------
# Background job endpoints
# ---------------------------------------------------------------------------

def _get_rq_queue():
    """Return the RQ Queue instance, or raise 503 when Redis is down."""
    client = get_redis()
    if client is None:
        raise HTTPException(503, "Redis jest niedostępny — kolejka zadań wyłączona.")
    from rq import Queue
    return Queue("company-lab", connection=client)


@app.post('/api/jobs/export-csv')
def submit_export_csv(
    collection: UUID,
    q: str = Query("", max_length=120),
    city: str = Query("", max_length=180),
    region: str = Query("", max_length=100),
    county: str = Query("", max_length=100),
    municipality: str = Query("", max_length=100),
    status: str = "developer_candidate",
    segment: str = "all",
    business_type: str = "all",
    activity: str = "all",
    verification: str = "all",
    revenue_min: float | None = None,
    revenue_max: float | None = None,
    profit_min: float | None = None,
    profit_max: float | None = None,
):
    queue = _get_rq_queue()
    filters = dict(
        q=q, status=status, segment=segment, city=city, region=region,
        county=county, municipality=municipality, business_type=business_type,
        activity=activity, verification=verification, revenue_min=revenue_min, revenue_max=revenue_max,
        profit_min=profit_min, profit_max=profit_max,
    )
    from backend.tasks import task_export_csv
    job = queue.enqueue(task_export_csv, str(collection), filters, job_timeout=300)
    return {'job_id': job.id, 'status': job.get_status()}


@app.post('/api/jobs/rebuild')
def submit_rebuild(collection_dir: str | None = None):
    queue = _get_rq_queue()
    from backend.tasks import task_rebuild_sqlite
    job = queue.enqueue(task_rebuild_sqlite, collection_dir, job_timeout=1800)
    return {'job_id': job.id, 'status': job.get_status()}


@app.post('/api/jobs/research')
def submit_research(
    module: str = Query(..., max_length=100),
):
    queue = _get_rq_queue()
    from backend.tasks import task_run_research
    job = queue.enqueue(task_run_research, module, job_timeout=3600)
    return {'job_id': job.id, 'status': job.get_status()}


@app.get('/api/jobs/{job_id}')
def job_status(job_id: str):
    client = get_redis()
    if client is None:
        raise HTTPException(503, "Redis jest niedostępny.")
    from rq.job import Job
    try:
        job = Job.fetch(job_id, connection=client)
    except Exception:
        raise HTTPException(404, "Nie znaleziono zadania.")
    meta = job.meta or {}
    return {
        'job_id': job.id,
        'status': job.get_status(),
        'progress': meta.get('progress'),
        'percent': meta.get('percent'),
        'enqueued_at': str(job.enqueued_at) if job.enqueued_at else None,
        'started_at': str(job.started_at) if job.started_at else None,
        'ended_at': str(job.ended_at) if job.ended_at else None,
    }


@app.get('/api/jobs/{job_id}/result')
def job_result(job_id: str):
    client = get_redis()
    if client is None:
        raise HTTPException(503, "Redis jest niedostępny.")
    from rq.job import Job
    try:
        job = Job.fetch(job_id, connection=client)
    except Exception:
        raise HTTPException(404, "Nie znaleziono zadania.")
    status = job.get_status()
    if status == 'failed':
        raise HTTPException(500, f"Zadanie zakończyło się błędem: {job.exc_info}")
    if status != 'finished':
        raise HTTPException(409, f"Zadanie jeszcze trwa (status: {status}).")
    result = job.result
    # If the result contains a file path (CSV export), serve it
    if isinstance(result, dict) and 'path' in result:
        path = Path(result['path'])
        if path.is_file():
            from fastapi.responses import FileResponse
            return FileResponse(
                path,
                media_type='text/csv; charset=utf-8',
                headers={'Content-Disposition': 'attachment; filename="company-lab-export.csv"'},
            )
    return result


@app.post('/api/cache/invalidate')
def invalidate_cache():
    deleted = cache_invalidate("cl:*")
    return {'deleted': deleted}


@app.get('/')
def root():
    index_file = ROOT / 'frontend' / 'dist' / 'index.html'
    if index_file.is_file():
        from fastapi.responses import FileResponse
        return FileResponse(
            index_file,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    return {
        "status": "ok",
        "app": "Company Intelligence · Research Lab",
        "version": "0.3.0",
        "redis": "connected" if redis_available() else "unavailable",
    }


# Production build is served from a dedicated folder, never the repository or data directory.
if (ROOT/'frontend'/'dist').is_dir():
    app.mount('/', StaticFiles(directory=ROOT/'frontend'/'dist', html=True), name='frontend')
