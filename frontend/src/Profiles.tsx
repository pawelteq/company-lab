import { ZoomableSvg } from './ZoomableSvg';
import { useEffect, useRef, useState } from 'react';
import { useApi } from './api';
import { LocationMap, type LocationSelection } from './LocationMap';
import { GeminiVerification, getStoredGeminiKey, setCachedGeminiResult } from './GeminiVerification';

const businessLabels: Record<string,string> = { developer:'Deweloper', spv:'Prawdopodobne SPV', contractor:'Wykonawca / usługi', other:'Inna działalność', review:'Niejednoznaczna', needs_web_grounding:'Do sprawdzenia w sieci' };
const labels: Record<string, string> = {
  developer_candidate: 'Deweloper według opisu', other_activity: 'Opis innej działalności',
  review: 'Do sprawdzenia', missing_summary: 'Brak opisu', name_signal: 'Nazwa sugeruje dewelopera',
};
const segments: Record<string, string> = {
  residential: 'Mieszkaniowy', commercial: 'Komercyjny / magazynowy', mixed: 'Mieszany', unknown: 'Nieokreślony',
};
const verificationLabels: Record<string, string> = {
  all: 'Wszystkie firmy',
  verified: 'Wszystkie zweryfikowane',
  confirmed: 'Potwierdzone jako deweloper',
  rejected: 'Wykluczone — nie deweloper',
  unverified: 'Jeszcze niezweryfikowane',
};
const fmt = (v: number) => v.toLocaleString('pl-PL');
type LocalVerification = 'confirmed' | 'rejected';
function verificationKey(collection: string) { return `company-lab:verification:${collection}`; }
function loadVerifications(collection: string): Record<string, LocalVerification> {
  try { return typeof window === 'undefined' ? {} : JSON.parse(window.localStorage.getItem(verificationKey(collection)) || '{}'); } catch { return {}; }
}
function storeVerification(collection: string, krs: string, value: LocalVerification | null) {
  if (typeof window === 'undefined') return;
  const current = loadVerifications(collection);
  if (value) current[krs] = value; else delete current[krs];
  window.localStorage.setItem(verificationKey(collection), JSON.stringify(current));
  window.dispatchEvent(new CustomEvent('company-lab:verification'));
}
async function saveVerification(collection: string, krs: string, value: LocalVerification | null) {
  const previous = loadVerifications(collection)[krs] || null;
  storeVerification(collection, krs, value);
  try {
    const response = await fetch(`/api/profiles/${krs}/verification`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status: value }),
    });
    if (!response.ok) throw new Error('Nie udało się zapisać weryfikacji w bazie.');
  } catch (error) {
    storeVerification(collection, krs, previous);
    throw error;
  }
}
export type ProfileCollection = {
  id: string; created_at: string;
  summary: { business_counts?: Record<string,number>; profiles: number; with_summary: number; counts: Record<string, number>; name_signal_missing_summary: number; selected_with_financials: number; note: string; rejected: number };
};
type Profile = {
  classification?: { business_type:string; reason:string; is_active:boolean|null; annual_period:string|null; annual_revenue:number|null; annual_profit:number|null; grounding_status:string };
  address_correction?: { source:string; note:string };
  krs: string; name: string; city: string | null; region: string | null; website: string | null;
  provider_status?: string | null; is_currently_suspended?: boolean | null; primary_pkd?: { code: string; version: string | null } | null;
  latest_standalone?: { period_end: string | null; currency: string | null; revenue: string | null } | null;
  financial_history?: { periods: number; revenue_periods: number; latest_revenue_period: string | null; latest_revenue_currency: string | null; latest_revenue: string | null } | null;
  summary: string | null; summary_pointer: string | null; source?: string | null; source_sha256: string; provider_updated_at: string | null;
  screening: { status: string; reason: string; flags: string[]; evidence: string[]; segment: string; name_signal: boolean; name_signal_reason?: string | null; method?: string | null; verified?: boolean | null };
  activities: { code: string; version: string | null; is_primary: boolean | null; description?: string | null; issues?: string[]; target_match?: boolean | null; source_pointer?: string | null }[];
  financials?: Record<string, any>[]; financial_notes: string[];
  company_info?: Record<string, any>; profile_details?: Record<string, any>;
  people?: Record<string, any>[]; related_companies?: Record<string, any>[];
  graph?: { nodes?: Record<string, any>[]; edges?: Record<string, any>[] };
  roles?: Record<string, any>[]; ownership?: Record<string, any>[];
  ownership_family_insight?: any; similar_companies?: Record<string, any>[];
  subsidiary_companies?: Record<string, any>[]; change_history?: Record<string, any>[];
  statistics?: any; insights_by_year?: any; seo_metric_summaries_by_year?: any;
  faq?: Record<string, any>[]; pkd_rankings?: Record<string, any>[];
  primary_pkd_description?: any; connections?: Record<string, any>; raw_profile?: Record<string, any>;
  financial_quality?: { periods: number; with_revenue: number; with_ebit: number; with_provider_ebitda: number; with_calculated_ebitda: number; status: 'complete' | 'partial' | 'missing' };
  verification?: any;
  verification_status?: LocalVerification | null;
};

function Feedback({ loading, error }: { loading: boolean; error?: string }) {
  return error ? <p className="notice error" role="alert">{error}</p> : loading ? <p className="state" role="status">Pobieranie profili…</p> : null;
}

export function ProfileOverview({ collection, onBrowse, onResearch }: { collection: ProfileCollection; onBrowse: (status: string) => void; onResearch: () => void }) {
  const s = collection.summary;
  const distribution = Object.entries(s.business_counts || {}).sort((a, b) => b[1] - a[1]);
  const classified = distribution.reduce((sum, [, count]) => sum + count, 0);
  return <>
    <section className="observatory">
      <div className="observatory-intro"><h1>Firmy.<br />Liczby.<br /><span>Perspektywa.</span></h1>
        <p>Za każdą firmą stoją liczby. Sprawdź wyniki, prześledź powiązania i zobacz szerszy obraz.</p>
        <button className="primary" onClick={() => onBrowse('all')}>Przeglądaj firmy <span aria-hidden="true">→</span></button>
        <button className="research-link" onClick={onResearch}>Przejdź do badań <span aria-hidden="true">↗</span></button>
      </div>
      <section className="database-exhibit" aria-labelledby="database-title">
        <div className="exhibit-heading"><h2 id="database-title">Przekrój bazy</h2><span>{fmt(s.profiles)} firm</span></div>
        {classified > 0 ? <>
          <div className="distribution-chart" aria-hidden="true">{distribution.map(([key,count], index) => <div key={key} className={`distribution-part tone-${index}`} style={{flex: count}} title={`${businessLabels[key] || key}: ${fmt(count)}`} />)}</div>
          <dl className="distribution-legend">{distribution.map(([key,count], index) => <div key={key}><dt><i className={`tone-${index}`} aria-hidden="true" />{businessLabels[key] || key}</dt><dd>{fmt(count)}<small>{(100 * count / classified).toLocaleString('pl-PL', {maximumFractionDigits: 1})}%</small></dd></div>)}</dl>
        </> : <p>Podział według działalności nie jest jeszcze dostępny.</p>}
        <p className="exhibit-note">Klasyfikacja automatyczna na podstawie nazwy, PKD, opisu i historii przychodów. Wymaga weryfikacji.</p>
      </section>
    </section>
    <div className="coverage-strip"><span><b>{fmt(s.with_summary)}</b> firm z opisem działalności</span><span><b>{fmt(s.counts.developer_candidate || 0)}</b> deweloperów według opisu</span><span><b>{fmt(s.selected_with_financials)}</b> z tej grupy ma finanse</span></div>
    <div className="overview-bottom"><section className="browse-index"><h2>Przeglądaj według opisu</h2>
      {Object.entries(labels).map(([key, label]) => <div className="cohort" key={key}><button className="text-button" onClick={() => onBrowse(key)}>{label} →</button><strong>{key === 'name_signal' ? fmt(s.name_signal_missing_summary) : fmt(s.counts[key] || 0)}</strong></div>)}
    </section><section className="method-note"><h2>Co kryje się za klasyfikacją?</h2>
      <p>W katalogu dostępna jest nowa klasyfikacja uwzględniająca nazwę, PKD, wcześniejszy opis i przebieg przychodów. Poniższe liczniki zachowują wcześniejszy podział według opisu. Oznaczenie „Deweloper według opisu” jest wstępną wskazówką, którą możesz zweryfikować w profilu firmy.</p>
      <details className="friendly-details"><summary>Jak działała wcześniejsza klasyfikacja?</summary>
      <p>Do domyślnej listy trafiają opisy wskazujące wprost dewelopera nieruchomości albo budowę i sprzedaż własnej oferty. Sam PKD, słowo „development” w nazwie lub usługi budowlane nie wystarczają.</p>
        <p>Rozbieżne nazwy, opisy całej grupy i niejednoznaczne role wymagają sprawdzenia. Brak opisu uniemożliwia kwalifikację według opisu. Badanie eksploracyjne uwzględnia również wybrane nazwy związane z deweloperką; to osobna, mniej pewna grupa.</p>
      <p className="muted">{s.note} Przesiew korzysta z jawnych reguł tekstowych; przy każdej firmie możesz odczytać uzasadnienie i oryginalny opis.</p>
      </details>
      <p className="muted">Brak opisu nie oznacza braku działalności ani braku finansów. Otwórz firmę, aby sprawdzić dostępne informacje.</p>
    </section></div>
    {s.rejected > 0 && <p className="notice">Pliki wymagające naprawy przed importem: {s.rejected}.</p>}
  </>;
}

