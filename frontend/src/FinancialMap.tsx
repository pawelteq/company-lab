import { useEffect, useMemo, useRef, useState } from 'react';
import { useApi } from './api';
import './financial-map.css';

type Metric = {
  id: string;
  label: string;
  category: string;
  format: 'currency' | 'percent' | 'ratio' | 'number';
  available_aggregations: string[];
  default_aggregation: string;
  higher_is_better: boolean | null;
  numerator_field?: string | null;
  denominator_field?: string | null;
  description?: string;
};

type Metadata = {
  collection: string;
  years: number[];
  metrics: Metric[];
  aggregations: { id: string; label: string }[];
  pkd: { code: string; company_count: number }[];
  levels: string[];
  index: { profiles: number; observations: number; current: boolean };
};

type MapRegion = {
  region_id: string;
  region_name: string;
  value: number | null;
  raw_value: number | null;
  formatted_value: string;
  company_count: number;
  metric_company_count: number;
  mean: number | null;
  median: number | null;
  winsor_mean: number | null;
  min: number | null;
  max: number | null;
  p25: number | null;
  p75: number | null;
  p90: number | null;
  regional_ratio: number | null;
  rank?: number;
  rank_total?: number;
  insufficient_data: boolean;
};

type MapData = {
  level: 'voivodeship' | 'county' | 'municipality';
  year: number;
  compare_year?: number;
  view: 'value' | 'change';
  metric: Metric;
  aggregation: string;
  min_companies: number;
  regions: MapRegion[];
};

type RegionDetail = MapData & {
  region: MapRegion;
  trend: { year: number; value: number | null }[];
  top_revenue: { krs: string; name: string; value: number }[];
  top_metric: { krs: string; name: string; value: number }[];
  suppressed: boolean;
};

type ComparisonData = {
  level: MapData['level'];
  year: number;
  regions: {
    region_id: string;
    region_name: string;
    metrics: Record<string, { value: number | null; formatted_value: string; company_count: number }>;
  }[];
};

const levelLabels = {
  voivodeship: 'Województwa',
  county: 'Powiaty',
  municipality: 'Gminy',
};

function fmtNumber(value: number | null | undefined, format: Metric['format'], change = false) {
  if (value == null || !Number.isFinite(value)) return '—';
  const sign = change && value > 0 ? '+' : '';
  if (change) return `${sign}${value.toLocaleString('pl-PL', { maximumFractionDigits: 2 })}${format === 'percent' ? ' p.p.' : '%'}`;
  if (format === 'currency') {
    const absolute = Math.abs(value);
    const prefix = value < 0 ? '−' : '';
    if (absolute >= 1e12) return `${prefix}${(absolute / 1e12).toLocaleString('pl-PL', { maximumFractionDigits: 2 })} bln zł`;
    if (absolute >= 1e9) return `${prefix}${(absolute / 1e9).toLocaleString('pl-PL', { maximumFractionDigits: 2 })} mld zł`;
    if (absolute >= 1e6) return `${prefix}${(absolute / 1e6).toLocaleString('pl-PL', { maximumFractionDigits: 2 })} mln zł`;
    if (absolute >= 1e3) return `${prefix}${(absolute / 1e3).toLocaleString('pl-PL', { maximumFractionDigits: 1 })} tys. zł`;
    return `${value.toLocaleString('pl-PL', { maximumFractionDigits: 0 })} zł`;
  }
  if (format === 'percent') return `${value.toLocaleString('pl-PL', { maximumFractionDigits: 2 })}%`;
  if (format === 'ratio') return `${value.toLocaleString('pl-PL', { maximumFractionDigits: 2 })}x`;
  return value.toLocaleString('pl-PL', { maximumFractionDigits: 2 });
}

function percentile(values: number[], q: number) {
  const sorted = [...values].sort((a, b) => a - b);
  if (!sorted.length) return 0;
  const position = (sorted.length - 1) * q;
  const low = Math.floor(position), high = Math.ceil(position);
  return low === high ? sorted[low] : sorted[low] + (sorted[high] - sorted[low]) * (position - low);
}

function parseLocalNumber(value: string) {
  if (!value.trim()) return null;
  const parsed = Number(value.trim().replace(',', '.'));
  return Number.isFinite(parsed) ? parsed : null;
}