export function ProfileCatalog({ collection, initialStatus, onSelect }: { collection: string; initialStatus: string; onSelect: (krs: string) => void }) {
  const [business, setBusiness] = useState('all');
  const [activity, setActivity] = useState('all');
  const [verification, setVerification] = useState('all');
  const [ranges,setRanges] = useState<Record<string,string>>({revenue_min:'',revenue_max:'',profit_min:'',profit_max:''});
  const extra = new URLSearchParams({business_type:business,activity,verification});
  Object.entries(ranges).forEach(([key,value])=>{if(value!=='' && Number.isFinite(Number(value)))extra.set(key,value);});
  const extraQuery = extra.toString();
  const invalidRange = ['revenue','profit'].some(key=>ranges[key+'_min']!=='' && ranges[key+'_max']!=='' && Number(ranges[key+'_min'])>Number(ranges[key+'_max']));
  const [location, setLocation] = useState<LocationSelection>({city:'',region:''});
  const [query, setQuery] = useState('');
  const [q, setQ] = useState('');
  const [status, setStatus] = useState(initialStatus);
  const [segment, setSegment] = useState('all');
  const [sort, setSort] = useState<'krs' | 'name' | 'revenue' | 'year'>('krs');
  const [direction, setDirection] = useState<'asc' | 'desc'>('asc');
  const [verifications, setVerifications] = useState<Record<string, LocalVerification>>(() => loadVerifications(collection));
  const [rowVerifying, setRowVerifying] = useState<Record<string, boolean>>({});
  const [verificationRevision, setVerificationRevision] = useState(0);
  const [offset, setOffset] = useState(0);
  const tableRef = useRef<HTMLElement>(null);

  useEffect(() => {
    fetch('/api/profiles/verifications')
      .then(r => r.ok ? r.json() : {})
      .then(data => {
        setVerifications(prev => {
          const merged = { ...prev };
          Object.entries(data || {}).forEach(([k, v]: [string, any]) => {
            if (v.status === 'confirmed' || v.status === 'rejected') {
              merged[k] = v.status;
            }
          });
          return merged;
        });
      })
      .catch(() => {});
  }, [collection]);

  const handleRowVerify = async (krs: string) => {
    setRowVerifying(prev => ({ ...prev, [krs]: true }));
    const key = getStoredGeminiKey();
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (key) headers['X-Gemini-Key'] = key;

    try {
      const resp = await fetch(`/api/profiles/${krs}/verify-gemini?collection=${collection}`, {
        method: 'POST',
        headers,
        body: JSON.stringify({ api_key: key || undefined }),
      });

      if (!resp.ok) {
        const errData = await resp.json().catch(() => ({ detail: 'Błąd weryfikacji' }));
        alert(`Błąd weryfikacji dla KRS ${krs}: ${errData.detail || 'Błąd serwera'}`);
        return;
      }

      const data = await resp.json();
      const newStatus: LocalVerification | null = data.is_developer === true ? 'confirmed' : data.is_developer === false ? 'rejected' : null;
      if (newStatus) {
        storeVerification(collection, krs, newStatus);
        setVerifications(prev => ({ ...prev, [krs]: newStatus }));
      }
      setCachedGeminiResult(krs, data);
    } catch (err: any) {
      alert(`Błąd połączenia: ${err.message}`);
    } finally {
      setRowVerifying(prev => ({ ...prev, [krs]: false }));
    }
  };

  useEffect(() => { const timer = setTimeout(() => { setQ(query); setOffset(0); }, 300); return () => clearTimeout(timer); }, [query]);
  useEffect(() => { const refresh = () => { setVerifications(loadVerifications(collection)); setVerificationRevision(value => value + 1); }; window.addEventListener('company-lab:verification', refresh); return () => window.removeEventListener('company-lab:verification', refresh); }, [collection]);
  const state = useApi<{ items: Profile[]; total: number }>(`/api/profiles?collection=${collection}&status=${status}&segment=${segment}&sort=${sort}&direction=${direction}&q=${encodeURIComponent(q)}&city=${encodeURIComponent(location.city)}&region=${encodeURIComponent(location.region)}&county=${encodeURIComponent(location.county || '')}&municipality=${encodeURIComponent(location.municipality || '')}&offset=${offset}&${extraQuery}&verification_revision=${verificationRevision}`);

  useEffect(() => {
    if (state.data && state.data.total > 0 && offset >= state.data.total) {
      setOffset(0);
    }
  }, [state.data?.total, offset]);

  const total = state.data?.total || 0;
  const pageSize = 25;
  const currentPage = Math.floor(offset / pageSize) + 1;
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const hasNext = offset + pageSize < total;
  const hasPrev = offset > 0;

  const scrollToTable = () => {
    tableRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const handleNext = () => {
    if (hasNext && !state.loading) {
      setOffset(prev => prev + pageSize);
      scrollToTable();
    }
  };

  const handlePrev = () => {
    if (hasPrev && !state.loading) {
      setOffset(prev => Math.max(0, prev - pageSize));
      scrollToTable();
    }
  };

  const handleFirst = () => {
    if (hasPrev && !state.loading) {
      setOffset(0);
      scrollToTable();
    }
  };

  const handleLast = () => {
    if (hasNext && !state.loading) {
      setOffset((totalPages - 1) * pageSize);
      scrollToTable();
    }
  };

  const renderPagination = (position: 'top' | 'bottom') => {
    if (!state.data || total === 0) return null;
    return (
      <div className={`catalog-pagination-bar pagination-${position}`}>
        <div className="pagination-info">
          <span>
            Strona <strong>{currentPage}</strong> z <strong>{totalPages}</strong>
            <span className="pagination-count-badge">
              ({offset + 1}–{Math.min(offset + pageSize, total)} z {fmt(total)} firm)
            </span>
          </span>
          {state.loading && <span className="pagination-loading-hint">Wczytywanie…</span>}
        </div>
        <div className="pagination-buttons">
          <button
            type="button"
            className="pagination-btn pagination-btn-nav"
            disabled={!hasPrev || state.loading}
            onClick={handleFirst}
            title="Pierwsza strona"
            aria-label="Pierwsza strona"
          >
            « Pierwsza
          </button>
          <button
            type="button"
            className="pagination-btn pagination-btn-main"
            disabled={!hasPrev || state.loading}
            onClick={handlePrev}
            aria-label="Poprzednia strona"
          >
            ← Poprzednia
          </button>
          <span className="pagination-current-page-badge" title={`Strona ${currentPage} z ${totalPages}`}>
            {currentPage} / {totalPages}
          </span>
          <button
            type="button"
            className="pagination-btn pagination-btn-main"
            disabled={!hasNext || state.loading}
            onClick={handleNext}
            aria-label="Następna strona"
          >
            Następna →
          </button>
          <button
            type="button"
            className="pagination-btn pagination-btn-nav"
            disabled={!hasNext || state.loading}
            onClick={handleLast}
            title="Ostatnia strona"
            aria-label="Ostatnia strona"
          >
            Ostatnia »
          </button>
        </div>
      </div>
    );
  };
  const exportUrl = `/api/profiles/export.csv?collection=${encodeURIComponent(collection)}&status=${encodeURIComponent(status)}&segment=${encodeURIComponent(segment)}&q=${encodeURIComponent(q)}&city=${encodeURIComponent(location.city)}&region=${encodeURIComponent(location.region)}&county=${encodeURIComponent(location.county || '')}&municipality=${encodeURIComponent(location.municipality || '')}&${extraQuery}`;
  const extraFilters = { business_type: business, activity, verification, revenue_min: ranges.revenue_min ? Number(ranges.revenue_min) : null, revenue_max: ranges.revenue_max ? Number(ranges.revenue_max) : null, profit_min: ranges.profit_min ? Number(ranges.profit_min) : null, profit_max: ranges.profit_max ? Number(ranges.profit_max) : null };
  const [exporting, setExporting] = useState(false);
  const [exportError,setExportError] = useState('');
  const financialSummaryFor = (profile: Profile) => {
    const latest = profile.latest_standalone;
    const history = profile.financial_history;
    const latestHasRevenue = latest?.revenue != null && latest.revenue !== '';
    const revenue = latestHasRevenue ? latest?.revenue : history?.latest_revenue;
    const period = latestHasRevenue ? latest?.period_end : history?.latest_revenue_period;
    const currency = latestHasRevenue ? latest?.currency : history?.latest_revenue_currency || latest?.currency;
    return { revenue, period, currency, historical: !latestHasRevenue && revenue != null && revenue !== '', periods: history?.periods || 0, revenuePeriods: history?.revenue_periods || 0, latestPeriod: latest?.period_end };
  };
  const qualityFor = (profile: Profile) => {
    const latest = profile.latest_standalone;
    const summary = financialSummaryFor(profile);
    if (!latest && !summary.periods) return { label: 'Brak okresu', className: 'quality-missing' };
    if (summary.revenue != null && summary.revenue !== '') return summary.historical ? { label: `Przychód historyczny ${summary.period?.slice(0, 4) || ''}`, className: 'quality-history' } : { label: `Przychód ${summary.period?.slice(0, 4) || ''}`, className: 'quality-ok' };
    if (summary.periods) return { label: 'Dane bez przychodu', className: 'quality-partial' };
    return { label: 'Brak przychodu', className: 'quality-partial' };
  };
  const downloadExport = async () => {
    setExporting(true); setExportError('');
    try {
      const { submitJob } = await import('./api');
      const params: Record<string, string> = {
        collection, status, segment, q,
        city: location.city, region: location.region,
        county: location.county || '', municipality: location.municipality || '',
        business_type: extraFilters.business_type || 'all',
        activity: extraFilters.activity || 'all',
        verification: extraFilters.verification || 'all',
      };
      if (extraFilters.revenue_min != null) params.revenue_min = String(extraFilters.revenue_min);
      if (extraFilters.revenue_max != null) params.revenue_max = String(extraFilters.revenue_max);
      if (extraFilters.profit_min != null) params.profit_min = String(extraFilters.profit_min);
      if (extraFilters.profit_max != null) params.profit_max = String(extraFilters.profit_max);
      const { job_id } = await submitJob('/api/jobs/export-csv', params);
      setExportError(`Zadanie w kolejce (${job_id.slice(0, 8)}…). Czekam na wynik…`);
      let attempts = 0;
      while (attempts < 150) {
        await new Promise(resolve => setTimeout(resolve, 2000));
        const statusResponse = await fetch(`/api/jobs/${job_id}`, { headers: { Accept: 'application/json' } });
        if (!statusResponse.ok) break;
        const jobData = await statusResponse.json();
        if (jobData.progress) setExportError(`Eksport: ${jobData.progress}`);
        if (jobData.status === 'finished') {
          const resultResponse = await fetch(`/api/jobs/${job_id}/result`);
          if (!resultResponse.ok) throw new Error('Nie udało się pobrać wyniku eksportu.');
          const blob = await resultResponse.blob();
          const link = document.createElement('a');
          const url = URL.createObjectURL(blob);
          link.href = url; link.download = 'company-lab-profile-export.csv'; link.click();
          window.setTimeout(() => URL.revokeObjectURL(url), 1000);
          setExportError('');
          return;
        }
        if (jobData.status === 'failed') throw new Error('Zadanie eksportu zakończyło się błędem.');
        attempts++;
      }
      if (attempts >= 150) throw new Error('Eksport przekroczył limit czasu.');
    } catch (e: unknown) {
      const message = e instanceof Error ? e.message : '';
      if (message.includes('503') || message.includes('Redis') || message.includes('kolejka')) {
        try {
          setExportError('Redis niedostępny — pobieranie bezpośrednie…');
          const response = await fetch(exportUrl);
          if (!response.ok) throw new Error('Nie udało się wyeksportować wyników.');
          const blob = await response.blob();
          const link = document.createElement('a');
          const url = URL.createObjectURL(blob);
          link.href = url; link.download = 'company-lab-profile-export.csv'; link.click();
          window.setTimeout(() => URL.revokeObjectURL(url), 1000);
          setExportError('');
          return;
        } catch { setExportError('Nie udało się pobrać eksportu. Nie zapisano niepełnych wyników.'); }
      } else {
        setExportError(message || 'Nie udało się pobrać eksportu.');
      }
    } finally { setExporting(false); }
  };
  const visibleItems = state.data ? [...state.data.items].sort((left, right) => {
    const value = (profile: Profile) => sort === 'name' ? (profile.name || '').toLocaleLowerCase() : sort === 'revenue' ? Number(financialSummaryFor(profile).revenue || Number.NEGATIVE_INFINITY) : sort === 'year' ? (profile.latest_standalone?.period_end || '') : profile.krs;
    const a = value(left), b = value(right);
    const result = typeof a === 'number' && typeof b === 'number' ? a - b : String(a).localeCompare(String(b), 'pl');
    return direction === 'asc' ? result : -result;
  }) : [];
const REVENUE_STEPS = [
  { value: '', label: '0 zł' },
  { value: '100000', label: '100 tys. zł' },
  { value: '250000', label: '250 tys. zł' },
  { value: '500000', label: '500 tys. zł' },
  { value: '1000000', label: '1 mln zł' },
  { value: '2000000', label: '2 mln zł' },
  { value: '5000000', label: '5 mln zł' },
  { value: '10000000', label: '10 mln zł' },
  { value: '25000000', label: '25 mln zł' },
  { value: '50000000', label: '50 mln zł' },
  { value: '100000000', label: '100 mln zł' },
  { value: '250000000', label: '250 mln zł' },
  { value: '500000000', label: '500 mln zł' },
  { value: '1000000000', label: '1 mld zł' },
  { value: '', label: 'Bez limitu' },
];

function valueToStepIndex(val: string, isMax: boolean): number {
  if (!val || val === '') return isMax ? REVENUE_STEPS.length - 1 : 0;
  const num = Number(val);
  if (!Number.isFinite(num)) return isMax ? REVENUE_STEPS.length - 1 : 0;
  let closestIdx = isMax ? REVENUE_STEPS.length - 1 : 0;
  let minDiff = Infinity;
  for (let i = 0; i < REVENUE_STEPS.length; i++) {
    const stepVal = REVENUE_STEPS[i].value;
    if (stepVal === '') continue;
    const diff = Math.abs(Number(stepVal) - num);
    if (diff < minDiff) {
      minDiff = diff;
      closestIdx = i;
    }
  }
  return closestIdx;
}

function formatRevenueBadge(minVal: string, maxVal: string): string {
  const hasMin = minVal !== '' && Number.isFinite(Number(minVal)) && Number(minVal) > 0;
  const hasMax = maxVal !== '' && Number.isFinite(Number(maxVal));
  const formatVal = (v: string) => {
    const n = Number(v);
    if (n >= 1_000_000_000) return `${(n / 1_000_000_000).toLocaleString('pl-PL')} mld zł`;
    if (n >= 1_000_000) return `${(n / 1_000_000).toLocaleString('pl-PL')} mln zł`;
    if (n >= 1_000) return `${(n / 1_000).toLocaleString('pl-PL')} tys. zł`;
    return `${n.toLocaleString('pl-PL')} zł`;
  };
  if (!hasMin && !hasMax) return 'Bez ograniczenia';
  if (hasMin && !hasMax) return `od ${formatVal(minVal)}`;
  if (!hasMin && hasMax) return `do ${formatVal(maxVal)}`;
  return `${formatVal(minVal)} – ${formatVal(maxVal)}`;
}

function RevenueRangeFilter({
  ranges,
  setRanges,
  setOffset,
}: {
  ranges: Record<string, string>;
  setRanges: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  setOffset: React.Dispatch<React.SetStateAction<number>>;
}) {
  const maxStep = REVENUE_STEPS.length - 1;
  const minIdx = valueToStepIndex(ranges.revenue_min, false);
  const maxIdx = valueToStepIndex(ranges.revenue_max, true);
  const [minZ, setMinZ] = useState(5);
  const [maxZ, setMaxZ] = useState(6);

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const hoverStep = ratio * maxStep;
    if (Math.abs(hoverStep - minIdx) < Math.abs(hoverStep - maxIdx)) {
      setMinZ(10);
      setMaxZ(5);
    } else {
      setMinZ(5);
      setMaxZ(10);
    }
  };

  const updateRange = (newMinIdx: number, newMaxIdx: number) => {
    const minVal = newMinIdx === 0 ? '' : REVENUE_STEPS[newMinIdx].value;
    const maxVal = newMaxIdx === maxStep ? '' : REVENUE_STEPS[newMaxIdx].value;
    setRanges(prev => ({ ...prev, revenue_min: minVal, revenue_max: maxVal }));
    setOffset(0);
  };

  const handleTrackClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if ((e.target as HTMLElement).classList.contains('stylish-range-input')) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
    const clickStep = Math.round(ratio * maxStep);
    const distToMin = Math.abs(clickStep - minIdx);
    const distToMax = Math.abs(clickStep - maxIdx);
    if (distToMin < distToMax) {
      const nextMin = Math.min(clickStep, maxIdx);
      updateRange(nextMin, maxIdx);
    } else {
      const nextMax = Math.max(clickStep, minIdx);
      updateRange(minIdx, nextMax);
    }
  };

  return (
    <div className="revenue-filter-card">
      <div className="revenue-header">
        <div className="revenue-title-group">
          <span className="revenue-label">Przychód (PLN)</span>
          <span className="revenue-badge">{formatRevenueBadge(ranges.revenue_min, ranges.revenue_max)}</span>
        </div>
        {(ranges.revenue_min !== '' || ranges.revenue_max !== '') && (
          <button
            type="button"
            className="revenue-reset-mini"
            onClick={() => {
              setRanges(prev => ({ ...prev, revenue_min: '', revenue_max: '' }));
              setOffset(0);
            }}
            title="Resetuj filtr przychodu"
          >
            ✕ Resetuj
          </button>
        )}
      </div>

      <div className="dual-slider-box" onMouseMove={handleMouseMove} onClick={handleTrackClick}>
        <div className="dual-slider-track">
          <div
            className="dual-slider-fill"
            style={{
              left: `${(minIdx / maxStep) * 100}%`,
              width: `${Math.max(0, ((maxIdx - minIdx) / maxStep) * 100)}%`,
            }}
          />
        </div>

        <input
          type="range"
          min={0}
          max={maxStep}
          value={minIdx}
          aria-label="Minimalny przychód"
          className="stylish-range-input stylish-range-min"
          style={{ zIndex: minZ }}
          onChange={e => {
            const nextMin = Number(e.target.value);
            if (nextMin > maxIdx) {
              updateRange(nextMin, nextMin);
            } else {
              updateRange(nextMin, maxIdx);
            }
          }}
        />

        <input
          type="range"
          min={0}
          max={maxStep}
          value={maxIdx}
          aria-label="Maksymalny przychód"
          className="stylish-range-input stylish-range-max"
          style={{ zIndex: maxZ }}
          onChange={e => {
            const nextMax = Number(e.target.value);
            if (nextMax < minIdx) {
              updateRange(nextMax, nextMax);
            } else {
              updateRange(minIdx, nextMax);
            }
          }}
        />
      </div>

      <div className="dual-slider-labels">
        <span>0 zł</span>
        <span>1 mln</span>
        <span>10 mln</span>
        <span>50 mln</span>
        <span>Bez limitu</span>
      </div>

      <div className="revenue-presets">
        <button
          type="button"
          className={`revenue-preset-btn ${ranges.revenue_min === '' && ranges.revenue_max === '' ? 'active' : ''}`}
          onClick={() => {
            setRanges(prev => ({ ...prev, revenue_min: '', revenue_max: '' }));
            setOffset(0);
          }}
        >
          Wszystkie
        </button>
        <button
          type="button"
          className={`revenue-preset-btn ${ranges.revenue_min === '' && ranges.revenue_max === '1000000' ? 'active' : ''}`}
          onClick={() => {
            setRanges(prev => ({ ...prev, revenue_min: '', revenue_max: '1000000' }));
            setOffset(0);
          }}
        >
          &lt; 1 mln zł
        </button>
        <button
          type="button"
          className={`revenue-preset-btn ${ranges.revenue_min === '1000000' && ranges.revenue_max === '10000000' ? 'active' : ''}`}
          onClick={() => {
            setRanges(prev => ({ ...prev, revenue_min: '1000000', revenue_max: '10000000' }));
            setOffset(0);
          }}
        >
          1 – 10 mln zł
        </button>
        <button
          type="button"
          className={`revenue-preset-btn ${ranges.revenue_min === '10000000' && ranges.revenue_max === '50000000' ? 'active' : ''}`}
          onClick={() => {
            setRanges(prev => ({ ...prev, revenue_min: '10000000', revenue_max: '50000000' }));
            setOffset(0);
          }}
        >
          10 – 50 mln zł
        </button>
        <button
          type="button"
          className={`revenue-preset-btn ${ranges.revenue_min === '50000000' && ranges.revenue_max === '' ? 'active' : ''}`}
          onClick={() => {
            setRanges(prev => ({ ...prev, revenue_min: '50000000', revenue_max: '' }));
            setOffset(0);
          }}
        >
          &gt; 50 mln zł
        </button>
      </div>

      <div className="revenue-inputs-row">
        <span>Dokładnie:</span>
        <input
          type="number"
          step="any"
          placeholder="Od (PLN)"
          aria-label="Przychód od (PLN)"
          value={ranges.revenue_min}
          onChange={e => {
            setRanges(prev => ({ ...prev, revenue_min: e.target.value }));
            setOffset(0);
          }}
        />
        <span>–</span>
        <input
          type="number"
          step="any"
          placeholder="Do (PLN)"
          aria-label="Przychód do (PLN)"
          value={ranges.revenue_max}
          onChange={e => {
            setRanges(prev => ({ ...prev, revenue_max: e.target.value }));
            setOffset(0);
          }}
        />
      </div>
    </div>
  );
}

  return <><div className="catalog-heading"><h1>Katalog firm<span>.</span></h1><p>Wyniki finansowe, historia i powiązania.<br />Znajdź firmę i zajrzyj głębiej.</p></div>
    <label className="catalog-search">Szukaj firmy<input aria-label="Szukaj w profilach" placeholder="Nazwa, KRS, miasto lub słowo w opisie…" value={query} onChange={e => setQuery(e.target.value)} /></label>
    <p className="filter-context">Wyświetlasz: <strong>{status === 'all' ? 'wszystkie firmy' : labels[status]}</strong>. {status !== 'all' && <button className="text-button" onClick={() => { setStatus('all'); setOffset(0); }}>Pokaż wszystkie firmy →</button>}</p>
    <div className="verification-filter-bar">
      <label>Stan weryfikacji<select aria-label="Filtr weryfikacji firmy" value={verification} onChange={event => { setVerification(event.target.value); setOffset(0); }}>
        {Object.entries(verificationLabels).map(([value, label]) => <option value={value} key={value}>{label}</option>)}
      </select></label>
      <p><strong>{verificationLabels[verification]}</strong><span>Decyzje ręczne i wyniki Gemini zapisane w bazie. Filtr wpływa także na eksport CSV i mapę finansową.</span></p>
    </div>
    <details className="catalog-panel"><summary>Działalność i wyniki finansowe <span>{business !== 'all' || activity !== 'all' || verification !== 'all' || Object.values(ranges).some(Boolean) ? 'Filtry aktywne' : 'Ustaw filtry'}</span></summary>
      <div className="enrichment-filters">
        <label>Profil działalności<select aria-label="Nowa klasyfikacja" value={business} onChange={e=>{setBusiness(e.target.value);setStatus('all');setOffset(0);}}><option value="all">Wszystkie profile działalności</option>{Object.entries(businessLabels).map(([key,label])=><option key={key} value={key}>{label}</option>)}</select></label>
        <label>Aktywność<select value={activity} onChange={e=>{setActivity(e.target.value);setOffset(0);}}><option value="all">Wszystkie statusy</option><option value="active">Aktywne</option><option value="inactive">Nieaktywne / zawieszone</option></select></label>
        <RevenueRangeFilter ranges={ranges} setRanges={setRanges} setOffset={setOffset} />
        <label>Zysk netto od (PLN)<input type="number" step="any" value={ranges.profit_min} placeholder="Bez ograniczenia" onChange={e=>{setRanges(prev=>({...prev,profit_min:e.target.value}));setOffset(0);}} /></label>
        <label>Zysk netto do (PLN)<input type="number" step="any" value={ranges.profit_max} placeholder="Bez ograniczenia" onChange={e=>{setRanges(prev=>({...prev,profit_max:e.target.value}));setOffset(0);}} /></label>
        <button onClick={()=>{setBusiness('all');setActivity('all');setVerification('all');setRanges({revenue_min:'',revenue_max:'',profit_min:'',profit_max:''});setOffset(0);}}>Wyczyść filtry</button>
      </div>
      <p className="muted">Kwoty dotyczą ostatniego pełnego roku kalendarzowego w PLN, sprawozdanie jednostkowe. Rok jest podany przy firmie. Brak wartości nie oznacza zera. Klasyfikacja według reguł nie jest weryfikacją w sieci.</p>
      {invalidRange && <p role="alert">Dolna granica nie może być większa od górnej.</p>}
      {business==='needs_web_grounding' && <p className="notice">Firmy oczekują na sprawdzenie źródeł. Gemini Search Grounding nie jest podłączone; ta etykieta nie potwierdza działalności deweloperskiej.</p>}
    </details>
    <details className="catalog-panel"><summary>Lokalizacja na mapie <span>{location.city || location.region || location.county || location.municipality ? 'Filtry aktywne' : 'Cała Polska'}</span></summary><LocationMap extraQuery={extraQuery} collection={collection} query={q} status={status} segment={segment} selection={location} onChange={value => { setLocation(value); setOffset(0); }} /></details>
    <div className="toolbar profile-toolbar">
      <details className="catalog-filters"><summary>Filtry i sortowanie</summary><div className="catalog-filter-options">
      <label>Rodzaj działalności<select aria-label="Kwalifikacja działalności" value={status} onChange={e => { setStatus(e.target.value); setOffset(0); }}>
        {Object.entries(labels).map(([key,label]) => <option value={key} key={key}>{label}</option>)}<option value="all">Wszystkie pobrane profile</option>
      </select></label>
      <label>Segment<select aria-label="Segment dewelopera" value={segment} onChange={e => { setSegment(e.target.value); setOffset(0); }}>
        <option value="all">Wszystkie segmenty</option>{Object.entries(segments).map(([key,label]) => <option value={key} key={key}>{label}</option>)}
      </select></label>
      <label>Sortowanie<select aria-label="Sortowanie" value={sort} onChange={e => { setSort(e.target.value as typeof sort); setOffset(0); }}>
        <option value="krs">Sortuj: KRS</option><option value="name">Sortuj: nazwa</option><option value="revenue">Sortuj: przychód</option><option value="year">Sortuj: ostatni rok</option>
      </select></label>
      <button aria-label="Zmień kierunek sortowania" title="Zmień kierunek sortowania" onClick={() => { setDirection(value => value === 'asc' ? 'desc' : 'asc'); setOffset(0); }}>{direction === 'asc' ? 'Rosnąco ↑' : 'Malejąco ↓'}</button>
      <button className="button-link" onClick={downloadExport} disabled={exporting}>{exporting ? 'Przygotowuję…' : 'Eksport CSV ↓'}</button>
      </div></details>
    </div>{exportError && <p className="notice" role="alert">{exportError}</p>}<Feedback {...state} />
    {state.data && <section ref={tableRef} className="card table-card"><div className="section-title"><h2>{verification === 'all' ? (status === 'all' ? 'Wszystkie profile' : labels[status]) : verificationLabels[verification]}</h2><span>{fmt(state.data.total)} firm</span></div>
      {(location.city || location.region || location.county || location.municipality) && (() => {
        const getList = (v?: string) => v ? v.split(',').map(s => s.trim()).filter(Boolean) : [];
        const cities = getList(location.city);
        const regions = getList(location.region);
        const counties = getList(location.county);
        const municipalities = getList(location.municipality);
        const totalFilters = cities.length + regions.length + counties.length + municipalities.length;

        const removeCity = (c: string) => {
          const next = cities.filter(x => x !== c).join(',');
          setLocation(prev => ({ ...prev, city: next, cities: next ? next.split(',') : [] }));
          setOffset(0);
        };
        const removeRegion = (r: string) => {
          const next = regions.filter(x => x !== r).join(',');
          setLocation(prev => ({ ...prev, region: next, regions: next ? next.split(',') : [] }));
          setOffset(0);
        };
        const removeCounty = (c: string) => {
          const next = counties.filter(x => x !== c).join(',');
          setLocation(prev => ({ ...prev, county: next, counties: next ? next.split(',') : [] }));
          setOffset(0);
        };
        const removeMuni = (m: string) => {
          const next = municipalities.filter(x => x !== m).join(',');
          setLocation(prev => ({ ...prev, municipality: next, municipalities: next ? next.split(',') : [] }));
          setOffset(0);
        };

        return (
          <div className="active-location-banner" style={{ margin: '4px 0 14px', display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
            <span style={{ fontSize: '12px', color: '#526962', fontWeight: 600 }}>Wybrane lokalizacje:</span>
            {regions.map(r => (
              <span key={`r-${r}`} style={{ fontSize: '13px', background: '#e3f2ed', color: '#17473b', padding: '4px 10px', borderRadius: '14px', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                📍 Woj. {r}
                <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#17473b', fontWeight: 'bold', fontSize: '13px', padding: '0 2px' }} title={`Usuń filtr woj. ${r}`} onClick={() => removeRegion(r)}>✕</button>
              </span>
            ))}
            {counties.map(c => (
              <span key={`c-${c}`} style={{ fontSize: '13px', background: '#e0f2fe', color: '#0369a1', padding: '4px 10px', borderRadius: '14px', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                📍 Powiat {c}
                <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#0369a1', fontWeight: 'bold', fontSize: '13px', padding: '0 2px' }} title={`Usuń filtr powiat ${c}`} onClick={() => removeCounty(c)}>✕</button>
              </span>
            ))}
            {municipalities.map(m => (
              <span key={`m-${m}`} style={{ fontSize: '13px', background: '#e0e7ff', color: '#3730a3', padding: '4px 10px', borderRadius: '14px', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                📍 Gmina {m}
                <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#3730a3', fontWeight: 'bold', fontSize: '13px', padding: '0 2px' }} title={`Usuń filtr gmina ${m}`} onClick={() => removeMuni(m)}>✕</button>
              </span>
            ))}
            {cities.map(ct => (
              <span key={`ct-${ct}`} style={{ fontSize: '13px', background: '#fef3c7', color: '#92400e', padding: '4px 10px', borderRadius: '14px', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                📍 {ct}
                <button style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#92400e', fontWeight: 'bold', fontSize: '13px', padding: '0 2px' }} title={`Usuń filtr ${ct}`} onClick={() => removeCity(ct)}>✕</button>
              </span>
            ))}
            {totalFilters > 1 && (
              <button
                style={{ fontSize: '12px', background: 'none', border: '1px solid #c4cdca', color: '#526962', padding: '3px 8px', borderRadius: '12px', cursor: 'pointer' }}
                onClick={() => { setLocation({ city: '', region: '', county: '', municipality: '' }); setOffset(0); }}
              >
                Wyczyść wszystkie
              </button>
            )}
          </div>
        );
      })()}
      {renderPagination('top')}
      <p className="scroll-hint desktop-catalog-hint">Przewiń tabelę w poziomie, aby zobaczyć wszystkie kolumny i otworzyć profil firmy.</p><div className="table-scroll desktop-catalog" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie"><table className="catalog-table"><thead><tr><th>Firma / KRS</th><th>Lokalizacja</th><th>PKD główne</th><th>Przychód / status</th><th>Jakość finansów</th><th>Kwalifikacja</th><th>Weryfikacja / Profil</th></tr></thead><tbody>
        {visibleItems.map(p => {
          const quality = qualityFor(p);
          const summary = financialSummaryFor(p);
          const hasRevenue = summary.revenue != null && summary.revenue !== '';
          const local = verifications[p.krs] || p.verification_status || undefined;
          const cls = p.classification;
          const statusLabel = p.provider_status === 'active' ? 'aktywna' : p.provider_status === 'inactive' ? 'nieaktywna' : p.provider_status;
          return <tr key={p.krs}>
            <td><button className="text-button firm-name" onClick={() => onSelect(p.krs)}>{p.name || p.krs}</button><br /><span className="muted">{p.krs}</span></td>
            <td>{[p.city,p.region].filter(Boolean).join(', ') || 'Brak danych'}</td>
            <td><span className="mono">{p.primary_pkd?.code || 'Brak'}</span><br /><span className="muted">{p.primary_pkd?.version || ''}</span></td>
            <td className="revenue-cell">
              <span className="revenue-amount">{hasRevenue ? `${amount(summary.revenue)} ${summary.currency || ''}` : 'Brak danych'}</span><br />
              <span className="muted">{hasRevenue ? `${summary.historical ? 'ostatni przychód ' : ''}${summary.period?.slice(0,4) || ''}` : summary.latestPeriod?.slice(0,4) || ''}{statusLabel ? ` · ${statusLabel}` : ''}</span>
            </td>
            <td><span className={`quality-pill ${quality.className}`} title={summary.historical ? 'Najnowszy okres nie zawiera przychodu; pokazujemy ostatni dostępny rok z przychodem.' : undefined}>{quality.label}</span></td>
            <td>
              {local === 'rejected' ? (
                <span className="tag tag-rejected" title="Zweryfikowano negatywnie: firma nie prowadzi działalności deweloperskiej">✕ Nie deweloper</span>
              ) : local === 'confirmed' ? (
                <span className="tag tag-confirmed" title="Zweryfikowano pozytywnie: potwierdzony deweloper">✓ Deweloper</span>
              ) : (
                <span className="tag" title={cls?.reason}>{cls ? businessLabels[cls.business_type] : labels[p.screening.status]}</span>
              )}
              {cls && <div className="business-note">
                {cls.is_active === false ? 'Nieaktywna / zawieszona · ' : ''}
                {cls.annual_period?.slice(0,4) || 'Brak pełnego roku'}
                {cls.annual_revenue != null && ` · przychód ${amount(cls.annual_revenue)} PLN`}
                {cls.annual_profit != null && ` · zysk ${amount(cls.annual_profit)} PLN`}
              </div>}
              <div className={`muted local-verification-note ${local ? 'local-verification' : ''}`}>
                {local === 'confirmed' ? '✓ Potwierdzona weryfikacją' : local === 'rejected' ? '✕ Wykluczona (brak działalności)' : 'Automatyczny przesiew'}
              </div>
            </td>
            <td>
              <div className="table-actions-row">
                <button
                  type="button"
                  className={`row-verify-btn ${rowVerifying[p.krs] ? 'loading' : ''} ${local ? 'verified' : ''}`}
                  onClick={() => handleRowVerify(p.krs)}
                  disabled={rowVerifying[p.krs]}
                  title={local ? 'Ponów weryfikację AI (zapisze wynik w bazie)' : 'Sprawdź firmę przez Gemini AI (od razu zaktualizuje status)'}
                >
                  {rowVerifying[p.krs] ? (
                    <>
                      <span className="row-spinner" aria-hidden="true" />
                      Sprawdzam…
                    </>
                  ) : local ? (
                    '↻ Ponów AI'
                  ) : (
                    '✨ Weryfikuj AI'
                  )}
                </button>
                <button className="open-profile-btn" onClick={() => onSelect(p.krs)}>Otwórz profil →</button>
              </div>
            </td>
          </tr>;
        })}
      </tbody></table></div>
      <div className="mobile-catalog-list" aria-label="Lista firm">
        {visibleItems.map(p => { const quality = qualityFor(p); const summary = financialSummaryFor(p); const hasRevenue = summary.revenue != null && summary.revenue !== ''; const local = verifications[p.krs] || p.verification_status || undefined; return <article className="mobile-company-card" key={p.krs}>
          <div className="mobile-company-heading"><div><button className="text-button firm-name" onClick={() => onSelect(p.krs)}>{p.name || p.krs}</button><span className="mono">KRS {p.krs}</span></div><span className={`quality-pill ${quality.className}`}>{quality.label}</span></div>
          <dl className="mobile-company-facts">
            <div><dt>Lokalizacja</dt><dd>{[p.city,p.region].filter(Boolean).join(', ') || 'Brak danych'}</dd></div>
            <div><dt>PKD główne</dt><dd>{p.primary_pkd?.code || 'Brak'}{p.primary_pkd?.version ? ` · ${p.primary_pkd.version}` : ''}</dd></div>
            <div><dt>Przychód</dt><dd>{hasRevenue ? `${amount(summary.revenue)} ${summary.currency || ''}` : 'Brak'}<small>{hasRevenue ? `${summary.historical ? 'ostatni dostępny · ' : ''}${summary.period?.slice(0,4) || ''}` : summary.latestPeriod?.slice(0,4) || ''}</small></dd></div>
            <div><dt>Status</dt><dd>{p.provider_status === 'active' ? 'Aktywna' : p.provider_status === 'inactive' ? 'Nieaktywna' : p.provider_status || 'Nieznany'}</dd></div>
          </dl>
          <div className="mobile-company-tags">
            {local === 'rejected' ? (
              <span className="tag tag-rejected">✕ Nie deweloper</span>
            ) : local === 'confirmed' ? (
              <span className="tag tag-confirmed">✓ Deweloper</span>
            ) : (
              <span className="tag" title={p.classification?.reason}>{p.classification ? businessLabels[p.classification.business_type] : labels[p.screening.status]}</span>
            )}
            {p.classification && <div className="business-note">{p.classification.is_active===false?'Nieaktywna / zawieszona · ':''}{p.classification.annual_period?.slice(0,4) || 'Brak pełnego roku'} · przychód {amount(p.classification.annual_revenue)} PLN · zysk {amount(p.classification.annual_profit)} PLN</div>}
            {p.screening.name_signal && <span className="tag">Sygnał w nazwie</span>}
            {local && <span className={`local-verification ${local === 'rejected' ? 'local-rejected' : ''}`}>{local === 'confirmed' ? '✓ Potwierdzona' : '✕ Wykluczona'}</span>}
          </div>
          <div className="mobile-card-actions">
            <button
              type="button"
              className={`row-verify-btn ${rowVerifying[p.krs] ? 'loading' : ''} ${local ? 'verified' : ''}`}
              onClick={() => handleRowVerify(p.krs)}
              disabled={rowVerifying[p.krs]}
              title={local ? 'Ponów weryfikację AI (zapisze wynik w bazie)' : 'Sprawdź firmę przez Gemini AI (od razu zaktualizuje status)'}
            >
              {rowVerifying[p.krs] ? (
                <>
                  <span className="row-spinner" aria-hidden="true" />
                  Sprawdzam…
                </>
              ) : local ? (
                '↻ Ponów AI'
              ) : (
                '✨ Weryfikuj AI'
              )}
            </button>
            <button className="mobile-open-profile" onClick={() => onSelect(p.krs)}>Otwórz profil <span aria-hidden="true">→</span></button>
          </div>
        </article>; })}
      </div>
      {renderPagination('bottom')}
    </section>}
  </>;
}

function websiteUrl(value: string | null) {
  if (!value) return null;
  try { const url = new URL(value.includes('://') ? value : `https://${value}`); return ['http:','https:'].includes(url.protocol) ? url.href : null; } catch { return null; }
}
const amount = (value: string | number | null | undefined) => value == null ? 'Brak danych' : Number.isFinite(Number(value)) ? Number(value).toLocaleString('pl-PL', { maximumFractionDigits: 2 }) : 'Wymaga sprawdzenia';
const scopes: Record<string, string> = { standalone: 'jednostkowe', consolidated: 'skonsolidowane' };

type FinancialRecord = Record<string, any>;
type FinancialRow = { record: FinancialRecord; year: number | null; index: number; derived: Record<string, number | null> };
type MetricKind = 'amount' | 'percent' | 'ratio';
type MetricDefinition = { key: string; label: string; kind: MetricKind };

const financialAmountMetrics: MetricDefinition[] = [
  { key: 'revenue_total', label: 'Przychody razem', kind: 'amount' },
  { key: 'profit_net', label: 'Zysk netto', kind: 'amount' },
  { key: 'ebit', label: 'EBIT', kind: 'amount' },
  { key: 'ebitda', label: 'EBITDA', kind: 'amount' },
  { key: 'total_assets', label: 'Aktywa razem', kind: 'amount' },
  { key: 'current_assets', label: 'Aktywa obrotowe', kind: 'amount' },
  { key: 'cash_and_equivalents', label: 'Środki pieniężne', kind: 'amount' },
  { key: 'short_term_receivables', label: 'Należności krótkoterminowe', kind: 'amount' },
  { key: 'equity', label: 'Kapitał własny', kind: 'amount' },
  { key: 'liabilities_and_provisions', label: 'Zobowiązania i rezerwy', kind: 'amount' },
  { key: 'short_term_liabilities', label: 'Zobowiązania krótkoterminowe', kind: 'amount' },
  { key: 'long_term_liabilities', label: 'Zobowiązania długoterminowe', kind: 'amount' },
  { key: 'liabilities_borrowings', label: 'Kredyty i pożyczki', kind: 'amount' },
  { key: 'interest_expense', label: 'Koszty odsetkowe', kind: 'amount' },
];
const providerRatioMetrics: MetricDefinition[] = [
  { key: 'roa', label: 'ROA', kind: 'percent' },
  { key: 'roe', label: 'ROE', kind: 'percent' },
  { key: 'net_margin', label: 'Marża netto', kind: 'percent' },
  { key: 'ebitda_margin', label: 'Marża EBITDA', kind: 'percent' },
  { key: 'asset_turnover', label: 'Obrót aktywów', kind: 'ratio' },
  { key: 'current_ratio', label: 'Wskaźnik bieżącej płynności', kind: 'ratio' },
  { key: 'cash_ratio', label: 'Wskaźnik płynności gotówkowej', kind: 'ratio' },
  { key: 'liabilities_to_total_assets', label: 'Zobowiązania / aktywa', kind: 'percent' },
  { key: 'cash_to_total_assets', label: 'Gotówka / aktywa', kind: 'percent' },
  { key: 'receivables_to_total_assets', label: 'Należności / aktywa', kind: 'percent' },
];
const derivedMetrics: MetricDefinition[] = [
  { key: 'debt_to_equity', label: 'Zobowiązania / kapitał własny', kind: 'percent' },
  { key: 'ebit_margin', label: 'Marża EBIT', kind: 'percent' },
  { key: 'financial_cost_ratio', label: 'Koszty finansowe / przychody', kind: 'percent' },
  { key: 'gross_margin', label: 'Marża brutto', kind: 'percent' },
  { key: 'operating_cost_ratio', label: 'Koszty operacyjne / przychody', kind: 'percent' },
];

function numeric(value: string | number | null | undefined) {
  if (value == null || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function periodYear(record: FinancialRecord) {
  const value = record.period_to_resolved || record.sf_period_to || '';
  const match = value.match(/(\d{4})/);
  return match ? Number(match[1]) : null;
}

function enrichFinancials(financials: FinancialRecord[]): FinancialRow[] {
  const ordered = financials.map((record, index) => ({ record, index, year: periodYear(record) }))
    .sort((a, b) => (a.year ?? 0) - (b.year ?? 0) || a.index - b.index);
  return ordered.map(item => {
    const current = item.record;
    const previous = item.year == null ? undefined : ordered.find(candidate => candidate.year === item.year! - 1 && (candidate.record.currency || '') === (current.currency || '') && (candidate.record.consolidation_scope || '') === (current.consolidation_scope || ''));
    const sameCurrencyAndScope = !!previous && ordered.filter(candidate => candidate.year === previous.year && (candidate.record.currency || '') === (current.currency || '') && (candidate.record.consolidation_scope || '') === (current.consolidation_scope || '')).length === 1;
    const change = (key: string) => {
      const now = numeric(current[key]);
      const before = sameCurrencyAndScope && previous ? numeric(previous.record[key]) : null;
      return now != null && before != null && before !== 0 ? (now / before - 1) * 100 : null;
    };
    const assets = numeric(current.total_assets);
    const equity = numeric(current.equity);
    const liabilities = numeric(current.liabilities_and_provisions);
    const revenue = numeric(current.revenue_total);
    const ebit = numeric(current.ebit);
    const currentAssets = numeric(current.current_assets);
    const shortTermLiabilities = numeric(current.short_term_liabilities);
    const borrowings = numeric(current.liabilities_borrowings);
    const cash = numeric(current.cash_and_equivalents);
    const derived: Record<string, number | null> = {
      equity_ratio: assets != null && assets !== 0 && equity != null ? equity / assets * 100 : null,
      debt_to_equity: equity != null && equity !== 0 && liabilities != null ? liabilities / equity * 100 : null,
      ebit_margin: revenue != null && revenue !== 0 && ebit != null ? ebit / revenue * 100 : null,
      working_capital: currentAssets != null && shortTermLiabilities != null ? currentAssets - shortTermLiabilities : null,
      net_debt: borrowings != null && cash != null ? borrowings - cash : null,
      revenue_growth_yoy: change('revenue_total'),
      profit_growth_yoy: change('profit_net'),
      assets_growth_yoy: change('total_assets'),
      equity_growth_yoy: change('equity'),
    };
    return { ...item, derived };
  });
}

function metricValue(row: FinancialRow, definition: MetricDefinition) {
  return definition.key in row.derived ? row.derived[definition.key] : numeric(row.record[definition.key]);
}

function formatMetric(value: string | number | null | undefined, kind: MetricKind) {
  const parsed = numeric(value);
  if (parsed == null) return '—';
  const formatted = parsed.toLocaleString('pl-PL', { maximumFractionDigits: 2 });
  return kind === 'amount' ? formatted : kind === 'percent' ? `${formatted} %` : `${formatted}×`;
}

function periodLabel(row: FinancialRow) {
  const end = row.record.period_to_resolved || row.record.sf_period_to || '';
  const from = row.record.period_from_resolved || row.record.sf_period_from || '';
  const scope = scopes[row.record.consolidation_scope || ''] || row.record.consolidation_scope || 'zakres nieznany';
  return `${from || '?'} – ${end || '?'} · ${row.record.currency || '?'} / ${scope}`;
}

function FinancialMatrix({ rows, definitions }: { rows: FinancialRow[]; definitions: MetricDefinition[] }) {
  if (!rows.length) return <p className="state">Brak danych dla tego zestawu wskaźników.</p>;
  return <div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie"><table className="financial-matrix"><thead><tr><th>Wskaźnik</th>{rows.map((row, index) => <th key={`${row.index}-${index}`} title={periodLabel(row)}>{row.year || '?'}<small>{row.record.currency || '?'}</small></th>)}</tr></thead><tbody>{definitions.map(definition => <tr key={definition.key}><th>{definition.label}</th>{rows.map(row => <td key={`${row.index}-${definition.key}`}>{formatMetric(metricValue(row, definition), definition.kind)}</td>)}</tr>)}</tbody></table></div>;
}

function niceScale(min: number, max: number, targetTicks = 5) {
  if (min === max) {
    if (min === 0) {
      min = 0;
      max = 1;
    } else if (min > 0) {
      min = 0;
      max = min * 1.5;
    } else {
      max = 0;
      min = min * 1.5;
    }
  }
  // If values are non-negative and min is relatively small, start from 0 for clear perspective
  if (min >= 0 && min < max * 0.35) {
    min = 0;
  }
  // If values are non-positive and max is relatively small, end at 0
  if (max <= 0 && max > min * 0.35) {
    max = 0;
  }
  const span = max - min;
  const rawStep = span / (targetTicks - 1);
  const mag = Math.pow(10, Math.floor(Math.log10(rawStep)));
  const frac = rawStep / mag;
  let niceFrac = 1;
  if (frac <= 1.2) niceFrac = 1;
  else if (frac <= 2.5) niceFrac = 2;
  else if (frac <= 3.5) niceFrac = 2.5;
  else if (frac <= 7) niceFrac = 5;
  else niceFrac = 10;
  const step = niceFrac * mag;
  const niceMin = Math.floor(min / step) * step;
  const niceMax = Math.ceil(max / step) * step;
  const ticks: number[] = [];
  const count = Math.round((niceMax - niceMin) / step);
  for (let i = 0; i <= count; i++) {
    ticks.push(Number((niceMin + i * step).toFixed(10)));
  }
  return { min: niceMin, max: niceMax, step, ticks };
}

function formatChartTick(value: number, kind: MetricKind, currency = 'PLN') {
  const currLabel = currency === 'PLN' ? 'zł' : currency;
  if (value === 0) return kind === 'percent' ? '0 %' : kind === 'ratio' ? '0×' : `0 ${currLabel}`;
  const abs = Math.abs(value);
  const sign = value < 0 ? '−' : '';
  if (kind === 'amount') {
    if (abs >= 1_000_000_000) {
      const num = (abs / 1_000_000_000).toLocaleString('pl-PL', { maximumFractionDigits: 1 });
      return `${sign}${num} mld ${currLabel}`;
    }
    if (abs >= 1_000_000) {
      const num = (abs / 1_000_000).toLocaleString('pl-PL', { maximumFractionDigits: 1 });
      return `${sign}${num} mln ${currLabel}`;
    }
    if (abs >= 1_000) {
      const num = (abs / 1_000).toLocaleString('pl-PL', { maximumFractionDigits: 1 });
      return `${sign}${num} tys. ${currLabel}`;
    }
    return `${sign}${abs.toLocaleString('pl-PL', { maximumFractionDigits: 0 })} ${currLabel}`;
  }
  if (kind === 'percent') {
    return `${value.toLocaleString('pl-PL', { maximumFractionDigits: 1 })} %`;
  }
  if (kind === 'ratio') {
    return `${value.toLocaleString('pl-PL', { maximumFractionDigits: 2 })}×`;
  }
  return value.toLocaleString('pl-PL');
}

function FinancialChart({ rows, title, series, phases }: { rows: FinancialRow[]; title: string; series: { key: string; label: string; color: string; kind: MetricKind }[]; phases?: Record<number, YearPhaseInfo> }) {
  const values = series.flatMap(item => rows.map(row => numeric(metricValue(row, { key: item.key, label: item.label, kind: item.kind })))).filter((v): v is number => v != null);
  if (!values.length) return <section className="financial-chart card"><h3>{title}</h3><p className="state">Brak wystarczających danych do wykresu.</p></section>;
  const currency = rows[0]?.record?.currency || 'PLN';
  const width = 820, height = 285, right = 24, top = 26, bottom = 48;
  const mn = Math.min(...values), mx = Math.max(...values);
  const { min: niceMin, max: niceMax, ticks } = niceScale(mn, mx, 5);
  const labels = ticks.map(t => formatChartTick(t, series[0].kind, currency));
  const maxLabelLen = Math.max(...labels.map(l => l.length));
  const left = Math.max(70, maxLabelLen * 7.5 + 20);
  const xPos = (index: number) => left + (width - left - right) * (rows.length <= 1 ? 0.5 : index / (rows.length - 1));
  const yPos = (val: number) => top + (height - top - bottom) * (niceMax - val) / (niceMax - niceMin || 1);
  return (
    <section className="financial-chart card">
      <div className="section-title">
        <h3>{title}</h3>
        <div className="chart-legend">{series.map(item => <span key={item.key}><i style={{ background: item.color }} />{item.label}</span>)}</div>
      </div>
      <ZoomableSvg className="chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label={title}>
        <defs>{series.map(item => <linearGradient key={`grad-${item.key}`} id={`area-${item.key}`} x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stopColor={item.color} stopOpacity="0.18" /><stop offset="100%" stopColor={item.color} stopOpacity="0.02" /></linearGradient>)}</defs>
        {ticks.map((tickVal, i) => {
          const ty = yPos(tickVal);
          const isZero = Math.abs(tickVal) < 1e-9;
          return <g key={tickVal}><line x1={left} x2={width - right} y1={ty} y2={ty} className={isZero ? 'chart-grid chart-grid-zero' : 'chart-grid'} stroke={isZero ? '#94a3b8' : undefined} strokeWidth={isZero ? 1.5 : undefined} /><text x={left - 8} y={ty + 4} textAnchor="end" style={isZero ? { fontWeight: 600, fill: '#334155' } : undefined}>{labels[i]}</text></g>;
        })}
        {series.map(item => {
          const pts = rows.map((row, idx) => { const v = numeric(metricValue(row, { key: item.key, label: item.label, kind: item.kind })); return v == null ? null : { value: v, index: idx }; }).filter((p): p is { value: number; index: number } => p != null);
          const areaBase = yPos(niceMin);
          return <g key={item.key}>
            {pts.length > 1 && <><polygon points={`${xPos(pts[0].index)},${areaBase} ${pts.map(p => `${xPos(p.index)},${yPos(p.value)}`).join(' ')} ${xPos(pts[pts.length - 1].index)},${areaBase}`} fill={`url(#area-${item.key})`} /><polyline points={pts.map(p => `${xPos(p.index)},${yPos(p.value)}`).join(' ')} fill="none" stroke={item.color} strokeWidth="2.5" strokeLinejoin="round" /></>}
            {pts.map((pt, pi) => { const yr = rows[pt.index]?.year; const pInfo = yr != null && phases ? phases[yr] : null; const tip = `${yr || '?'}: ${formatMetric(pt.value, item.kind)}${pInfo ? ` · ${pInfo.phaseLabel}` : ''}`; const isLast = pi === pts.length - 1; return <circle key={pt.index} cx={xPos(pt.index)} cy={yPos(pt.value)} r={isLast ? '5.5' : '4'} fill={item.color} stroke={isLast ? '#fff' : 'none'} strokeWidth={isLast ? '2' : '0'}><title>{tip}</title></circle>; })}
          </g>;
        })}
        {rows.map((row, index) => { const yr = row.year; const pInfo = yr != null && phases ? phases[yr] : null; return <g key={`${row.index}-label`}><text x={xPos(index)} y={height - 24} textAnchor="middle">{yr || '?'}</text>{pInfo && <text x={xPos(index)} y={height - 10} textAnchor="middle" style={{ fontSize: '10px', fontWeight: 600, fill: pInfo.phase === 'delivery' ? '#166534' : pInfo.phase === 'construction' ? '#92400e' : '#64748b' }}>{pInfo.shortLabel}</text>}</g>; })}
      </ZoomableSvg>
      <p className="muted">Wykres obejmuje tylko okresy z porównywalną walutą i zakresem sprawozdania.</p>
    </section>
  );
}

function compactFinancialAmount(value: number | null, currency: string) {
  if (value == null) return '—';
  const absolute = Math.abs(value);
  const sign = value < 0 ? '−' : '';
  if (absolute >= 1_000_000) return `${sign}${(absolute / 1_000_000).toLocaleString('pl-PL', { maximumFractionDigits: 2 })} mln ${currency}`;
  if (absolute >= 1_000) return `${sign}${(absolute / 1_000).toLocaleString('pl-PL', { maximumFractionDigits: 1 })} tys. ${currency}`;
  return `${value.toLocaleString('pl-PL', { maximumFractionDigits: 2 })} ${currency}`;
}

function polishDate(value: string | null | undefined) {
  if (!value) return '?';
  const match = String(value).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return match ? `${match[3]}.${match[2]}.${match[1]}` : String(value);
}

function statementValue(record: FinancialRecord, keys: string[]) {
  for (const key of keys) {
    const value = numeric(record[key]);
    if (value != null) return value;
  }
  return null;
}

function StatementComparison({ record }: { record: FinancialRecord }) {
  const currency = record.currency || 'PLN';
  const totalRevenue = statementValue(record, ['revenue_total', 'revenue_operating']);
  // "Przychody razem" is a separate provider field.  Prefer the
  // net-sales line for the left-hand source so the chart does not show the
  // same amount twice under two different labels.
  const salesRevenue = statementValue(record, ['revenue_net_sales_products', 'revenue_other_sales']);
  const displayedSales = salesRevenue ?? totalRevenue;
  const otherIncome = statementValue(record, ['other_oper_income']);
  const operatingCosts = statementValue(record, ['operating_costs_total']);
  const profit = statementValue(record, ['profit_net']);
  const breakdown = [
    { label: 'Materiały i energia', value: statementValue(record, ['cost_materials_energy']), color: '#e76b67' },
    { label: 'Usługi obce', value: statementValue(record, ['cost_external_services']), color: '#ed8178' },
    { label: 'Wynagrodzenia', value: statementValue(record, ['cost_wages']), color: '#ef9489' },
    { label: 'Amortyzacja', value: statementValue(record, ['cost_amortization']), color: '#f1a69b' },
    { label: 'Pozostałe koszty', value: statementValue(record, ['cost_other_generic', 'other_oper_costs']), color: '#f4b8ad' },
    { label: 'Koszty finansowe', value: statementValue(record, ['financial_costs', 'interest_expense']), color: '#f6c9c1' },
  ].filter(item => item.value != null && item.value !== 0) as { label: string; value: number; color: string }[];
  const comparison = [
    {label: 'Przychody razem', value: totalRevenue, kind: 'income'},
    {label: 'Koszty operacyjne', value: operatingCosts, kind: 'cost'},
    {label: profit != null && profit < 0 ? 'Strata netto' : 'Zysk netto', value: profit, kind: profit != null && profit < 0 ? 'loss' : 'profit'},
  ];
  const available = comparison.filter(item => item.value != null);
  if (!available.length) return <p className="state">Brak pozycji do porównania przychodów, kosztów i wyniku.</p>;
  const scale = Math.max(1, ...available.map(item => Math.abs(item.value!)));
  const detailRows = [
    {label: salesRevenue != null ? 'Przychody ze sprzedaży' : 'Przychody z działalności', value: displayedSales},
    {label: 'Pozostałe przychody operacyjne', value: otherIncome},
    ...breakdown,
  ].filter(item => item.value != null);
  return <div className="statement-comparison">
    <h4>Przychody, koszty i wynik</h4>
    <dl className="statement-bars">{comparison.map(item => <div className={`statement-bar ${item.kind}`} key={item.label}>
      <div><dt>{item.label}</dt><dd>{compactFinancialAmount(item.value, currency)}</dd></div>
      <div className="statement-bar-track" aria-hidden="true"><span style={{width: `${item.value == null ? 0 : Math.abs(item.value) / scale * 100}%`}} /></div>
    </div>)}</dl>
    <p className="muted">Długość pasków odpowiada wartości bezwzględnej kwot. Zysk netto uwzględnia również pozostałe pozycje i podatek.</p>
    {!!detailRows.length && <details className="statement-breakdown"><summary>Składowe przychodów i kosztów</summary><dl>{detailRows.map(item => <div key={item.label}><dt>{item.label}</dt><dd>{compactFinancialAmount(item.value, currency)}</dd></div>)}</dl><p className="muted">Wybrane pozycje ze sprawozdania. Nie stanowią pełnego rozliczenia wyniku.</p></details>}
  </div>;
}

function FinancialStatementOverview({ rows }: { rows: FinancialRow[] }) {
  const selectable = rows.filter(row => row.year != null);
  const defaultRow = [...selectable].reverse().find(row => ['revenue_total', 'revenue_operating', 'total_assets', 'profit_net'].some(key => numeric(row.record[key]) != null)) || selectable.at(-1);
  const [selectedIndex, setSelectedIndex] = useState(defaultRow?.index ?? null);
  const selected = selectable.find(row => row.index === selectedIndex) || defaultRow;
  if (!selected) return null;
  const sameScope = rows.filter(row => row.year != null && row.year < (selected.year || Number.MAX_SAFE_INTEGER) && (row.record.currency || '') === (selected.record.currency || '') && (row.record.consolidation_scope || '') === (selected.record.consolidation_scope || ''));
  const previous = sameScope.at(-1);
  const currency = selected.record.currency || 'PLN';
  const cardDefinitions = [
    { key: 'revenue_total', label: 'Przychody razem' },
    { key: 'operating_costs_total', label: 'Koszty operacyjne' },
    { key: 'total_assets', label: 'Aktywa razem' },
    { key: 'equity', label: 'Kapitał własny' },
  ];
  const changeText = (key: string) => {
    const current = numeric(selected.record[key]);
    const before = previous ? numeric(previous.record[key]) : null;
    if (current == null || before == null || before === 0) return { text: 'brak porównania', className: 'statement-change neutral' };
    const change = (current / before - 1) * 100;
    return { text: `${change >= 0 ? '+' : ''}${change.toLocaleString('pl-PL', { maximumFractionDigits: 1 })}% vs ${previous?.year || 'poprzedni rok'}`, className: `statement-change ${change >= 0 ? 'up' : 'down'}` };
  };
  const scopeLabel = scopes[selected.record.consolidation_scope || ''] || selected.record.consolidation_scope || 'zakres nieznany';
  const from = selected.record.period_from_resolved || selected.record.sf_period_from;
  const to = selected.record.period_to_resolved || selected.record.sf_period_to;
  return <section className="statement-overview"><div className="statement-header"><h3>Wynik finansowy firmy</h3><div className="statement-controls"><label>Rok<select aria-label="Rok sprawozdania" value={selected.index} onChange={event => setSelectedIndex(Number(event.target.value))}>{[...selectable].reverse().map(row => <option key={row.index} value={row.index}>{row.year} · {row.record.currency || '?'} · {scopes[row.record.consolidation_scope || ''] || row.record.consolidation_scope || '?'}</option>)}</select></label><span className="statement-period">{polishDate(from)} — {polishDate(to)}</span></div></div><p className="muted">Kwoty ze sprawozdania za wybrany okres. Zmiana względem poprzedniego porównywalnego roku.</p><div className="statement-cards">{cardDefinitions.map(definition => { const value = statementValue(selected.record, [definition.key]); const change = changeText(definition.key); return <div className="statement-card" key={definition.key}><span>{definition.label}</span><strong>{compactFinancialAmount(value, currency)}</strong><small className={change.className}>{change.text}</small></div>; })}</div><StatementComparison record={selected.record} /></section>;
}

type TrendDefinition = MetricDefinition & { higherIsBetter: boolean };
const trendDefinitions: TrendDefinition[] = [
  { key: 'roa', label: 'ROA', kind: 'percent', higherIsBetter: true },
  { key: 'roe', label: 'ROE', kind: 'percent', higherIsBetter: true },
  { key: 'net_margin', label: 'Marża netto', kind: 'percent', higherIsBetter: true },
  { key: 'ebit_margin', label: 'Marża EBIT', kind: 'percent', higherIsBetter: true },
  { key: 'current_ratio', label: 'Płynność bieżąca', kind: 'ratio', higherIsBetter: true },
  { key: 'liabilities_to_total_assets', label: 'Zobowiązania / aktywa', kind: 'percent', higherIsBetter: false },
  { key: 'debt_to_equity', label: 'Zobowiązania / kapitał własny', kind: 'percent', higherIsBetter: false },
];

export type CycleMetrics = {
  sumNetProfit: number | null;
  sumRevenue: number | null;
  sumEBIT: number | null;
  sumAvgAssets: number | null;
  sumAvgEquity: number | null;
  cycleROA: number | null;
  cycleROE: number | null;
  cycleNetMargin: number | null;
  cycleEBITMargin: number | null;
  startYear: number | null;
  endYear: number | null;
  periodCount: number;
};

function calculateCycleMetrics(rows: FinancialRow[]): CycleMetrics {
  let sumNetProfit = 0, hasProfit = false;
  let sumRevenue = 0, hasRevenue = false;
  let sumEBIT = 0, hasEBIT = false;
  let sumAvgAssets = 0, hasAssets = false;
  let sumAvgEquity = 0, hasEquity = false;

  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const prev = i > 0 && rows[i - 1].year != null && row.year != null && rows[i - 1].year === row.year - 1
      ? rows[i - 1]
      : null;

    const profit = numeric(row.record.profit_net);
    if (profit != null) {
      sumNetProfit += profit;
      hasProfit = true;
    }

    const revenue = numeric(row.record.revenue_total);
    if (revenue != null) {
      sumRevenue += revenue;
      hasRevenue = true;
    }

    const ebit = numeric(row.record.ebit);
    if (ebit != null) {
      sumEBIT += ebit;
      hasEBIT = true;
    }

    const currentAssets = numeric(row.record.total_assets);
    if (currentAssets != null) {
      const prevAssets = prev ? numeric(prev.record.total_assets) : null;
      const avgAsset = prevAssets != null ? (prevAssets + currentAssets) / 2 : currentAssets;
      sumAvgAssets += avgAsset;
      hasAssets = true;
    }

    const currentEquity = numeric(row.record.equity);
    if (currentEquity != null) {
      const prevEquity = prev ? numeric(prev.record.equity) : null;
      const avgEq = prevEquity != null ? (prevEquity + currentEquity) / 2 : currentEquity;
      sumAvgEquity += avgEq;
      hasEquity = true;
    }
  }

  const cycleROA = hasProfit && hasAssets && sumAvgAssets > 0 ? (sumNetProfit / sumAvgAssets) * 100 : null;
  const cycleROE = hasProfit && hasEquity && sumAvgEquity > 0 ? (sumNetProfit / sumAvgEquity) * 100 : null;
  const cycleNetMargin = hasProfit && hasRevenue && sumRevenue > 0 ? (sumNetProfit / sumRevenue) * 100 : null;
  const cycleEBITMargin = hasEBIT && hasRevenue && sumRevenue > 0 ? (sumEBIT / sumRevenue) * 100 : null;

  return {
    sumNetProfit: hasProfit ? sumNetProfit : null,
    sumRevenue: hasRevenue ? sumRevenue : null,
    sumEBIT: hasEBIT ? sumEBIT : null,
    sumAvgAssets: hasAssets ? sumAvgAssets : null,
    sumAvgEquity: hasEquity ? sumAvgEquity : null,
    cycleROA,
    cycleROE,
    cycleNetMargin,
    cycleEBITMargin,
    startYear: rows[0]?.year ?? null,
    endYear: rows.at(-1)?.year ?? null,
    periodCount: rows.length,
  };
}

export type CyclePhase = 'construction' | 'delivery' | 'mixed';

export type YearPhaseInfo = {
  year: number | null;
  phase: CyclePhase;
  phaseLabel: string;
  shortLabel: string;
  reason: string;
};

function median(values: number[]): number | null {
  if (!values.length) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const mid = Math.floor(sorted.length / 2);
  return sorted.length % 2 !== 0 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
}

function determineCyclePhases(rows: FinancialRow[]): Record<number, YearPhaseInfo> {
  const revenues = rows.map(r => numeric(r.record.revenue_total)).filter((v): v is number => v != null);
  const ebits = rows.map(r => numeric(r.record.ebit)).filter((v): v is number => v != null);
  const medRevenue = median(revenues);
  const medEbit = median(ebits);

  const result: Record<number, YearPhaseInfo> = {};

  for (let i = 0; i < rows.length; i++) {
    const row = rows[i];
    const prev = i > 0 ? rows[i - 1] : null;
    const year = row.year;
    if (year == null) continue;

    const rev = numeric(row.record.revenue_total);
    const ebit = numeric(row.record.ebit);
    const inv = numeric(row.record.inventories);
    const prevInv = prev ? numeric(prev.record.inventories) : null;
    const debt = numeric(row.record.liabilities_borrowings);
    const prevDebt = prev ? numeric(prev.record.liabilities_borrowings) : null;
    const cash = numeric(row.record.cash_and_equivalents);
    const prevCash = prev ? numeric(prev.record.cash_and_equivalents) : null;

    let constructionScore = 0;
    let deliveryScore = 0;
    const notes: string[] = [];

    // Inventories dynamic
    if (inv != null && prevInv != null && prevInv > 0) {
      const invGrowth = (inv - prevInv) / prevInv;
      if (invGrowth > 0.08) {
        constructionScore += 1.5;
        notes.push('rosnące zapasy (+ ' + (invGrowth * 100).toFixed(0) + '%)');
      } else if (invGrowth < -0.05) {
        deliveryScore += 1.2;
        notes.push('spadek zapasów (' + (invGrowth * 100).toFixed(0) + '%)');
      }
    }

    // Revenue dynamic vs median
    if (rev != null && medRevenue != null && medRevenue > 0) {
      if (rev > medRevenue * 1.08) {
        deliveryScore += 1.5;
        notes.push('wysokie przychody vs mediana');
      } else if (rev < medRevenue * 0.88) {
        constructionScore += 1.0;
        notes.push('niższe przychody vs mediana');
      }
    }

    // EBIT / profitability
    if (ebit != null && medEbit != null) {
      if (ebit > 0 && ebit > medEbit) {
        deliveryScore += 1.0;
        notes.push('wysoki EBIT');
      } else if (ebit <= 0 || ebit < medEbit * 0.75) {
        constructionScore += 1.0;
        notes.push('niski/ujemny EBIT');
      }
    }

    // Borrowings / debt growth
    if (debt != null && prevDebt != null && prevDebt > 0) {
      if (debt > prevDebt * 1.1) {
        constructionScore += 0.5;
        notes.push('wzrost długu');
      }
    }

    // Cash change
    if (cash != null && prevCash != null) {
      if (cash > prevCash) {
        deliveryScore += 0.5;
        notes.push('wzrost gotówki');
      }
    }

    let phase: CyclePhase = 'mixed';
    let phaseLabel = 'Faza mieszana';
    let shortLabel = 'Mieszana';

    if (constructionScore >= 2.0 && constructionScore > deliveryScore + 0.5) {
      phase = 'construction';
      phaseLabel = 'Prawdopodobna faza: budowa / inwestycje';
      shortLabel = 'Budowa';
    } else if (deliveryScore >= 2.0 && deliveryScore > constructionScore + 0.5) {
      phase = 'delivery';
      phaseLabel = 'Prawdopodobna faza: przekazania / sprzedaż';
      shortLabel = 'Sprzedaż';
    }

    result[year] = {
      year,
      phase,
      phaseLabel,
      shortLabel,
      reason: notes.join(', ') || 'brak wyraźnego sygnału kierunkowego',
    };
  }

  return result;
}

function generateAnalyticalCommentary(
  cycle: CycleMetrics,
  phases: Record<number, YearPhaseInfo>,
  latestRow: FinancialRow | undefined,
  firstRow: FinancialRow | undefined,
  smoothedRoa: { firstAvg: number; lastAvg: number; diff: number } | null,
  medianRoa: number | null
): string {
  if (!latestRow || !firstRow) {
    return 'Brak wystarczających danych do przeprowadzenia pełnej analizy cyklu.';
  }
  const latestYear = latestRow.year || 'ostatni';
  const firstYear = firstRow.year || 'początek';
  const latestRoa = numeric(metricValue(latestRow, { key: 'roa', label: 'ROA', kind: 'percent' }));
  const firstRoa = numeric(metricValue(firstRow, { key: 'roa', label: 'ROA', kind: 'percent' }));
  const latestPhase = latestRow.year ? phases[latestRow.year] : null;

  const parts: string[] = [];

  // 1. Comparison of latest vs first year and median
  if (latestRoa != null && firstRoa != null && medianRoa != null) {
    const diff = latestRoa - firstRoa;
    const diffFromMedian = latestRoa - medianRoa;
    const roaFmt = (v: number) => `${v.toLocaleString('pl-PL', { maximumFractionDigits: 1 })}%`;

    if (diff < -1.0) {
      if (Math.abs(diffFromMedian) <= 1.5) {
        parts.push(`Ostatni rok (${latestYear}) charakteryzuje się niższą rentownością (ROA ${roaFmt(latestRoa)}) niż początek badanego okresu (${firstYear}: ${roaFmt(firstRoa)}), jednak wynik pozostaje zbliżony do historycznej mediany spółki (${roaFmt(medianRoa)}).`);
      } else if (diffFromMedian < -1.5) {
        parts.push(`Ostatni rok (${latestYear}) przyniósł spadek rentowności (ROA ${roaFmt(latestRoa)}) zarówno względem ${firstYear} roku (${roaFmt(firstRoa)}), jak i historycznej mediany (${roaFmt(medianRoa)}).`);
      } else {
        parts.push(`Mimo że rentowność w ${latestYear} roku (ROA ${roaFmt(latestRoa)}) jest niższa niż w ${firstYear} roku (${roaFmt(firstRoa)}), przewyższa wieloletnią medianę spółki (${roaFmt(medianRoa)}).`);
      }
    } else if (diff > 1.0) {
      parts.push(`Ostatni rok (${latestYear}) charakteryzuje się wyższą rentownością (ROA ${roaFmt(latestRoa)}) w porównaniu z początkiem okresu (${firstYear}: ${roaFmt(firstRoa)}) oraz historyczną medianą (${roaFmt(medianRoa)}).`);
    } else {
      parts.push(`Rentowność w ${latestYear} roku (ROA ${roaFmt(latestRoa)}) utrzymuje się na zbliżonym poziomie do początku okresu (${firstYear}: ${roaFmt(firstRoa)}) oraz wieloletniej mediany (${roaFmt(medianRoa)}).`);
    }
  }

  // 2. Cycle phase context
  if (latestPhase) {
    if (latestPhase.phase === 'construction') {
      parts.push(`W ostatnim okresie spółka znajduje się w prawdopodobnej fazie budowy i inwestycji (${latestPhase.reason}), w której kapitał jest zaangażowany w zapasy, a zyski ze sprzedaży zmaterializują się po oddaniu i przekazaniu mieszkań.`);
    } else if (latestPhase.phase === 'delivery') {
      parts.push(`W ostatnim okresie spółka realizuje fazę przekazań i sprzedaży (${latestPhase.reason}), co sprzyja wysokim przychodom i kumulacji marży ze zrealizowanych projektów.`);
    } else {
      parts.push(`W ostatnim okresie spółka znajduje się w fazie mieszanej (${latestPhase.reason}), łączącej bieżące przekazania z realizacją kolejnych etapów budowy.`);
    }
  }

  // 3. Conclusion on cycle vs single point
  if (cycle.cycleNetMargin != null && cycle.periodCount >= 3) {
    const marginFmt = `${cycle.cycleNetMargin.toLocaleString('pl-PL', { maximumFractionDigits: 1 })}%`;
    parts.push(`Ze względu na cykliczny charakter działalności deweloperskiej samo punktowe porównanie ${firstYear} z ${latestYear} nie wystarcza do oceny długoterminowej zmiany rentowności – skumulowana marża netto w całym cyklu ${cycle.startYear}–${cycle.endYear} wynosi ${marginFmt}.`);
  }

  return parts.join(' ');
}

function CycleSummaryDashboard({
  rows,
  cycle,
  phases,
}: {
  rows: FinancialRow[];
  cycle: CycleMetrics;
  phases: Record<number, YearPhaseInfo>;
}) {
  const latest = rows.at(-1);
  const first = rows[0];
  const latestYear = latest?.year;

  const latestROA = latest ? numeric(metricValue(latest, { key: 'roa', label: 'ROA', kind: 'percent' })) : null;
  const latestROE = latest ? numeric(metricValue(latest, { key: 'roe', label: 'ROE', kind: 'percent' })) : null;
  const latestNetMargin = latest ? numeric(metricValue(latest, { key: 'net_margin', label: 'Marża netto', kind: 'percent' })) : null;
  const latestEbitMargin = latest ? numeric(metricValue(latest, { key: 'ebit_margin', label: 'Marża EBIT', kind: 'percent' })) : null;

  const roaValues = rows.map(r => numeric(metricValue(r, { key: 'roa', label: 'ROA', kind: 'percent' }))).filter((v): v is number => v != null);
  const medRoa = median(roaValues);

  const N = rows.length;
  const W = N >= 6 ? 3 : N >= 4 ? 2 : 0;
  let smoothedRoa: { firstAvg: number; lastAvg: number; diff: number } | null = null;
  if (W > 0 && roaValues.length >= W * 2) {
    const fAvg = roaValues.slice(0, W).reduce((a, b) => a + b, 0) / W;
    const lAvg = roaValues.slice(roaValues.length - W).reduce((a, b) => a + b, 0) / W;
    smoothedRoa = { firstAvg: fAvg, lastAvg: lAvg, diff: lAvg - fAvg };
  }

  const commentary = generateAnalyticalCommentary(cycle, phases, latest, first, smoothedRoa, medRoa);
  const latestPhase = latestYear ? phases[latestYear] : null;

  return (
    <div className="cycle-summary-dashboard">
      <div className="cycle-perspectives-grid">
        {/* Kolumna 1: Perspektywa ostatniego roku */}
        <div className="cycle-perspective-card">
          <div className="cycle-card-header">
            <div>
              <span className="eyebrow">BIEŻĄCY STAN</span>
              <h4>Perspektywa ostatniego roku ({latestYear || '—'})</h4>
            </div>
            {latestPhase && (
              <span className={`phase-badge ${latestPhase.phase}`} title={latestPhase.reason}>
                {latestPhase.shortLabel}
              </span>
            )}
          </div>
          <div className="cycle-metrics-list">
            <div className="cycle-metric-row">
              <span>ROA:</span>
              <strong>{formatMetric(latestROA, 'percent')}</strong>
            </div>
            <div className="cycle-metric-row">
              <span>ROE:</span>
              <strong>{formatMetric(latestROE, 'percent')}</strong>
            </div>
            <div className="cycle-metric-row">
              <span>Marża netto:</span>
              <strong>{formatMetric(latestNetMargin, 'percent')}</strong>
            </div>
            <div className="cycle-metric-row">
              <span>Marża EBIT:</span>
              <strong>{formatMetric(latestEbitMargin, 'percent')}</strong>
            </div>
          </div>
        </div>

        {/* Kolumna 2: Perspektywa całego cyklu */}
        <div className="cycle-perspective-card highlight">
          <div className="cycle-card-header">
            <div>
              <span className="eyebrow">WYNIKI W CAŁYM CYKLU</span>
              <h4>Rentowność całego okresu {cycle.startYear}–{cycle.endYear}</h4>
            </div>
            <span className="cycle-period-tag">{cycle.periodCount} lat (z sum kwot)</span>
          </div>
          <div className="cycle-metrics-list">
            <div className="cycle-metric-row">
              <span>ROA okresu:</span>
              <strong>{formatMetric(cycle.cycleROA, 'percent')}</strong>
            </div>
            <div className="cycle-metric-row">
              <span>ROE okresu:</span>
              <strong>{formatMetric(cycle.cycleROE, 'percent')}</strong>
            </div>
            <div className="cycle-metric-row">
              <span>Marża netto:</span>
              <strong>{formatMetric(cycle.cycleNetMargin, 'percent')}</strong>
            </div>
            <div className="cycle-metric-row">
              <span>Marża EBIT:</span>
              <strong>{formatMetric(cycle.cycleEBITMargin, 'percent')}</strong>
            </div>
          </div>
        </div>

        {/* Kolumna 3: Trend wygładzony */}
        <div className="cycle-perspective-card">
          <div className="cycle-card-header">
            <div>
              <span className="eyebrow">WYGŁADZENIE DANYCH</span>
              <h4>Trend wygładzony {W > 0 ? `${W}-letni` : 'wieloletni'}</h4>
            </div>
            {smoothedRoa && (
              <span className={`trend-badge ${smoothedRoa.diff > 0.5 ? 'improved' : smoothedRoa.diff < -0.5 ? 'worsened' : 'steady'}`}>
                {smoothedRoa.diff > 0.5 ? 'Poprawa' : smoothedRoa.diff < -0.5 ? 'Pogorszenie' : 'Stabilnie'}
              </span>
            )}
          </div>
          <div className="cycle-metrics-list">
            {smoothedRoa ? (
              <>
                <div className="cycle-metric-row">
                  <span>Pierwsze {W} lata (ROA):</span>
                  <strong>{formatMetric(smoothedRoa.firstAvg, 'percent')}</strong>
                </div>
                <div className="cycle-metric-row">
                  <span>Ostatnie {W} lata (ROA):</span>
                  <strong>{formatMetric(smoothedRoa.lastAvg, 'percent')}</strong>
                </div>
                <div className="cycle-metric-row">
                  <span>Zmiana ROA:</span>
                  <strong className={smoothedRoa.diff > 0.5 ? 'color-up' : smoothedRoa.diff < -0.5 ? 'color-down' : ''}>
                    {smoothedRoa.diff >= 0 ? '+' : ''}{formatMetric(smoothedRoa.diff, 'percent')}
                  </strong>
                </div>
                <div className="cycle-metric-row">
                  <span>Mediana roczna ROA:</span>
                  <strong>{formatMetric(medRoa, 'percent')}</strong>
                </div>
              </>
            ) : (
              <p className="muted" style={{ fontSize: '13px', margin: '8px 0' }}>
                Zbyt mało porównywalnych lat do wyznaczenia trendu 3-letniego (wymagane min. 4 okresy).
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Komentarz analityczny */}
      <div className="cycle-commentary">
        <div className="commentary-icon">💡</div>
        <div className="commentary-body">
          <strong>Wniosek analityczny uwzględniający specyfikę cyklu deweloperskiego:</strong>
          <p>{commentary}</p>
        </div>
      </div>
    </div>
  );
}

function DeveloperCycleTimeline({
  rows,
  phases,
}: {
  rows: FinancialRow[];
  phases: Record<number, YearPhaseInfo>;
}) {
  const years = rows.map(r => r.year).filter((y): y is number => y != null);
  if (!years.length) return null;

  return (
    <div className="cycle-timeline-card">
      <div className="cycle-timeline-header">
        <div>
          <span className="eyebrow" style={{ display: 'block', marginBottom: '2px' }}>FAZA DZIAŁALNOŚCI</span>
          <strong>Szacunkowa faza cyklu deweloperskiego rok po roku</strong>
        </div>
        <p className="muted" style={{ margin: 0, fontSize: '12.5px' }}>
          Ocena orientacyjna na podstawie dynamiki zapasów, przychodów, długu i wyników.
        </p>
      </div>
      <div className="cycle-timeline-chips">
        {years.map(yr => {
          const info = phases[yr];
          if (!info) return null;
          return (
            <div
              key={yr}
              className={`cycle-chip ${info.phase}`}
              title={`${yr}: ${info.phaseLabel}\n${info.reason}`}
            >
              <span className="chip-year">{yr}</span>
              <span className={`chip-badge ${info.phase}`}>{info.shortLabel}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function TrendSparkline({
  rows,
  definition,
  values,
  cycle,
  phases,
  mode,
}: {
  rows: FinancialRow[];
  definition: TrendDefinition;
  values: { row: FinancialRow; value: number }[];
  cycle: CycleMetrics;
  phases: Record<number, YearPhaseInfo>;
  mode: 'point' | 'smoothed' | 'cycle';
}) {
  const width = 250, height = 62, pad = 7;
  const rawVals = values.map(item => item.value);
  const min = Math.min(...rawVals), max = Math.max(...rawVals);
  const span = max - min || Math.abs(max) || 1;
  const x = (index: number) => pad + (width - pad * 2) * (values.length <= 1 ? .5 : index / (values.length - 1));
  const y = (value: number) => height - pad - (height - pad * 2) * (value - (min - span * .08)) / (span * 1.16);

  const first = values[0].value;
  const latest = values.at(-1)!.value;
  const firstYear = values[0].row.year;
  const latestYear = values.at(-1)!.row.year;
  const med = median(rawVals);

  // Cycle value: use aggregated sum calculation for roa, roe, net_margin, ebit_margin
  const cycleVal =
    definition.key === 'roa' ? cycle.cycleROA :
    definition.key === 'roe' ? cycle.cycleROE :
    definition.key === 'net_margin' ? cycle.cycleNetMargin :
    definition.key === 'ebit_margin' ? cycle.cycleEBITMargin :
    rawVals.reduce((a, b) => a + b, 0) / rawVals.length;

  // 1. Point comparison
  const ptDiff = latest - first;
  const ptTol = definition.kind === 'percent' ? 0.5 : Math.max(0.03, Math.abs(first) * 0.03);
  const isPtImp = definition.higherIsBetter ? ptDiff > ptTol : ptDiff < -ptTol;
  const isPtWor = definition.higherIsBetter ? ptDiff < -ptTol : ptDiff > ptTol;
  const ptState = isPtImp ? 'improved' : isPtWor ? 'worsened' : 'steady';
  const ptLabel = isPtImp ? 'Poprawa' : isPtWor ? 'Pogorszenie' : 'Stabilnie';

  // 2. Smoothed trend
  const N = values.length;
  const W = N >= 6 ? 3 : N >= 4 ? 2 : 0;
  let firstAvg = 0, lastAvg = 0, smDiff = 0;
  let smState = 'steady', smLabel = 'Stabilnie';
  if (W > 0) {
    firstAvg = rawVals.slice(0, W).reduce((a, b) => a + b, 0) / W;
    lastAvg = rawVals.slice(N - W).reduce((a, b) => a + b, 0) / W;
    smDiff = lastAvg - firstAvg;
    const smTol = definition.kind === 'percent' ? 0.5 : Math.max(0.03, Math.abs(firstAvg) * 0.03);
    const isSmImp = definition.higherIsBetter ? smDiff > smTol : smDiff < -smTol;
    const isSmWor = definition.higherIsBetter ? smDiff < -smTol : smDiff > smTol;
    smState = isSmImp ? 'improved' : isSmWor ? 'worsened' : 'steady';
    smLabel = isSmImp ? 'Poprawa' : isSmWor ? 'Pogorszenie' : 'Stabilnie';
  }

  // 3. Position vs Median
  let posLabel = 'W pobliżu mediany';
  let posState = 'steady';
  if (med != null) {
    const medDiff = latest - med;
    const medTol = definition.kind === 'percent' ? 0.8 : Math.max(0.03, Math.abs(med) * 0.04);
    if (medDiff > medTol) {
      posLabel = 'Powyżej mediany';
      posState = definition.higherIsBetter ? 'improved' : 'worsened';
    } else if (medDiff < -medTol) {
      posLabel = 'Poniżej mediany';
      posState = definition.higherIsBetter ? 'worsened' : 'improved';
    }
  }

  // Primary badge according to active mode
  let mainState = ptState;
  let mainLabel = ptLabel;
  let subHeader = `Punktowo: ${firstYear} → ${latestYear}`;

  if (mode === 'smoothed') {
    if (W > 0) {
      mainState = smState;
      mainLabel = `Trend ${W}L: ${smLabel}`;
      subHeader = `Średnia ${W} pierwszych l. vs ${W} ostatnich l.`;
    } else {
      mainState = ptState;
      mainLabel = ptLabel;
      subHeader = `Próba < 4 lat (porównanie punktowe)`;
    }
  } else if (mode === 'cycle') {
    mainState = posState;
    mainLabel = posLabel;
    subHeader = `Ostatni rok vs mediana wieloletnia`;
  }

  const strokeColor = mainState === 'improved' ? '#2f7a52' : mainState === 'worsened' ? '#b15f4f' : '#52665b';

  return (
    <div className={`trend-card ${mainState}`}>
      <div className="trend-card-heading">
        <div>
          <strong>{definition.label}</strong>
          <small className="trend-subheading">{subHeader}</small>
        </div>
        <span className={`trend-badge ${mainState}`}>{mainLabel}</span>
      </div>

      <ZoomableSvg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${definition.label}: ${mainLabel}`}>
        <polyline
          points={values.map((item, index) => `${x(index)},${y(item.value)}`).join(' ')}
          fill="none"
          stroke={strokeColor}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {values.map((item, index) => {
          const yr = item.row.year;
          const pInfo = yr != null ? phases[yr] : null;
          return (
            <circle
              key={`${item.row.index}-${index}`}
              cx={x(index)}
              cy={y(item.value)}
              r="3.2"
              fill={strokeColor}
            >
              <title>{`${yr || '?'}: ${formatMetric(item.value, definition.kind)}${pInfo ? ` · ${pInfo.phaseLabel}` : ''}`}</title>
            </circle>
          );
        })}
      </ZoomableSvg>

      <div className="trend-card-stats">
        <div className="trend-stat-row">
          <span>{latestYear || 'Ostatni rok'}:</span>
          <strong>{formatMetric(latest, definition.kind)}</strong>
        </div>
        <div className="trend-stat-row">
          <span>Cały okres:</span>
          <strong>{formatMetric(cycleVal, definition.kind)}</strong>
        </div>
        <div className="trend-stat-row">
          <span>Mediana:</span>
          <strong>{formatMetric(med, definition.kind)}</strong>
        </div>
        <div className="trend-stat-row">
          <span>Zakres:</span>
          <small>{formatMetric(min, definition.kind)} – {formatMetric(max, definition.kind)}</small>
        </div>
      </div>

      <div className="trend-pills">
        <span className={`trend-pill ${ptState}`} title={`Zmiana punktowa ${firstYear} → ${latestYear}`}>
          Punktowo: {ptDiff >= 0 ? '+' : ''}{formatMetric(ptDiff, definition.kind)} ({ptLabel})
        </span>
        {W > 0 && (
          <span className={`trend-pill ${smState}`} title={`Trend ${W}-letni: pierwsze ${W} l. (${formatMetric(firstAvg, definition.kind)}) vs ostatnie ${W} l. (${formatMetric(lastAvg, definition.kind)})`}>
            Trend {W}L: {smDiff >= 0 ? '+' : ''}{formatMetric(smDiff, definition.kind)} ({smLabel})
          </span>
        )}
        <span className={`trend-pill ${posState}`} title={`Pozycja ostatniego roku (${formatMetric(latest, definition.kind)}) względem mediany (${formatMetric(med, definition.kind)})`}>
          {posLabel}
        </span>
      </div>
    </div>
  );
}

function TrendOverview({ rows, status }: { rows: FinancialRow[]; status?: string }) {
  const comparable = comparableRows(rows);
  const cycle = calculateCycleMetrics(comparable);
  const phases = determineCyclePhases(comparable);

  const defaultMode: 'point' | 'smoothed' | 'cycle' =
    status === 'developer_candidate'
      ? (comparable.length >= 4 ? 'smoothed' : 'cycle')
      : 'point';

  const [mode, setMode] = useState<'point' | 'smoothed' | 'cycle'>(defaultMode);

  const cards = trendDefinitions.map(definition => ({
    definition,
    values: comparable
      .map(row => ({ row, value: numeric(metricValue(row, definition)) }))
      .filter((item): item is { row: FinancialRow; value: number } => item.value != null),
  })).filter(item => item.values.length >= 2);

  if (!cards.length) return null;

  return (
    <section className="trend-overview">
      <div className="section-title">
        <div>
          <p className="eyebrow">KIERUNEK ZMIAN I CYKL DEWELOPERSKI</p>
          <h3>Czy sytuacja się poprawia w całym cyklu?</h3>
        </div>
        <div className="mode-switcher" role="group" aria-label="Tryb analizy trendu">
          <button
            type="button"
            className={mode === 'cycle' ? 'active' : ''}
            onClick={() => setMode('cycle')}
          >
            Cały cykl
          </button>
          <button
            type="button"
            className={mode === 'smoothed' ? 'active' : ''}
            onClick={() => setMode('smoothed')}
          >
            Trend wygładzony {comparable.length >= 6 ? '3-letni' : '2-letni'}
          </button>
          <button
            type="button"
            className={mode === 'point' ? 'active' : ''}
            onClick={() => setMode('point')}
          >
            Porównanie punktowe: pierwszy → ostatni rok
          </button>
        </div>
      </div>

      <CycleSummaryDashboard rows={comparable} cycle={cycle} phases={phases} />

      <DeveloperCycleTimeline rows={comparable} phases={phases} />

      <div className="trend-grid">
        {cards.map(card => (
          <TrendSparkline
            key={card.definition.key}
            rows={comparable}
            definition={card.definition}
            values={card.values}
            cycle={cycle}
            phases={phases}
            mode={mode}
          />
        ))}
      </div>
    </section>
  );
}

function comparableRows(rows: FinancialRow[]) {
  const latest = rows.at(-1);
  if (!latest) return rows;
  return rows.filter(row => (row.record.currency || '') === (latest.record.currency || '') && (row.record.consolidation_scope || '') === (latest.record.consolidation_scope || ''));
}

function FinancialSources({ rows }: { rows: FinancialRow[] }) {
  return <div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie"><table><thead><tr><th>Okres</th><th>Zakres</th><th>Dokument finansowy</th><th>Ścieżka źródłowa</th></tr></thead><tbody>{rows.map(row => <tr key={row.index}><td>{periodLabel(row)}</td><td>{scopes[row.record.consolidation_scope || ''] || row.record.consolidation_scope || 'nieznany'}</td><td className="mono">{row.record.financial_document_id || '—'}</td><td className="mono">{row.record.source_pointer || '—'}</td></tr>)}</tbody></table></div>;
}

const calculationDefinitions: Record<string, { label: string; formula: string; kind: MetricKind }> = {
  ebitda: { label: 'EBITDA', formula: 'EBIT + amortyzacja', kind: 'amount' },
  ebit: { label: 'EBIT', formula: 'wynik ze sprzedaży + pozostałe przychody − pozostałe koszty operacyjne', kind: 'amount' },
  profit_net: { label: 'Zysk netto', formula: 'zysk brutto − podatek dochodowy', kind: 'amount' },
  gross_margin: { label: 'Marża brutto', formula: 'zysk brutto / przychody × 100', kind: 'percent' },
  net_margin: { label: 'Marża netto', formula: 'zysk netto / przychody × 100', kind: 'percent' },
  ebit_margin: { label: 'Marża EBIT', formula: 'EBIT / przychody × 100', kind: 'percent' },
  ebitda_margin: { label: 'Marża EBITDA', formula: 'EBITDA / przychody × 100', kind: 'percent' },
  operating_cost_ratio: { label: 'Koszty operacyjne / przychody', formula: 'koszty operacyjne / przychody × 100', kind: 'percent' },
  financial_cost_ratio: { label: 'Koszty finansowe / przychody', formula: 'koszty finansowe / przychody × 100', kind: 'percent' },
  roa: { label: 'ROA', formula: 'zysk netto / aktywa × 100', kind: 'percent' },
  roe: { label: 'ROE', formula: 'zysk netto / kapitał własny × 100', kind: 'percent' },
  asset_turnover: { label: 'Obrót aktywów', formula: 'przychody / aktywa', kind: 'ratio' },
  current_ratio: { label: 'Płynność bieżąca', formula: 'aktywa obrotowe / zobowiązania krótkoterminowe', kind: 'ratio' },
  cash_ratio: { label: 'Płynność gotówkowa', formula: 'środki pieniężne / zobowiązania krótkoterminowe', kind: 'ratio' },
  liabilities_to_total_assets: { label: 'Zobowiązania / aktywa', formula: 'zobowiązania i rezerwy / aktywa × 100', kind: 'percent' },
  cash_to_total_assets: { label: 'Gotówka / aktywa', formula: 'środki pieniężne / aktywa × 100', kind: 'percent' },
  receivables_to_total_assets: { label: 'Należności / aktywa', formula: 'należności krótkoterminowe / aktywa × 100', kind: 'percent' },
  debt_to_equity: { label: 'Zobowiązania / kapitał własny', formula: 'zobowiązania i rezerwy / kapitał własny × 100', kind: 'percent' },
  working_capital: { label: 'Kapitał obrotowy netto', formula: 'aktywa obrotowe − zobowiązania krótkoterminowe', kind: 'amount' },
  net_debt: { label: 'Dług netto', formula: 'kredyty i pożyczki − środki pieniężne', kind: 'amount' },
};

const polishFieldWords: Record<string, string> = {
  revenue: 'przychody', total: 'razem', net: 'netto', profit: 'zysk', assets: 'aktywa', liabilities: 'zobowiązania',
  equity: 'kapitał własny', cash: 'gotówka', current: 'bieżące', short: 'krótkoterminowe', long: 'długoterminowe',
  term: 'terminowe', receivables: 'należności', borrowings: 'kredyty i pożyczki', interest: 'odsetki', expense: 'koszt',
  income: 'przychody', cost: 'koszt', operating: 'operacyjne', financial: 'finansowe', gross: 'brutto',
  amortization: 'amortyzacja', materials: 'materiały i energia', wages: 'wynagrodzenia', taxes: 'podatki i opłaty',
  services: 'usługi obce', inventories: 'zapasy', fixed: 'trwałe', intangible: 'niematerialne', tangible: 'rzeczowe',
  capital: 'kapitał', reserves: 'rezerwy', payables: 'zobowiązania handlowe', tax: 'podatki', salaries: 'wynagrodzenia',
  other: 'pozostałe', ratio: 'wskaźnik', margin: 'marża', turnover: 'obrót', period: 'okres', currency: 'waluta',
};

function polishFinancialLabel(key: string) {
  if (calculationDefinitions[key]) return calculationDefinitions[key].label;
  return key.split('_').map(part => polishFieldWords[part] || part).join(' ');
}

function FinancialCalculations({ rows }: { rows: FinancialRow[] }) {
  const keys = [...new Set(rows.flatMap(row => Object.keys(row.record).filter(key => key.startsWith('calculated_') && !key.endsWith('_formula') && !key.endsWith('_inputs') && !key.endsWith('_difference') && key !== 'calculated_metrics')))].sort();
  if (!keys.length) return null;
  const definitionFor = (key: string) => {
    const base = key.replace(/^calculated_/, '');
    return calculationDefinitions[base] || { label: polishFinancialLabel(base), formula: rows.find(row => row.record[`${key}_formula`])?.record[`${key}_formula`] || 'Wyliczenie pomocnicze na podstawie danych API', kind: /margin|roa|roe|ratio|to_total_assets|debt_to_equity/.test(base) ? 'percent' as MetricKind : /turnover/.test(base) ? 'ratio' as MetricKind : 'amount' as MetricKind };
  };
  return <div className="financial-subsection calculation-panel"><div className="section-title"><div><h3>Obliczenia dodatkowe</h3><p className="muted">Wartości pomocnicze liczone z danych źródłowych. Oryginał z API pozostaje bez zmian.</p></div><span className="calculation-badge">EBITDA i wskaźniki</span></div><div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie"><table className="financial-matrix calculation-table"><thead><tr><th>Wskaźnik</th><th>Jak liczymy</th>{rows.map((row, index) => <th key={`${row.index}-${index}`}>{row.year || '?'}<small>{row.record.currency || '?'}</small></th>)}</tr></thead><tbody>{keys.map(key => { const definition = definitionFor(key); return <tr key={key}><th>{definition.label}</th><td className="calc-definition">{definition.formula}</td>{rows.map(row => { const difference = numeric(row.record[`${key}_difference`]); return <td key={`${row.index}-${key}`}><strong>{formatMetric(row.record[key], definition.kind)}</strong>{difference != null && (Math.abs(difference) < 0.000001 ? <small className="metric-note metric-ok">✓ zgodne z API</small> : <small className="metric-note metric-diff">różnica: {formatMetric(difference, definition.kind)}</small>)}</td>; })}</tr>; })}</tbody></table></div></div>;
}

function AllFinancialFields({ financials }: { financials: FinancialRecord[] }) {
  const hidden = new Set(['source_pointer', 'calculated_metrics', 'esf_statement_lines', 'esf_consistency_warnings']);
  const keys = [...new Set(financials.flatMap(record => Object.keys(record).filter(key => !hidden.has(key) && !key.startsWith('calculated_') && record[key] != null && (typeof record[key] !== 'object' || key.endsWith('_ui')))))].sort();
  return <details className="profile-provenance financial-all-fields"><summary>Wszystkie pozycje finansowe z API ({keys.length})</summary><p className="muted">Pokazujemy także szczegółowe pozycje rachunku wyników i bilansu. Nazwa techniczna pola jest pod polską etykietą.</p><div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie"><table className="financial-matrix"><thead><tr><th>Pole finansowe</th><th>Źródło</th>{financials.map((record, index) => <th key={index}>{periodYear(record) || '?'}<small>{record.currency || '?'}</small></th>)}</tr></thead><tbody>{keys.map(key => <tr key={key}><th>{polishFinancialLabel(key)}</th><td className="mono api-field-name">{key}</td>{financials.map((record, index) => <td key={`${index}-${key}`}>{readableValue(record[key])}</td>)}</tr>)}</tbody></table></div></details>;
}

function FinancialSection({ financials, notes, status }: { financials: FinancialRecord[]; notes: string[]; status: string }) {
  const rows = enrichFinancials(financials);
  const newestFirst = [...rows].reverse();
  const charts = comparableRows(rows);
  const phases = determineCyclePhases(charts);
  const latest = rows.at(-1);
  const completeness = {
    revenue: rows.filter(row => numeric(row.record.revenue_total) != null).length,
    ebit: rows.filter(row => numeric(row.record.ebit) != null).length,
    providerEbitda: rows.filter(row => numeric(row.record.ebitda) != null).length,
    calculatedEbitda: rows.filter(row => numeric(row.record.calculated_ebitda) != null).length,
  };
  const completenessLabel = completeness.revenue === rows.length && completeness.ebit === rows.length ? 'Kompletne podstawowe dane' : completeness.revenue || completeness.ebit ? 'Dane częściowe' : 'Brak podstawowych danych';
  return <section className="card table-card profile-financials"><div className="section-title"><h2>Finanse</h2>{latest && <span className="tag">Ostatni rok: {latest.year || 'brak'}</span>}</div>
    <FinancialStatementOverview rows={rows} />
    <details className="friendly-details"><summary>Zakres danych i uwagi do porównań · {rows.length} okresów</summary>
    <p>Przychody pokazują skalę działalności. Zysk netto mówi, ile zostało po kosztach i podatku. Przejrzyj kilka lat, aby zobaczyć szerszy obraz. Zmiany nie są oceną inwestycyjną.</p>
    <p className="muted">Kwoty pokazujemy w walucie z danego rekordu. Nie sumujemy powtórzonych lat ani nie łączymy różnych zakresów (jednostkowe/skonsolidowane). Wskaźniki obliczone są informacyjne i wymagają sprawdzenia jednostek.</p>
    <div className="financial-completeness" role="status"><div><span className="eyebrow">KOMPLETNOŚĆ DANYCH</span><strong>{completenessLabel}</strong></div><div className="completeness-grid"><span>Przychód <b>{completeness.revenue}/{rows.length}</b></span><span>EBIT <b>{completeness.ebit}/{rows.length}</b></span><span>EBITDA API <b>{completeness.providerEbitda}/{rows.length}</b></span><span>EBITDA wyliczona <b>{completeness.calculatedEbitda}/{rows.length}</b></span></div></div>
    <p className="muted">Do porównań i modeli używaj jednej waluty oraz tego samego zakresu sprawozdania. EBITDA wyliczona jest pomocnicza: <strong>EBIT + amortyzacja</strong> i nie zastępuje wartości raportowanej.</p>
    {status !== 'developer_candidate' && <p className="notice">Profil jest poza domyślną kwalifikacją deweloperów, ale dostępne dane finansowe pokazujemy informacyjnie.</p>}
    {notes.map(note => <p className="notice" key={note}>{note}</p>)}
    </details>
    {latest && <div className="stats company-stats profile-financial-highlights">{financialAmountMetrics.slice(0, 4).concat(providerRatioMetrics.slice(0, 2)).map(definition => <div className="stat" key={definition.key}><span>{definition.label}</span><strong>{formatMetric(metricValue(latest, definition), definition.kind)}</strong><small>{latest.year || 'brak roku'}</small></div>)}</div>}
    {!!rows.length && <>
      <div className="financial-charts"><FinancialChart rows={charts} phases={phases} title="Przychody i wynik netto w czasie" series={[{ key: 'revenue_total', label: 'Przychody', color: '#217769', kind: 'amount' }, { key: 'profit_net', label: 'Zysk netto', color: '#c17a3b', kind: 'amount' }]} /><FinancialChart rows={charts} phases={phases} title="Aktywa i kapitał własny w czasie" series={[{ key: 'total_assets', label: 'Aktywa', color: '#496b9b', kind: 'amount' }, { key: 'equity', label: 'Kapitał własny', color: '#8a5b93', kind: 'amount' }]} /><FinancialChart rows={charts} phases={phases} title="Rentowność i marże" series={[{ key: 'roa', label: 'ROA', color: '#217769', kind: 'percent' }, { key: 'roe', label: 'ROE', color: '#c17a3b', kind: 'percent' }, { key: 'net_margin', label: 'Marża netto', color: '#496b9b', kind: 'percent' }]} /></div>
      <details className="friendly-details"><summary>Wszystkie kwoty rok po roku</summary><p className="muted">Przychody, koszty, majątek i zobowiązania. Przesuń tabelę w bok, aby zobaczyć kolejne lata.</p><FinancialMatrix rows={newestFirst} definitions={financialAmountMetrics} /></details>
      <details className="friendly-details"><summary>Rentowność, płynność i zadłużenie — wskaźniki</summary><p className="muted">Wartości podane przez dostawcę. Objaśnienia skrótów znajdziesz w słowniczku na górze strony.</p><FinancialMatrix rows={newestFirst} definitions={providerRatioMetrics} /></details>
      <TrendOverview rows={rows} status={status} />
      <details className="friendly-details"><summary>Dodatkowe wskaźniki obliczone z danych</summary><p className="muted">Pokazujemy wyłącznie pozycje, których nie ma w tabeli dostawcy, m.in. marżę EBIT, marżę brutto, koszty operacyjne i relację długu do kapitału.</p><FinancialMatrix rows={newestFirst} definitions={derivedMetrics} /></details>
    </>}
    {!rows.length && <p>Brak sprawozdań w tym profilu.</p>}
  </section>;
}

const companyFieldLabels: Record<string, string> = {
  registry_number: 'KRS', company_name: 'Nazwa prawna', nip: 'NIP', regon: 'REGON', legal_form: 'Forma prawna',
  full_address: 'Pełny adres',
  street: 'Ulica', building_no: 'Numer budynku', building_unit: 'Lokal', postal_code: 'Kod pocztowy',
  city: 'Miasto', county: 'Powiat', municipality: 'Gmina', region: 'Województwo', country: 'Kraj',
  state_date: 'Data rejestracji / stan na dzień',
  representation_method: 'Sposób reprezentacji', share_capital_amount: 'Kapitał zakładowy',
  share_capital_currency: 'Waluta kapitału', share_capital_amount_usd: 'Kapitał zakładowy (USD)',
  share_capital_amount_eur: 'Kapitał zakładowy (EUR)', is_komandytowa: 'Spółka komandytowa',
  company_summary: 'Opis firmy',
};

function shortRole(value: any) {
  const raw = String(value || 'Rola nieokreślona').replace(/\s*\([^)]*\)/g, '').trim();
  const known: Record<string, string> = {
    'PREZES ZARZĄDU': 'Prezes zarządu', 'ZASTĘPCA PREZESA ZARZĄDU': 'Zastępca prezesa zarządu',
    'CZŁONEK RADY NADZORCZEJ': 'Członek rady nadzorczej', 'PROKURENT': 'Prokurent',
    'WSPÓLNIK': 'Wspólnik', 'CZŁONEK ZARZĄDU': 'Członek zarządu', 'LIKWIDATOR': 'Likwidator',
  };
  return known[raw] || raw.charAt(0) + raw.slice(1).toLowerCase();
}

function readableValue(value: any) {
  if (value == null || value === '') return '—';
  if (typeof value === 'boolean') return value ? 'Tak' : 'Nie';
  if (typeof value === 'object') return JSON.stringify(value);
  return String(value);
}

function issueLabel(issue: string) {
  const labels: Record<string, string> = {
    invalid_pkd_format: 'Niepełny lub nieprawidłowy format kodu PKD',
    unknown_pkd_code: 'Nieznany kod PKD',
    missing_pkd_description: 'Brak opisu kodu PKD',
    conflicting_pkd_version: 'Niespójna wersja PKD',
  };
  return labels[issue] || issue;
}

function personRelationshipLabels(person: any, relationshipName: (value: any) => string) {
  const labels = new Set<string>();
  (person?.relationships || []).forEach((relationship: any) => {
    const role = String(relationship?.role || '').trim();
    const kind = String(relationship?.kind || '').trim().toLowerCase();
    if (role.toLowerCase().includes('beneficjent')) labels.add('Beneficjent rzeczywisty');
    else if (role) labels.add(shortRole(role));
    else if (kind === 'ownership') labels.add('Właściciel / wspólnik');
    else if (kind) labels.add(relationshipName(kind));
  });
  if (person?.display_role) labels.add(shortRole(person.display_role));
  return [...labels];
}

function relationshipGraphLabel(edge: any) {
  const kind = String(edge?.relationship_kind || '').toLowerCase();
  const role = String(edge?.role || '').toLowerCase();
  if (role.includes('beneficjent')) return 'Beneficjent rzeczywisty';
  if (kind === 'ownership') return 'Właścicielstwo';
  if (kind === 'management') return 'Zarząd';
  if (kind === 'supervisory') return 'Nadzór';
  if (kind === 'representation') return 'Reprezentacja';
  if (kind === 'procuration') return 'Prokura';
  return edge?.role || edge?.relationship_kind || 'Powiązanie';
}

function relationshipColor(edge: any) {
  const kind = String(edge?.relationship_kind || '').toLowerCase();
  if (kind === 'ownership') return '#4f8b62';
  if (kind === 'management') return '#4f719f';
  if (kind === 'supervisory') return '#ba7b3e';
  if (kind === 'representation' || kind === 'procuration') return '#8b6199';
  return '#829189';
}

function RelationshipGraph({ profile, nodes, edges }: { profile: Profile; nodes: any[]; edges: any[] }) {
  const company = nodes.find(node => node.type === 'company' && (node.krs === profile.krs || node.id === profile.krs)) || nodes.find(node => node.type === 'company') || { id: profile.krs, name: profile.name, type: 'company', krs: profile.krs };
  const otherNodes = nodes.filter(node => node.id !== company.id);
  const positions = new Map<string, { x: number; y: number }>([[company.id, { x: 420, y: 220 }]]);
  const radiusX = otherNodes.length > 8 ? 315 : 275;
  const radiusY = otherNodes.length > 8 ? 165 : 145;
  otherNodes.forEach((node, index) => {
    const angle = -Math.PI / 2 + (Math.PI * 2 * index) / Math.max(otherNodes.length, 1);
    positions.set(node.id, { x: 420 + radiusX * Math.cos(angle), y: 220 + radiusY * Math.sin(angle) });
  });
  const nodeById = new Map(nodes.map(node => [node.id, node]));
  const deduped = new Map<string, any>();
  edges.filter(edge => positions.has(edge.source) && positions.has(edge.target)).forEach(edge => {
    const key = `${edge.source}|${edge.target}|${edge.relationship_kind || ''}`;
    const current = deduped.get(key);
    if (current) {
      const label = relationshipGraphLabel(edge);
      current.labels = [...new Set([...current.labels, label])];
    } else deduped.set(key, { ...edge, labels: [relationshipGraphLabel(edge)] });
  });
  const graphEdges = [...deduped.values()];
  const [activeId, setActiveId] = useState(company.id);
  const activeNode = nodeById.get(activeId) || company;
  const connected = graphEdges.filter(edge => edge.source === activeId || edge.target === activeId);
  const label = (node: any) => String(node?.name || node?.krs || 'Nieznany węzeł');
  const short = (value: string, length: number) => value.length > length ? `${value.slice(0, length - 1)}…` : value;
  return <div className="network-graph"><div className="network-toolbar"><div><strong>Mapa powiązań</strong><p className="muted">Kliknij węzeł, aby zobaczyć relacje. Mapę możesz przewijać w poziomie.</p></div><span className="muted">{positions.size} węzłów · {graphEdges.length} relacji</span></div><div className="network-layout"><div className="network-canvas" tabIndex={0} role="region" aria-label="Mapa powiązań — przewijanie w poziomie"><ZoomableSvg viewBox="0 0 840 440" role="img" aria-label={`Mapa powiązań firmy ${profile.name}`}>
    <defs><marker id="network-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse"><path d="M 0 0 L 10 5 L 0 10 z" fill="#829189" /></marker></defs>
    {graphEdges.map((edge, index) => { const from = positions.get(edge.source)!; const to = positions.get(edge.target)!; const midX = (from.x + to.x) / 2; const midY = (from.y + to.y) / 2; const highlighted = edge.source === activeId || edge.target === activeId; return <g key={`${edge.source}-${edge.target}-${index}`} className={highlighted ? 'network-edge highlighted' : 'network-edge'}><line x1={from.x} y1={from.y} x2={to.x} y2={to.y} stroke={relationshipColor(edge)} markerEnd="url(#network-arrow)" /><text x={midX} y={midY - 5} textAnchor="middle" fill={relationshipColor(edge)}>{short(edge.labels.join(' · '), 27)}</text></g>; })}
    {[company, ...otherNodes].map(node => { const point = positions.get(node.id)!; const root = node.id === company.id; const isActive = node.id === activeId; return <g key={node.id} className={`network-node ${root ? 'root' : ''} ${isActive ? 'active' : ''}`} role="button" tabIndex={0} aria-label={`Węzeł ${label(node)}`} onClick={() => setActiveId(node.id)} onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') setActiveId(node.id); }}><rect x={point.x - (root ? 88 : 67)} y={point.y - (root ? 30 : 25)} width={root ? 176 : 134} height={root ? 60 : 50} rx="11" /><text x={point.x} y={point.y - 4} textAnchor="middle">{short(label(node), root ? 25 : 19)}</text><text x={point.x} y={point.y + 14} textAnchor="middle" className="network-node-type">{root ? 'Firma · KRS' : node.type === 'person' ? 'Osoba' : 'Firma'}</text></g>; })}
  </ZoomableSvg></div><aside className="network-details"><span className="eyebrow">WYBRANY WĘZEŁ</span><h4>{label(activeNode)}</h4><p className="muted">{activeNode.type === 'person' ? 'Osoba' : 'Firma'}{activeNode.krs ? ` · KRS ${activeNode.krs}` : ''}</p><h5>Relacje ({connected.length})</h5>{connected.length ? <ul>{connected.map((edge, index) => <li key={`${edge.source}-${edge.target}-${index}`}><span className="network-dot" style={{ background: relationshipColor(edge) }} />{edge.source === activeId ? `do: ${label(nodeById.get(edge.target))}` : `od: ${label(nodeById.get(edge.source))}`}<small>{edge.labels.join(' · ')}</small></li>)}</ul> : <p className="muted">Brak bezpośrednich relacji.</p>}<div className="network-legend"><span><i style={{ background: '#4f8b62' }} />właścicielstwo</span><span><i style={{ background: '#4f719f' }} />zarząd</span><span><i style={{ background: '#ba7b3e' }} />nadzór</span><span><i style={{ background: '#8b6199' }} />reprezentacja / prokura</span></div></aside></div></div>;
}

function ProfileInformation({ profile }: { profile: Profile }) {
  const company = profile.company_info || {};
  const people = profile.people || profile.connections?.people || [];
  const ownership = profile.ownership || [];
  const graphNodes = profile.graph?.nodes || [];
  const graphEdges = profile.graph?.edges || [];
  const related = profile.related_companies || [];
  const similar = profile.similar_companies || [];
  const subsidiaries = profile.subsidiary_companies || [];
  const hasRegister = Object.keys(company).length > 0;
  const hasConnections = people.length || ownership.length || related.length || graphNodes.length || graphEdges.length || (profile.roles || []).length;
  const linkedName = (item: any) => item?.company_name_display || item?.company_name || item?.name || item?.display_name || item?.registry_number || item?.krs || '—';
  const partyName = (role: any) => linkedName(role?.party || role?.person || role?.owner || role?.company || role);
  const roleName = (role: any) => role?.role_name || role?.role || role?.display_role || role?.kind || 'Rola nieokreślona';
  const relationshipName = (value: any) => ({ ownership: 'Właścicielstwo', supervisory: 'Nadzór', management: 'Zarząd', representation: 'Reprezentacja', procuration: 'Prokura' }[String(value)] || (String(value).toLowerCase().includes('beneficjent') ? 'Beneficjent rzeczywisty (CRBR)' : value || 'Powiązanie'));
  const nodeNames = new Map(graphNodes.map((node: any) => [node.id, node.name || node.krs || 'Nieznany węzeł']));
  const compactRoles = [...new Map((profile.roles || []).map((role: any) => {
    const person = partyName(role) || 'Nieznana osoba';
    const title = shortRole(roleName(role));
    const kind = role.relationship_kind ? relationshipName(role.relationship_kind) : 'Rejestr przedsiębiorców';
    return [`${person}|${title}|${kind}`, { person, title, kind }];
  })).values()];
  return <section className="card profile-information"><div className="section-title"><div><p className="eyebrow">DANE PODMIOTU I POWIĄZANIA</p><h2>Informacje rejestrowe</h2></div><span className="muted">KRS {profile.krs}</span></div>
    {hasRegister && <div className="info-grid">{Object.entries(companyFieldLabels).map(([key, label]) => company[key] != null && <div className="info-item" key={key}><span>{label}</span><strong>{readableValue(company[key])}</strong></div>)}</div>}
    {profile.primary_pkd_description && <div className="info-callout"><strong>Opis głównego PKD</strong><p>{readableValue(profile.primary_pkd_description)}</p></div>}
    {hasConnections ? <>
      {!!people.length && <div className="financial-subsection people-section"><div className="section-title"><div><h3>Osoby i reprezentacja</h3><p className="muted">Nazwiska i role odczytane z rejestru.</p></div><span className="muted">{people.length} osób</span></div><div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie"><table className="people-table"><thead><tr><th>Osoba</th><th>Rok urodzenia</th><th>Rola / powiązanie</th><th>Powiązane spółki</th></tr></thead><tbody>{people.map((person: any, index: number) => { const roleLabels = personRelationshipLabels(person, relationshipName); const otherCompanies = person.other_companies || []; const otherCount = Number(person.other_companies_count || otherCompanies.length || 0); return <tr key={person.person_id || index}><td><strong>{person.display_name || person.name || '—'}</strong></td><td>{person.birth_year || '—'}</td><td><div className="relationship-pills">{roleLabels.length ? roleLabels.map((label, roleIndex) => <span className="role-pill" key={`${label}-${roleIndex}`}>{label}</span>) : <span className="muted">Brak określonej roli</span>}</div></td><td>{otherCompanies.length ? <div className="person-companies">{otherCompanies.map((companyItem: any, companyIndex: number) => <span className="tag person-company" key={`${linkedName(companyItem)}-${companyIndex}`}>{linkedName(companyItem)}{companyItem.role ? ` · ${shortRole(companyItem.role)}` : ''}{companyItem.holding_percent != null ? ` · ${companyItem.holding_percent}%` : ''}</span>)}</div> : person.has_other_connections && otherCount ? `${otherCount} ${otherCount === 1 ? 'spółka' : 'spółki'}` : 'Brak'}</td></tr>; })}</tbody></table></div></div>}
      {!!ownership.length && <div className="financial-subsection"><div className="section-title"><div><h3>Właściciele i beneficjenci</h3><p className="muted">Najważniejsze informacje o właścicielach. Szczegóły źródłowe są dostępne w pełnym widoku danych.</p></div><span className="muted">{ownership.length} wpisów</span></div><div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie"><table className="ownership-table"><thead><tr><th>Osoba</th><th>Udział / status</th></tr></thead><tbody>{ownership.map((entry, index) => { const owner = entry.owner || {}; return <tr key={index}><td><strong>{owner.display_name || owner.name || '—'}</strong></td><td>{entry.holding_text || (entry.has_all_shares == null ? 'Właściciel / beneficjent' : entry.has_all_shares ? 'Wszystkie udziały' : 'Część udziałów')}</td></tr>; })}</tbody></table></div></div>}
      {!!compactRoles.length && <details className="register-roles-details"><summary>Role w rejestrze ({compactRoles.length})</summary><p className="muted">Skrócona lista formalnych ról; powtórzone wpisy zostały połączone.</p><div className="compact-role-list">{compactRoles.map((role, index) => <span className="tag" key={`${role.person}-${role.title}-${index}`}><strong>{role.person}</strong> · {role.title}{role.kind !== 'Rejestr przedsiębiorców' ? ` · ${role.kind}` : ''}</span>)}</div></details>}
      {!!graphNodes.length && <div className="financial-subsection"><RelationshipGraph profile={profile} nodes={graphNodes} edges={graphEdges} /><details className="graph-raw-details"><summary>Lista węzłów i relacji</summary><div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie"><table className="graph-table"><thead><tr><th>Węzeł</th><th>Typ</th><th>KRS / identyfikator</th></tr></thead><tbody>{graphNodes.map((node: any, index) => <tr key={node.id || index}><td><strong>{node.name || '—'}</strong></td><td><span className="type-pill">{node.type === 'company' ? 'Firma' : node.type === 'person' ? 'Osoba' : node.type || 'Inny'}</span></td><td className="mono">{node.krs || (node.type === 'company' ? node.id : '—')}</td></tr>)}</tbody></table></div>{!!graphEdges.length && <div className="relationship-list"><h4>Rodzaje relacji</h4><div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie"><table><thead><tr><th>Od</th><th>Relacja</th><th>Do</th></tr></thead><tbody>{graphEdges.map((edge: any, index) => <tr key={index}><td>{nodeNames.get(edge.source) || edge.source_name || 'Firma'}</td><td><span className="role-pill" title={edge.role || edge.relationship_kind}>{shortRole(relationshipName(edge.role || edge.relationship_kind))}</span></td><td>{nodeNames.get(edge.target) || edge.target_name || 'Osoba / podmiot'}</td></tr>)}</tbody></table></div></div>}</details></div>}
      {!!related.length && <div className="financial-subsection"><h3>Powiązane spółki</h3><div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie"><table><thead><tr><th>Spółka</th><th>KRS</th><th>Forma prawna</th><th>Rola / udział</th></tr></thead><tbody>{related.map((item: any, index) => <tr key={item.entity_id || index}><td>{linkedName(item)}</td><td className="mono">{item.registry_number || item.krs || '—'}</td><td>{item.legal_form || '—'}</td><td>{[item.role, item.holding_text, item.holding_percent != null ? `${item.holding_percent}%` : null].filter(Boolean).join(' · ') || '—'}</td></tr>)}</tbody></table></div></div>}
    </> : <p className="muted">Brak osob, właścicieli lub powiązań w dostarczonym profilu.</p>}
    {!!similar.length && <div className="financial-subsection"><div className="section-title"><h3>Podobne firmy</h3><span className="muted">{similar.length}</span></div><div className="compact-links">{similar.map((item: any, index) => <span className="tag" key={item.entity_id || item.registry_number || index}>{linkedName(item)}{item.registry_number ? ` · ${item.registry_number}` : ''}</span>)}</div></div>}
    {!!subsidiaries.length && <div className="financial-subsection"><h3>Spółki zależne</h3><div className="compact-links">{subsidiaries.map((item: any, index) => <span className="tag" key={item.entity_id || item.registry_number || index}>{linkedName(item)}{item.registry_number ? ` · ${item.registry_number}` : ''}</span>)}</div></div>}
    {!!profile.ownership_family_insight && <div className="info-callout"><strong>Informacja o rodzinie właścicielskiej</strong><p>{readableValue(profile.ownership_family_insight)}</p></div>}
    <details className="profile-provenance"><summary>Pełne dane rejestrowe i powiązania z API</summary><p className="muted">Poniżej są także pola, dla których nie ma jeszcze osobnej kolumny w widoku.</p><pre>{JSON.stringify({company: profile.company_info, details: profile.profile_details, people: profile.people, roles: profile.roles, ownership: profile.ownership, related_companies: profile.related_companies, graph: profile.graph, similar_companies: profile.similar_companies, subsidiary_companies: profile.subsidiary_companies, change_history: profile.change_history, statistics: profile.statistics, insights_by_year: profile.insights_by_year, seo_metric_summaries_by_year: profile.seo_metric_summaries_by_year, faq: profile.faq, pkd_rankings: profile.pkd_rankings, connections: profile.connections, other_provider_fields: profile.raw_profile}, null, 2)}</pre></details>
  </section>;
}

export function CurrentProfile({ collection, krs, onBack }: { collection: string; krs: string; onBack: () => void }) {
  const state = useApi<Profile>(`/api/profiles/${krs}?collection=${collection}`);
  const p = state.data;
  const website = websiteUrl(p?.website || null);
  const financials = (p?.financials || []) as FinancialRecord[];
  const [localVerification, setLocalVerification] = useState<LocalVerification | null>(() => loadVerifications(collection)[krs] || null);
  const [verificationSaving, setVerificationSaving] = useState(false);
  const [verificationError, setVerificationError] = useState('');

  useEffect(() => {
    if (p?.verification?.status) {
      if (p.verification.status === 'confirmed' || p.verification.status === 'rejected') {
        setLocalVerification(p.verification.status);
      }
    }
  }, [p]);

  const updateLocalVerification = async (value: LocalVerification | null) => {
    const previous = localVerification;
    setLocalVerification(value);
    setVerificationSaving(true);
    setVerificationError('');
    try {
      await saveVerification(collection, krs, value);
    } catch (error) {
      setLocalVerification(previous);
      setVerificationError(error instanceof Error ? error.message : 'Nie udało się zapisać weryfikacji. Spróbuj ponownie.');
    } finally {
      setVerificationSaving(false);
    }
  };

  return <><button className="text-button" onClick={onBack}>← Wróć do profili</button><Feedback {...state} />{p && <>
    <div className="company-title">
      <div className="company-title-row">
        <h1>{p.name}</h1>
        {localVerification === 'rejected' ? (
          <span className="tag tag-rejected badge-large">✕ Nie deweloper (wykluczona)</span>
        ) : localVerification === 'confirmed' ? (
          <span className="tag tag-confirmed badge-large">✓ Potwierdzony deweloper</span>
        ) : (
          <span className="tag badge-large">Wstępny przesiew: {p.classification ? businessLabels[p.classification.business_type] : labels[p.screening.status]}</span>
        )}
      </div>
      <p>KRS {p.krs}</p>
    </div>
    <p>{[p.city,p.region].filter(Boolean).join(' · ')} {website && <> · <a href={website} target="_blank" rel="noreferrer">Strona firmy ↗</a></>} · Status: {p.provider_status === 'active' ? 'aktywna' : p.provider_status || 'nieznany'}{p.is_currently_suspended ? ' · zawieszona' : ''}</p>

    <div className="card qualification-override-card">
      <div className="qualification-override-header">
        <div>
          <span className="eyebrow">STATUS KWALIFIKACJI FIRMY</span>
          <h3>Zmień kwalifikację</h3>
          <p className="muted">
            Możesz ręcznie zmienić status kwalifikacji firmy (np. potwierdzić dewelopera lub wykluczyć). Status jest zapisywany w bazie danych SQLite i synchronizowany z katalogiem.
          </p>
        </div>
        <div className="current-status-badge-wrap">
          <span className="muted">Aktualny status:</span>
          {localVerification === 'rejected' ? (
            <span className="tag tag-rejected badge-large">✕ Nie deweloper</span>
          ) : localVerification === 'confirmed' ? (
            <span className="tag tag-confirmed badge-large">✓ Potwierdzony deweloper</span>
          ) : (
            <span className="tag badge-large">{p.classification ? businessLabels[p.classification.business_type] : labels[p.screening.status]} (Przesiew)</span>
          )}
        </div>
      </div>
      <div className="qualification-override-buttons">
        <button
          type="button"
          className={`qual-btn qual-btn-confirmed ${localVerification === 'confirmed' ? 'active' : ''}`}
          onClick={() => void updateLocalVerification('confirmed')}
          disabled={verificationSaving}
          title="Oznacz firmę jako potwierdzonego dewelopera"
        >
          <span className="qual-icon">✓</span>
          <span className="qual-text">
            <strong>Oznacz jako Deweloper</strong>
            <small>Firma realizuje inwestycje deweloperskie</small>
          </span>
        </button>
        <button
          type="button"
          className={`qual-btn qual-btn-rejected ${localVerification === 'rejected' ? 'active' : ''}`}
          onClick={() => void updateLocalVerification('rejected')}
          disabled={verificationSaving}
          title="Oznacz firmę jako niebędącą deweloperem"
        >
          <span className="qual-icon">✕</span>
          <span className="qual-text">
            <strong>Oznacz jako Nie deweloper</strong>
            <small>Wyklucz podmiot z grona deweloperów</small>
          </span>
        </button>
        {localVerification && (
          <button
            type="button"
            className="qual-btn qual-btn-reset"
            onClick={() => void updateLocalVerification(null)}
            disabled={verificationSaving}
            title="Przywróć status pierwotny z automatycznego przesiewu"
          >
            <span className="qual-icon">↺</span>
            <span className="qual-text">
              <strong>Przywróć domyślny</strong>
              <small>Cofa ręczną zmianę kwalifikacji</small>
            </span>
          </button>
        )}
      </div>
      {verificationSaving && <p className="muted" role="status">Zapisuję decyzję i aktualizuję filtry oraz mapę…</p>}
      {verificationError && <p className="notice error" role="alert">{verificationError}</p>}
      {localVerification && (
        <div className="qual-status-sync-note">
          ✓ Wybór zapisany w bazie danych. Status w katalogu został automatycznie zaktualizowany.
        </div>
      )}
    </div>

    <GeminiVerification
      krs={p.krs}
      collection={collection}
      companyName={p.name}
      localVerification={localVerification}
      onApplyVerification={value => { void updateLocalVerification(value); }}
      onGeminiVerification={value => { storeVerification(collection, krs, value); setLocalVerification(value); }}
      initialDbVerification={p.verification}
    />
    {financials.length ? <FinancialSection financials={financials} notes={p.financial_notes} status={p.screening.status} /> : <p className="notice">Brak sprawozdań finansowych w tym profilu.</p>}
    <details className="card friendly-details"><summary>Czym zajmuje się firma? Opis i rodzaje działalności</summary>
      <div className="section-title">
        <div>
          <h2>
            {localVerification === 'confirmed'
              ? '✓ Potwierdzony deweloper'
              : localVerification === 'rejected'
              ? '✕ Wykluczona z deweloperów'
              : (p.classification ? businessLabels[p.classification.business_type] : labels[p.screening.status])}
          </h2>
          <p className="muted">
            {localVerification === 'confirmed'
              ? 'Potwierdzona działalność deweloperska'
              : localVerification === 'rejected'
              ? 'Negatywna weryfikacja — podmiot wykluczony z deweloperów'
              : 'Ocena wstępna na podstawie opisu'} · Twoja weryfikacja: {localVerification === 'confirmed' ? 'potwierdzona' : localVerification === 'rejected' ? 'odrzucona' : 'jeszcze nie sprawdzono'}
          </p>
        </div>
        <span className={`tag ${localVerification === 'rejected' ? 'tag-rejected' : localVerification === 'confirmed' ? 'tag-confirmed' : ''}`}>
          {localVerification === 'rejected' ? 'Wykluczona' : localVerification === 'confirmed' ? 'Potwierdzona' : segments[p.screening.segment]}
        </span>
      </div>
      {localVerification === 'rejected' ? (
        <div className="notice notice-rejected">
          <strong>✕ Wykluczona w weryfikacji (Nie deweloper)</strong>
          <p>Weryfikacja wykazała, że firma nie prowadzi działalności deweloperskiej. Poprzednia automatyczna kwalifikacja heurystyczna: {p.classification ? businessLabels[p.classification.business_type] : labels[p.screening.status]} ({p.classification?.reason || p.screening.reason}).</p>
        </div>
      ) : localVerification === 'confirmed' ? (
        <div className="notice notice-confirmed">
          <strong>✓ Potwierdzony deweloper</strong>
          <p>Działalność deweloperska firmy została zweryfikowana i zatwierdzona.</p>
        </div>
      ) : p.classification ? (
        <div className="notice"><strong>Wstępna kwalifikacja: {businessLabels[p.classification.business_type]}</strong><p>{p.classification.reason}</p><p>Aktywność: {p.classification.is_active===null?'nieznana':p.classification.is_active?'aktywna':'nieaktywna / zawieszona'}. Ocena automatyczna, wymagająca weryfikacji.</p></div>
      ) : null}
      {p.address_correction && <p className="notice">Uzupełniony adres: {p.company_info?.full_address}. {p.address_correction.note} Źródło: {p.address_correction.source}</p>}
      <p>{p.screening.reason}</p>{p.screening.flags.map(flag => <p className="notice" key={flag}>{flag}</p>)}
      <div className="verification-actions"><strong>Weryfikacja na tym komputerze</strong><span className="muted">Zapisujemy tylko Twoją decyzję lokalnie; dane źródłowe pozostają niezmienione.</span><div><button className={localVerification === 'confirmed' ? 'selected-action' : ''} onClick={() => updateLocalVerification('confirmed')}>✓ Potwierdź dewelopera</button><button className={localVerification === 'rejected' ? 'selected-action danger-action' : ''} onClick={() => updateLocalVerification('rejected')}>× Odrzuć</button>{localVerification && <button onClick={() => updateLocalVerification(null)}>Wyczyść decyzję</button>}</div></div>
      <h3>Oryginalny opis firmy</h3><p className="profile-summary">{p.summary || 'Ten profil nie zawiera opisu firmy. Nie kwalifikujemy go automatycznie po samym PKD.'}</p>
      {p.screening.evidence.length > 0 && <details><summary>Fragmenty wykorzystane w kwalifikacji</summary>{p.screening.evidence.map((s,i) => <blockquote key={i}>{s}</blockquote>)}</details>}
      <p className="muted">Opis dostawcy Compabase, potencjalnie wygenerowany przez AI. Może dotyczyć marki, grupy lub obecnej zawartości strony. Nie potwierdza działalności firmy w historycznych latach.</p>
      <div className="financial-subsection"><div className="section-title"><div><h3>PKD i pozostałe rodzaje działalności</h3><p className="muted">Uwagi opisują jakość zapisu kodu, a nie automatycznie działalność firmy.</p></div><span className="muted">{p.activities.length} kodów</span></div><div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie"><table><thead><tr><th>Kod</th><th>Opis działalności</th><th>Wersja</th><th>Rola</th><th>Pasuje do celu</th><th>Uwagi</th></tr></thead><tbody>{p.activities.map((activity, index) => <tr key={`${activity.code}-${index}`}><td className="mono">{activity.code}</td><td>{activity.description || 'Opis niedostępny'}</td><td>{activity.version || '—'}</td><td>{activity.is_primary ? 'Główne' : 'Pozostałe'}</td><td>{activity.target_match == null ? '—' : activity.target_match ? 'Tak' : 'Nie'}</td><td>{activity.issues?.length ? activity.issues.map(issueLabel).join('; ') : '—'}</td></tr>)}</tbody></table></div></div>
      <details className="profile-provenance"><summary>Pochodzenie i kwalifikacja</summary><p>Pole opisu: {p.summary_pointer || 'brak'}<br />Data profilu u dostawcy: {p.provider_updated_at || 'nieznana'}<br />Źródło: {p.source || 'Compabase API'}<br />Metoda przesiewu: {p.screening.method || 'nieznana'}<br />Potwierdzenie ręczne: {p.screening.verified == null ? 'brak' : p.screening.verified ? 'tak' : 'nie'}<br />Sygnał z nazwy: {p.screening.name_signal ? 'tak' : 'nie'}{p.screening.name_signal_reason ? ` · ${p.screening.name_signal_reason}` : ''}<br />SHA-256: {p.source_sha256}</p></details>
    </details>
    <details className="card friendly-details"><summary>Właściciele, powiązania i dane rejestrowe</summary><ProfileInformation profile={p} /></details>
  </>}</>;
}