function legendBreaks(values: number[], method: 'quantile' | 'percentile' | 'minmax' | 'manual', manualMin: number | null, manualMax: number | null, change: boolean) {
  if (!values.length) return [];
  if (change) {
    const edge = Math.max(...values.map(Math.abs));
    return [-edge, -edge / 2, 0, edge / 2, edge];
  }
  if (method === 'quantile') return [0, .25, .5, .75, 1].map(q => percentile(values, q));
  let low = method === 'percentile' ? percentile(values, .05) : Math.min(...values);
  let high = method === 'percentile' ? percentile(values, .95) : Math.max(...values);
  if (method === 'manual' && manualMin != null && manualMax != null && manualMin < manualMax) {
    low = manualMin; high = manualMax;
  }
  return [0, .25, .5, .75, 1].map(part => low + (high - low) * part);
}

function Icon({ path }: { path: string }) {
  return <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round"><path d={path} /></svg>;
}

export function FinancialMap({ collection, onSelectCompany }: { collection: string; onSelectCompany: (krs: string) => void }) {
  const metadata = useApi<Metadata>(`/api/analytics/map/metadata?collection=${collection}`);
  const activeMetadata = metadata.data?.collection === collection ? metadata.data : undefined;
  const [level, setLevel] = useState<MapData['level']>('voivodeship');
  const [year, setYear] = useState<number>();
  const [metricId, setMetricId] = useState('revenue_total');
  const [aggregation, setAggregation] = useState('sum');
  const [pkd, setPkd] = useState('');
  const [pkdMode, setPkdMode] = useState<'primary' | 'all'>('primary');
  const [verification, setVerification] = useState<'all' | 'verified' | 'confirmed' | 'rejected' | 'unverified'>('all');
  const [minCompanies, setMinCompanies] = useState(5);
  const [view, setView] = useState<'value' | 'change'>('value');
  const [scaleMethod, setScaleMethod] = useState<'quantile' | 'percentile' | 'minmax' | 'manual'>('quantile');
  const [manualMin, setManualMin] = useState('');
  const [manualMax, setManualMax] = useState('');
  const [showValues, setShowValues] = useState(true);
  const [showNames, setShowNames] = useState(true);
  const [showRanking, setShowRanking] = useState(true);
  const [selectedRegion, setSelectedRegion] = useState('');
  const [search, setSearch] = useState('');
  const [compare, setCompare] = useState<string[]>([]);
  const frame = useRef<HTMLIFrameElement>(null);
  const [frameReady, setFrameReady] = useState(false);

  const activeMetric = activeMetadata?.metrics.find(metric => metric.id === metricId);
  useEffect(() => {
    const years = activeMetadata?.years || [];
    const metrics = activeMetadata?.metrics || [];
    if (years.length && (year == null || !years.includes(year))) setYear(years[0]);
    if (metrics.length && !metrics.some(metric => metric.id === metricId)) {
      setMetricId(metrics[0].id);
      setAggregation(metrics[0].default_aggregation);
    }
  }, [collection, activeMetadata, year, metricId]);
  useEffect(() => {
    if (activeMetric && !activeMetric.available_aggregations.includes(aggregation)) {
      setAggregation(activeMetric.default_aggregation);
    }
  }, [activeMetric, aggregation]);

  const query = useMemo(() => {
    if (!year || !activeMetadata) return null;
    const params = new URLSearchParams({
      collection, level, year: String(year), metric: metricId, aggregation,
      pkd, pkd_mode: pkdMode, verification, min_companies: String(minCompanies), view,
    });
    if (view === 'change') params.set('compare_year', String(year - 1));
    return `/api/analytics/map?${params}`;
  }, [collection, activeMetadata, level, year, metricId, aggregation, pkd, pkdMode, verification, minCompanies, view]);
  const map = useApi<MapData>(query);

  const detailQuery = selectedRegion && year && activeMetadata ? (() => {
    const params = new URLSearchParams({
      collection, level, year: String(year), metric: metricId, aggregation, pkd, pkd_mode: pkdMode,
      verification, min_companies: String(minCompanies),
    });
    return `/api/analytics/map/regions/${selectedRegion}?${params}`;
  })() : null;
  const detail = useApi<RegionDetail>(detailQuery);

  const comparisonQuery = useMemo(() => {
    if (!year || !compare.length || !activeMetadata) return null;
    const params = new URLSearchParams({
      collection, region_ids: compare.join(','), level, year: String(year), pkd, pkd_mode: pkdMode,
      verification, min_companies: String(minCompanies),
    });
    return `/api/analytics/map/compare/regions?${params}`;
  }, [collection, activeMetadata, compare, level, year, pkd, pkdMode, verification, minCompanies]);
  const comparison = useApi<ComparisonData>(comparisonQuery);

  useEffect(() => { setSelectedRegion(''); setSearch(''); setCompare([]); }, [collection, level]);
  useEffect(() => { setSelectedRegion(''); }, [year, metricId, aggregation, pkd, pkdMode, verification, view]);

  useEffect(() => {
    function receive(event: MessageEvent) {
      if (event.source !== frame.current?.contentWindow || event.origin !== window.location.origin) return;
      if (event.data?.type === 'company-map-ready') setFrameReady(true);
      if (event.data?.type === 'financial-map-select') selectRegion(String(event.data.regionId || ''));
    }
    window.addEventListener('message', receive);
    return () => window.removeEventListener('message', receive);
  });

  useEffect(() => {
    if (!frameReady || !map.data) return;
    frame.current?.contentWindow?.postMessage({
      type: 'financial-map-data',
      payload: {
        ...map.data,
        selectedRegionId: selectedRegion,
        showValues,
        showNames,
        metricLabel: activeMetric?.label || metricId,
        minCompanies,
        scale: { method: scaleMethod, min: parseLocalNumber(manualMin), max: parseLocalNumber(manualMax) },
      },
    }, window.location.origin);
  }, [frameReady, map.data, selectedRegion, showValues, showNames, activeMetric, metricId, minCompanies, scaleMethod, manualMin, manualMax]);

  function selectRegion(regionId: string, focus = false) {
    setSelectedRegion(regionId);
    if (focus) frame.current?.contentWindow?.postMessage({ type: 'financial-map-focus', regionId }, window.location.origin);
    requestAnimationFrame(() => document.querySelector(`[data-rank-region="${CSS.escape(regionId)}"]`)?.scrollIntoView({ block: 'nearest' }));
  }

  const eligible = (map.data?.regions || []).filter(region => region.value != null).sort((a, b) => (a.rank || 9999) - (b.rank || 9999));
  const searched = search.trim()
    ? (map.data?.regions || []).filter(region => region.region_name.toLocaleLowerCase('pl').includes(search.toLocaleLowerCase('pl'))).slice(0, 8)
    : [];
  const parsedManualMin = parseLocalNumber(manualMin);
  const parsedManualMax = parseLocalNumber(manualMax);
  const manualScaleValid = parsedManualMin != null && parsedManualMax != null && parsedManualMin < parsedManualMax;
  const legend = legendBreaks(eligible.map(region => region.value as number), scaleMethod, parsedManualMin, parsedManualMax, view === 'change');
  const aggregationLabel = activeMetadata?.aggregations.find(item => item.id === aggregation)?.label || aggregation;
  const selected = map.data?.regions.find(region => region.region_id === selectedRegion);
  const compareRegions = comparison.data?.regions || [];

  function toggleCompare(id: string) {
    setCompare(current => current.includes(id) ? current.filter(item => item !== id) : current.length < 5 ? [...current, id] : current);
  }

  if (metadata.error) return <section className="financial-map-empty"><h1>Finansowa mapa Polski</h1><p>{metadata.error}</p></section>;

  return <div className="financial-atlas">
    <section className="atlas-heading">
      <div>
        <h1>Finansowa mapa Polski<span>.</span></h1>
        <p>Porównuj realne wyniki firm w województwach, powiatach i gminach. Kolor pokazuje różnicę, liczba — dokładny wynik.</p>
      </div>
      {activeMetadata && <div className="atlas-coverage"><strong>{activeMetadata.index.observations.toLocaleString('pl-PL')}</strong><span>obserwacji firma–rok<br />w indeksie mapy</span></div>}
    </section>

    <section className="atlas-controls" aria-label="Ustawienia mapy finansowej">
      <label>Poziom<select value={level} onChange={event => setLevel(event.target.value as MapData['level'])}>
        {Object.entries(levelLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
      </select></label>
      <label>Rok<select value={year || ''} onChange={event => setYear(Number(event.target.value))}>
        {(activeMetadata?.years || []).map(value => <option key={value} value={value}>{value}</option>)}
      </select></label>
      <label className="metric-control">Wskaźnik<select value={metricId} onChange={event => {
        const next = activeMetadata?.metrics.find(metric => metric.id === event.target.value);
        setMetricId(event.target.value); if (next) setAggregation(next.default_aggregation);
      }}>
        {[...new Set(activeMetadata?.metrics.map(metric => metric.category) || [])].map(category => <optgroup key={category} label={category}>
          {activeMetadata?.metrics.filter(metric => metric.category === category).map(metric => <option key={metric.id} value={metric.id}>{metric.label}</option>)}
        </optgroup>)}
      </select></label>
      <label>Agregacja<select value={aggregation} onChange={event => setAggregation(event.target.value)}>
        {(activeMetric?.available_aggregations || []).map(value => <option key={value} value={value}>{activeMetadata?.aggregations.find(item => item.id === value)?.label || value}</option>)}
      </select></label>
      <label className="pkd-control">Branża / PKD<select value={pkd} onChange={event => setPkd(event.target.value)}>
        <option value="">Wszystkie firmy</option>
        <option value="developer">Deweloperzy — kody oznaczone w danych</option>
        {(activeMetadata?.pkd || []).map(item => <option key={item.code} value={item.code}>{item.code} · {item.company_count.toLocaleString('pl-PL')} firm</option>)}
      </select></label>
      <label>Zakres PKD<select value={pkdMode} onChange={event => setPkdMode(event.target.value as 'primary' | 'all')}>
        <option value="primary">Tylko główne PKD</option><option value="all">Główne + dodatkowe</option>
      </select></label>
      <label>Weryfikacja<select value={verification} onChange={event => setVerification(event.target.value as typeof verification)}>
        <option value="all">Wszystkie firmy</option>
        <option value="verified">Wszystkie zweryfikowane</option>
        <option value="confirmed">Potwierdzone jako deweloper</option>
        <option value="rejected">Wykluczone — nie deweloper</option>
        <option value="unverified">Jeszcze niezweryfikowane</option>
      </select></label>
      <label>Minimum firm<select value={minCompanies} onChange={event => setMinCompanies(Number(event.target.value))}>
        {[1, 3, 5, 10, 20, 50].map(value => <option key={value} value={value}>{value}</option>)}
      </select></label>
      <label>Widok<select value={view} onChange={event => setView(event.target.value as 'value' | 'change')}>
        <option value="value">Wartość</option><option value="change">Zmiana vs {year ? year - 1 : 'poprzedni rok'}</option>
      </select></label>
      <label>Skala kolorów<select value={scaleMethod} onChange={event => setScaleMethod(event.target.value as typeof scaleMethod)}>
        <option value="quantile">Kwantyle</option><option value="percentile">Percentyle</option><option value="minmax">Min–Max</option><option value="manual">Zakres ręczny</option>
      </select></label>
      {scaleMethod === 'manual' && <div className="manual-scale"><label>Od<input inputMode="decimal" value={manualMin} onChange={event => setManualMin(event.target.value)} aria-invalid={!manualScaleValid} /></label><label>Do<input inputMode="decimal" value={manualMax} onChange={event => setManualMax(event.target.value)} aria-invalid={!manualScaleValid} /></label>{!manualScaleValid && <small>Podaj poprawny zakres, np. od 1,5 do 20.</small>}</div>}
      <div className="atlas-toggles" role="group" aria-label="Widoczność elementów">
        <label><input type="checkbox" checked={showValues} onChange={event => setShowValues(event.target.checked)} /> Wartości na mapie</label>
        <label><input type="checkbox" checked={showNames} onChange={event => setShowNames(event.target.checked)} /> Nazwy regionów</label>
        <label><input type="checkbox" checked={showRanking} onChange={event => setShowRanking(event.target.checked)} /> Ranking</label>
      </div>
    </section>

    <div className={`atlas-stage ${showRanking ? '' : 'without-ranking'}`}>
      <section className="atlas-map-panel" aria-label="Mapa wyników finansowych">
        <div className="atlas-map-topline">
          <div><strong>{activeMetric?.label || 'Wskaźnik'} · {year || '—'}</strong><span>{aggregationLabel} · {levelLabels[level]}</span></div>
          <label className="region-search"><span className="sr-only">Szukaj regionu</span><input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Szukaj regionu…" /></label>
          {searched.length > 0 && <div className="region-search-results">{searched.map(region => <button key={region.region_id} onClick={() => { selectRegion(region.region_id, true); setSearch(''); }}>{region.region_name}<span>{region.formatted_value}</span></button>)}</div>}
        </div>
        <div className="atlas-map-frame">
          <iframe ref={frame} src="/maps/poland.html?financial=1&v=c9e615b9ed87" title={`Finansowa mapa Polski — ${levelLabels[level]}`} onLoad={() => frame.current?.contentWindow?.postMessage({ type: 'company-map-hello' }, window.location.origin)} />
          {map.loading && <div className="atlas-map-state" role="status">Przeliczamy regiony…</div>}
          {map.error && <div className="atlas-map-state error" role="alert">Nie udało się obliczyć mapy: {map.error}</div>}
        </div>
        <div className="atlas-legend" aria-label="Legenda skali kolorów">
          <span className="legend-title">{view === 'change' ? 'Zmiana' : scaleMethod === 'quantile' ? 'Kwantyle' : scaleMethod === 'percentile' ? 'Percentyle' : 'Zakres'}</span>
          <div className={`legend-ramp ${view === 'change' ? 'diverging' : ''}`} />
          <div className="legend-values">{legend.map((value, index) => <span key={`${value}-${index}`}>{fmtNumber(value, activeMetric?.format || 'number', view === 'change')}</span>)}</div>
          <span className="legend-missing"><i /> Brak danych lub mniej niż {minCompanies} firm</span>
        </div>
      </section>

      {showRanking && <aside className="atlas-ranking">
        <div className="ranking-heading"><div><h2>Ranking</h2><p>{activeMetric?.label} · {aggregationLabel}</p></div><span>{eligible.length}</span></div>
        <div className="ranking-list">{eligible.map(region => <button key={region.region_id} data-rank-region={region.region_id} className={selectedRegion === region.region_id ? 'active' : ''} onClick={() => selectRegion(region.region_id, true)}>
          <span className="rank-number">{region.rank}</span><span className="rank-name">{region.region_name}<small>{region.metric_company_count.toLocaleString('pl-PL')} firm z danymi</small></span><strong>{region.formatted_value}</strong>
        </button>)}</div>
      </aside>}
    </div>

    <section className={`atlas-detail ${selected ? 'is-open' : ''}`} aria-live="polite">
      {!selected && <div className="atlas-detail-empty"><Icon path="M3 11l9-8 9 8-9 10-9-10Zm9-8v18" /><div><h2>Wybierz region</h2><p>Kliknij obszar na mapie albo pozycję w rankingu, aby zobaczyć statystyki, dynamikę i firmy.</p></div></div>}
      {selected && <>
        <div className="detail-heading"><div><span>{levelLabels[level].slice(0, -1)}</span><h2>{selected.region_name}</h2><p>{year} · {activeMetric?.label} · {aggregationLabel}</p></div><div className="detail-actions"><button className={compare.includes(selected.region_id) ? 'active' : ''} disabled={selected.insufficient_data || (!compare.includes(selected.region_id) && compare.length >= 5)} onClick={() => toggleCompare(selected.region_id)}>{compare.includes(selected.region_id) ? 'Usuń z porównania' : 'Dodaj do porównania'}</button><button aria-label="Zamknij szczegóły" onClick={() => setSelectedRegion('')}>×</button></div></div>
        <div className="detail-core"><div className="detail-primary"><span>Wybrany wynik</span><strong>{selected.formatted_value}</strong><small>{selected.rank ? `${selected.rank}. miejsce na ${selected.rank_total}` : 'Poza rankingiem'}</small></div><dl>
          <div><dt>Firmy w regionie</dt><dd>{selected.company_count.toLocaleString('pl-PL')}</dd></div>
          <div><dt>Firmy z tym wskaźnikiem</dt><dd>{selected.metric_company_count.toLocaleString('pl-PL')}</dd></div>
          <div><dt>Mediana</dt><dd>{fmtNumber(selected.median, activeMetric?.format || 'number')}</dd></div>
          <div><dt>Średnia</dt><dd>{fmtNumber(selected.mean, activeMetric?.format || 'number')}</dd></div>
          <div><dt>P25 / P75</dt><dd>{fmtNumber(selected.p25, activeMetric?.format || 'number')} / {fmtNumber(selected.p75, activeMetric?.format || 'number')}</dd></div>
          <div><dt>Min / Max</dt><dd>{fmtNumber(selected.min, activeMetric?.format || 'number')} / {fmtNumber(selected.max, activeMetric?.format || 'number')}</dd></div>
        </dl></div>
        {detail.loading && <p className="detail-loading">Pobieramy firmy i historię regionu…</p>}
        {selected.insufficient_data && <p className="detail-loading">Szczegóły ukryte: region ma mniej niż {minCompanies} firm z tym wskaźnikiem.</p>}
        {detail.data && !detail.data.suppressed && <div className="detail-secondary">
          <div className="region-trend"><h3>Dynamika regionu</h3><div>{detail.data.trend.map(point => <span key={point.year}><small>{point.year}</small><b>{fmtNumber(point.value, activeMetric?.format || 'number')}</b></span>)}</div></div>
          <div className="top-companies"><h3>Największe firmy według przychodów</h3>{detail.data.top_revenue.map(company => <button key={company.krs} onClick={() => onSelectCompany(company.krs)}><span>{company.name || `KRS ${company.krs}`}<small>KRS {company.krs}</small></span><strong>{fmtNumber(company.value, 'currency')}</strong></button>)}</div>
          <div className="top-companies"><h3>Najwyższe: {activeMetric?.label}</h3>{detail.data.top_metric.map(company => <button key={company.krs} onClick={() => onSelectCompany(company.krs)}><span>{company.name || `KRS ${company.krs}`}<small>KRS {company.krs}</small></span><strong>{fmtNumber(company.value, activeMetric?.format || 'number')}</strong></button>)}</div>
        </div>}
      </>}
    </section>

    {compare.length > 0 && <section className="atlas-comparison"><div className="comparison-heading"><div><h2>Porównanie regionów</h2><p>Maksymalnie pięć regionów · ten sam rok, branża i zakres PKD.</p></div><button onClick={() => setCompare([])}>Wyczyść</button></div>{comparison.loading && <p className="detail-loading">Liczymy wspólne wskaźniki…</p>}{comparison.error && <p className="detail-loading">Nie udało się pobrać porównania: {comparison.error}</p>}{compareRegions.length > 0 && <div className="table-scroll"><table><thead><tr><th>Region</th><th>Przychody</th><th>Zysk netto</th><th>ROA</th><th>ROE</th><th>Marża EBIT</th><th /></tr></thead><tbody>{compareRegions.map(region => <tr key={region.region_id}><td><strong>{region.region_name}</strong></td>{['revenue_total', 'profit_net', 'roa', 'roe', 'ebit_margin'].map(metric => <td key={metric} title={`${region.metrics[metric]?.company_count || 0} firm z danymi`}>{region.metrics[metric]?.formatted_value || '—'}</td>)}<td><button onClick={() => toggleCompare(region.region_id)} aria-label={`Usuń ${region.region_name}`}>×</button></td></tr>)}</tbody></table></div>}</section>}

    <p className="atlas-method-note">Wartości pochodzą z zaimportowanych sprawozdań. Filtr weryfikacji korzysta z decyzji ręcznych i Gemini zapisanych w bazie, więc mapa przelicza się po każdej zmianie etykiety. Zero jest liczbą; brak danych nie jest zamieniany na zero. Dla wskaźników procentowych „wskaźnik zagregowany” liczy iloraz sum składowych, a nie średnią procentów.</p>
  </div>;
}
