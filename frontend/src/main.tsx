import { SegmentedResearch } from './SegmentedResearch';
import { ZoomableSvg } from './ZoomableSvg';
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  useApi,
  type Dataset,
  type Summary,
  type Firm,
  type Company,
  type Year,
  type Research,
  type Study,
} from "./api";
import "./style.css";
import "./clarity.css";
import { Lineage, type Trace } from "./Lineage";
import { Diagnostics } from "./Diagnostics";
import { Sources } from "./Sources";
import { LeverageResearch } from "./LeverageResearch";
import { DeveloperQuestions } from "./DeveloperQuestions";
import { PlainGuide } from "./PlainGuide";
import { ProfileOverview, ProfileCatalog, CurrentProfile, type ProfileCollection } from "./Profiles";
import { CreditResearch } from "./CreditResearch";
import { FinancialMap } from "./FinancialMap";
import "./design.css";

const number = new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 2 });
const compact = new Intl.NumberFormat("pl-PL", {
  notation: "compact",
  maximumFractionDigits: 2,
});
const fmt = (v: number | null | undefined) =>
  v == null ? "Brak danych" : number.format(v);
const scientific = (v: number | null | undefined) =>
  v == null
    ? "—"
    : v !== 0 && Math.abs(v) < 0.001
      ? v.toExponential(3)
      : new Intl.NumberFormat("pl-PL", { maximumSignificantDigits: 5 }).format(
          v,
        );
const metrics: Record<string, string> = {
  reported_revenue_total: "Przychody",
  reported_profit_net: "Zysk netto",
  reported_total_assets: "Aktywa",
  reported_equity: "Kapitał własny",
  reported_liabilities_and_provisions: "Zobowiązania i rezerwy",
  reported_cash_and_equivalents: "Gotówka",
  reported_short_term_receivables: "Należności",
  roa: "ROA",
  roe: "ROE",
  net_margin: "Marża netto",
  liabilities_to_assets: "Zobowiązania / aktywa",
  current_ratio: "Płynność bieżąca",
  revenue_growth: "Wzrost przychodów",
  ebitda_margin: "Marża EBITDA",
};
const percent = new Set([
  "roa",
  "roe",
  "net_margin",
  "liabilities_to_assets",
  "revenue_growth",
  "ebitda_margin",
]);
const metricFmt = (v: number | null | undefined, key: string) =>
  v == null ? "Brak danych" : percent.has(key) ? fmt(v * 100) + "%" : fmt(v);
function State({ loading, error }: { loading: boolean; error?: string }) {
  return loading ? (
    <div className="state" role="status">
      Pobieranie danych…
    </div>
  ) : error ? (
    <div className="notice error" role="alert">
      {error}
    </div>
  ) : null;
}
function Tag({ children }: { children: React.ReactNode }) {
  return <span className="tag">{children}</span>;
}
function Notice() {
  return (
    <div className="notice">
      <strong>Dane eksploracyjne.</strong> Mapowanie i skala dostawcy wymagają
      walidacji. Wyniki modeli opisują zależności warunkowe; nie stanowią dowodu
      przyczynowości ani rekomendacji.
    </div>
  );
}

function Overview({
  dataset,
  onCompanies,
}: {
  dataset: string;
  onCompanies: () => void;
}) {
  const state = useApi<Summary>(`/api/datasets/${dataset}/summary`);
  const s = state.data;
  return (
    <>
      <div className="hero">
        <div>
          <p className="eyebrow">COMPANY INTELLIGENCE + RESEARCH LAB</p>
          <h1>
            Od danych firmy
            <br />
            do pytań badawczych.
          </h1>
          <p>
            Przeglądaj historie finansowe i sprawdzaj, jakie cechy firm
            <br className="desktop" /> wiążą się z ich późniejszymi wynikami.
          </p>
          <button className="primary" onClick={onCompanies}>
            Przeglądaj firmy <span>↗</span>
          </button>
        </div>
        <div className="hero-mark" aria-hidden="true">
          <span>firma</span>
          <b>×</b>
          <span>rok</span>
          <small>Panel niezbilansowany</small>
        </div>
      </div>
      <State {...state} />
      {s && (
        <>
          <div className="stats">
            {[
              ["Firmy w panelu", fmt(s.companies)],
              ["Obserwacje firma–rok", fmt(s.observations)],
              ["Zakres lat", `${s.first_year}–${s.last_year}`],
              ["Nierozstrzygnięte lata", fmt(s.unresolved_observations)],
            ].map(([label, value]) => (
              <div className="stat" key={label}>
                <span>{label}</span>
                <strong>{value}</strong>
              </div>
            ))}
          </div>
          <div className="two-cols">
            <section className="card">
              <div className="section-title">
                <div>
                  <p className="eyebrow">POKRYCIE DANYCH</p>
                  <h2>Ile firm obserwujemy w kolejnych latach?</h2>
                </div>
                <Tag>Wszystkie obserwacje</Tag>
              </div>
              <div className="bars">
                {s.years.map((y) => (
                  <div className="bar-col" key={y.year}>
                    <span className="bar-count">{y.observations}</span>
                    <div
                      className="bar"
                      style={{
                        height: Math.max(
                          2,
                          (170 * y.observations) /
                            Math.max(...s.years.map((x) => x.observations)),
                        ),
                      }}
                      title={`${y.year}: ${y.observations} obserwacji`}
                    />
                    <span>{y.year}</span>
                  </div>
                ))}
              </div>
              <p className="muted">
                Krótkie historie i luki pozostają w panelu. Zakres lat nie
                oznacza pełnego pokrycia populacji.
              </p>
            </section>
            <section className="card">
              <p className="eyebrow">DŁUGOŚĆ HISTORII</p>
              <h2>Próby badawcze</h2>
              {Object.entries(s.cohorts).map(([key, value]) => (
                <div className="cohort" key={key}>
                  <span>
                    {key === "panel_long"
                      ? "Minimum 7 lat"
                      : key === "panel_5plus"
                        ? "Minimum 5 lat"
                        : "Minimum 3 lata"}
                  </span>
                  <strong>{fmt(value)} firm</strong>
                </div>
              ))}
              <p className="muted">
                Klasy zagnieżdżone, według dostępnych lat. Konkretny model ma
                własną próbę po sprawdzeniu kompletności zmiennych.
              </p>
            </section>
          </div>
        </>
      )}
      <Sources />
      <Notice />
    </>
  );
}

function Firms({
  dataset,
  onSelect,
}: {
  dataset: string;
  onSelect: (k: string) => void;
}) {
  const [text, setText] = useState(""),
    [q, setQ] = useState(""),
    [cohort, setCohort] = useState("full"),
    [offset, setOffset] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => {
      setQ(text);
      setOffset(0);
    }, 300);
    return () => clearTimeout(t);
  }, [text]);
  const state = useApi<{ items: Firm[]; total: number }>(
    `/api/companies?dataset=${dataset}&q=${encodeURIComponent(q)}&cohort=${cohort}&offset=${offset}&limit=25`,
  );
  return (
    <>
      <p className="eyebrow">KATALOG FIRM</p>
      <h1>Znajdź firmę. Poznaj jej historię.</h1>
      <p className="muted">
        Wyszukiwanie po nazwie lub KRS, z filtrem długości historii.
      </p>
      <div className="toolbar">
        <input
          aria-label="Nazwa firmy lub KRS"
          placeholder="Szukaj po nazwie lub KRS…"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
        <select
          aria-label="Długość historii"
          value={cohort}
          onChange={(e) => {
            setCohort(e.target.value);
            setOffset(0);
          }}
        >
          <option value="full">Wszystkie historie</option>
          <option value="3plus">Minimum 3 lata</option>
          <option value="5plus">Minimum 5 lat</option>
          <option value="long">Minimum 7 lat</option>
        </select>
      </div>
      <State {...state} />
      {state.data && (
        <section className="card table-card">
          <div className="section-title">
            <h2>Firmy w panelu</h2>
            <span className="muted">{fmt(state.data.total)} wyników</span>
          </div>
          <div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie">
            <table>
              <thead>
                <tr>
                  <th>Firma</th>
                  <th>KRS</th>
                  <th>Zakres danych</th>
                  <th>Liczba lat</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {state.data.items.map((f) => (
                  <tr key={f.krs}>
                    <td>
                      <button
                        className="text-button firm-name"
                        onClick={() => onSelect(f.krs)}
                      >
                        {f.name || "Nazwa niedostępna"}
                      </button>
                      <small>
                        {f.legal_form || "Forma prawna: brak danych"}
                      </small>
                    </td>
                    <td className="mono">{f.krs}</td>
                    <td>
                      {f.first_year}–{f.last_year}
                    </td>
                    <td>{f.years}</td>
                    <td>
                      <button
                        aria-label={`Otwórz firmę ${f.krs}`}
                        onClick={() => onSelect(f.krs)}
                      >
                        ↗
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {state.data.items.length === 0 && (
            <p className="state">Brak firm spełniających te warunki.</p>
          )}
          <div className="pagination">
            <span>
              {state.data.total
                ? `${offset + 1}–${Math.min(offset + 25, state.data.total)}`
                : "0"}{" "}
              z {fmt(state.data.total)}
            </span>
            <div>
              <button
                disabled={offset === 0}
                onClick={() => setOffset(prev => Math.max(0, prev - 25))}
              >
                ← Poprzednia
              </button>
              <button
                disabled={offset + 25 >= state.data.total}
                onClick={() => setOffset(prev => prev + 25)}
              >
                Następna →
              </button>
            </div>
          </div>
        </section>
      )}
    </>
  );
}

function Chart({ rows, metric }: { rows: Year[]; metric: string }) {
  const vals = rows
    .map((r) => r.features[metric])
    .filter((v): v is number => v != null && Number.isFinite(v));
  if (!vals.length)
    return (
      <p className="state">Brak wystarczających danych dla tego wskaźnika.</p>
    );
  const min = Math.min(...vals),
    max = Math.max(...vals),
    pad = (max - min || Math.abs(max) || 1) * 0.12,
    lo = min - pad,
    hi = max + pad;
  const first = Math.min(...rows.map((r) => r.year)),
    last = Math.max(...rows.map((r) => r.year));
  const x = (y: number) => 85 + ((y - first) / Math.max(1, last - first)) * 690;
  const y = (v: number) => 220 - ((v - lo) / (hi - lo)) * 180;
  return (
    <ZoomableSvg
      className="chart"
      viewBox="0 0 810 270"
      role="img"
      aria-label={`Historia: ${metrics[metric]}`}
    >
      {[0, 0.25, 0.5, 0.75, 1].map((t) => (
        <g key={t}>
          <line
            x1="85"
            x2="775"
            y1={220 - 180 * t}
            y2={220 - 180 * t}
            stroke="#e4e9e5"
          />
          <text x="73" y={224 - 180 * t} textAnchor="end">
            {compact.format(
              (lo + (hi - lo) * t) * (percent.has(metric) ? 100 : 1),
            )}
            {percent.has(metric) ? "%" : ""}
          </text>
        </g>
      ))}
      {rows.map((r, i) => {
        const v = r.features[metric],
          prev = rows[i - 1],
          pv = prev?.features[metric];
        return (
          <g key={r.year}>
            {v != null && Number.isFinite(v) && (
              <>
                {prev &&
                  prev.year === r.year - 1 &&
                  pv != null &&
                  Number.isFinite(pv) && (
                    <line
                      x1={x(prev.year)}
                      y1={y(pv)}
                      x2={x(r.year)}
                      y2={y(v)}
                      stroke="#217769"
                      strokeWidth="2.5"
                    />
                  )}
                <circle cx={x(r.year)} cy={y(v)} r="4" fill="#217769">
                  <title>
                    {r.year}: {metricFmt(v, metric)}
                  </title>
                </circle>
              </>
            )}
            <text x={x(r.year)} y="247" textAnchor="middle">
              {r.year}
            </text>
          </g>
        );
      })}
    </ZoomableSvg>
  );
}

function CompanyPage({
  dataset,
  krs,
  onBack,
}: {
  dataset: string;
  krs: string;
  onBack: () => void;
}) {
  const state = useApi<Company>(`/api/companies/${krs}?dataset=${dataset}`),
    c = state.data;
  const [metric, setMetric] = useState("reported_revenue_total"),
    [year, setYear] = useState<number>(),
    [showSource, setSource] = useState(false);
  const effectiveYear = year ?? c?.years.at(-1)?.year;
  const source = useApi<Trace>(
    showSource && effectiveYear
      ? `/api/companies/${krs}/lineage?dataset=${dataset}&year=${effectiveYear}&feature=${metric}`
      : null,
  );
  const latest = c?.years.at(-1),
    identity = c?.identity_snapshots.find((x) => x.name);
  return (
    <>
      <button className="text-button" onClick={onBack}>
        ← Wróć do firm
      </button>
      <State {...state} />
      {c && (
        <>
          <div className="company-heading">
            <div>
              <p className="eyebrow">PROFIL FIRMY · KRS {krs}</p>
              <h1>{identity?.name || "Nazwa niedostępna"}</h1>
              <p className="muted">
                {identity?.legal_form || "Forma prawna: brak danych"} · NIP,
                REGON, lokalizacja: brak potwierdzonych danych
              </p>
            </div>
            <Tag>Historia: {c.years.length} lat</Tag>
          </div>
          <Notice />
          <div className="section-title">
            <h2>Ostatni rok w panelu: {latest?.year ?? "brak"}</h2>
            <span className="muted">
              Nie zastępujemy braków starszym rokiem
            </span>
          </div>
          <div className="stats company-stats">
            {[
              "reported_revenue_total",
              "reported_profit_net",
              "roa",
              "net_margin",
              "liabilities_to_assets",
              "current_ratio",
            ].map((key) => (
              <div className="stat" key={key}>
                <span>{metrics[key]}</span>
                <strong>{metricFmt(latest?.features[key], key)}</strong>
                {latest?.features[key] == null && (
                  <small>
                    {latest?.missing_reasons[key] || "Brak obserwacji"}
                  </small>
                )}
              </div>
            ))}
          </div>
          <section className="card">
            <div className="section-title">
              <div>
                <p className="eyebrow">FINANSE W CZASIE</p>
                <h2>{metrics[metric]}</h2>
              </div>
              <select
                aria-label="Wskaźnik finansowy"
                value={metric}
                onChange={(e) => {
                  setMetric(e.target.value);
                  setSource(false);
                }}
              >
                {Object.entries(metrics).map(([key, label]) => (
                  <option key={key} value={key}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <Chart rows={c.years} metric={metric} />
            <p className="muted">
              {c.unit_note} Przerwy w danych przerywają linię wykresu.
            </p>
            <div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie">
              <table>
                <thead>
                  <tr>
                    <th>Rok</th>
                    <th>{metrics[metric]}</th>
                    <th>Status / przyczyna braku</th>
                    <th>Źródło</th>
                  </tr>
                </thead>
                <tbody>
                  {c.years.map((r) => (
                    <tr key={r.year}>
                      <td>{r.year}</td>
                      <td>{metricFmt(r.features[metric], metric)}</td>
                      <td>
                        {r.features[metric] == null
                          ? r.missing_reasons[metric] || r.selection_status
                          : "Wartość dostępna · dane prowizoryczne"}
                      </td>
                      <td>
                        <button
                          onClick={() => {
                            setYear(r.year);
                            setSource(true);
                          }}
                        >
                          Sprawdź źródło
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
          {showSource && (
            <section className="card">
              <div className="section-title">
                <h2>Pochodzenie wartości · {effectiveYear}</h2>
                <button onClick={() => setSource(false)}>Zamknij</button>
              </div>
              <State {...source} />
              {source.data != null && <Lineage trace={source.data} />}
            </section>
          )}
          <section className="card">
            <h2>Jakość i zakres informacji</h2>
            <p className="muted">{c.identity_note}</p>
            <div className="quality-list">
              {[...new Set(c.years.flatMap((y) => y.quality_codes))].map(
                (code) => (
                  <Tag key={code}>{code}</Tag>
                ),
              )}
            </div>
            <p>
              Peer group, ocena ryzyka oraz historyczne powiązania wymagają
              osobnych modeli i walidacji. Na tym etapie nie przypisujemy firmie
              oceny ani rekomendacji.
            </p>
          </section>
        </>
      )}
    </>
  );
}

function StudyView({ study }: { study: Study }) {
  const [variant, setVariant] = useState("untrimmed"),
    [model, setModel] = useState("firm_and_year_fe");
  const e = study.estimates.find(
    (x) => x.variant === variant && x.model === model,
  );
  return (
    <section className="card">
      <p className="eyebrow">{study.specification.id} · ZALEŻNOŚĆ WARUNKOWA</p>
      <h2>{study.specification.title}</h2>
      <p className="formula">
        {study.specification.outcome}(t+1) ~ {study.specification.exposure}(t)
        {study.specification.quadratic ? " + kwadrat" : ""} +{" "}
        {study.specification.controls.join(" + ")}
      </p>
      <div className="toolbar">
        <select
          aria-label={`Model ${study.specification.id}`}
          value={model}
          onChange={(x) => setModel(x.target.value)}
        >
          <option value="firm_and_year_fe">Efekty stałe firmy i roku</option>
          <option value="pooled_year_effects">Pooled OLS + efekty roku</option>
        </select>
        <select
          aria-label={`Wariant ${study.specification.id}`}
          value={variant}
          onChange={(x) => setVariant(x.target.value)}
        >
          <option value="untrimmed">Główny · bez przycinania</option>
          <option value="winsor_01_99">Wrażliwość · winsoryzacja 1/99</option>
        </select>
      </div>
      {e?.status === "estimated" ? (
        <>
          <div className="model-meta">
            <span>
              <b>{fmt(e.n_companies)}</b> firm
            </span>
            <span>
              <b>{fmt(e.n_observations)}</b> obserwacji
            </span>
            <span>
              R²: {scientific(e.r_squared)} · within R²:{" "}
              {scientific(e.within_r_squared)}
            </span>
            <span>SE klastrowane po firmie</span>
            <span>
              q BH testu głównego: {scientific(study.primary_test?.bh_q_value)}
            </span>
          </div>
          <div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie">
            <table>
              <thead>
                <tr>
                  <th>Zmienna</th>
                  <th>Współczynnik</th>
                  <th>Błąd standardowy</th>
                  <th>95% CI</th>
                  <th>p-value</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(e.coefficients).map(([key, c]) => (
                  <tr key={key}>
                    <td
                      className={
                        key === study.specification.primary_term
                          ? "emphasis"
                          : ""
                      }
                    >
                      {key}
                    </td>
                    <td>{scientific(c.coefficient)}</td>
                    <td>{scientific(c.standard_error)}</td>
                    <td>
                      [{scientific(c.ci95_low)}; {scientific(c.ci95_high)}]
                    </td>
                    <td>{scientific(c.p_value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <p className="notice">Brak estymacji dla wybranego wariantu.</p>
      )}
      <details>
        <summary>Dobór próby i pełne wyniki modelu</summary>
        <pre>
          {JSON.stringify(
            { sample_flow: study.sample_flow, estimate: e },
            null,
            2,
          )}
        </pre>
      </details>
      <p className="muted">
        Przedziały i p dotyczą wybranego wariantu. q BH koryguje rodzinę
        czterech głównych testów FE bez przycinania. Zmiana wariantu nie jest
        nowym dowodem potwierdzającym hipotezę.
      </p>
    </section>
  );
}

function ResearchPage({ dataset }: { dataset: string }) {
  const runs = useApi<{ id: string; created_at: string }[]>(
    `/api/research?dataset=${dataset}`,
  );
  const [chosen, setChosen] = useState("");
  const id = chosen || runs.data?.[0]?.id;
  const state = useApi<Research>(id ? `/api/research/${id}` : null);
  return (
    <>
      <p className="eyebrow">RESEARCH LAB</p>
      <h1>Co pokazują dane?</h1>
      <p className="muted">
        Cztery pytania, z góry zapisany protokół i jawna analiza wrażliwości.
      </p>
      <Notice />
      <State {...runs} />
      {runs.data?.length === 0 && (
        <p className="state">Brak zapisanych badań dla tej wersji danych.</p>
      )}
      {!!runs.data?.length && (
        <div className="toolbar">
          <label>
            Wersja obliczeń{" "}
            <select value={id} onChange={(e) => setChosen(e.target.value)}>
              {runs.data.map((r) => (
                <option key={r.id} value={r.id}>
                  {new Date(r.created_at).toLocaleString("pl-PL")} ·{" "}
                  {r.id.slice(0, 8)}
                </option>
              ))}
            </select>
          </label>
          <Tag>Brak walidacji predykcyjnej</Tag>
        </div>
      )}
      <State {...state} />
      {state.data && (
        <>
          <p className="muted">
            Zmienne X: lata 2018–2024. Wynik Y: dokładnie kolejny rok. Skrajne
            wartości powodują szerokie przedziały; brak istotności nie dowodzi
            braku związku.
          </p>
          <Diagnostics key={state.data.run_id} run={state.data.run_id} />
          {state.data.studies.map((s) => (
            <StudyView key={id + s.specification.id} study={s} />
          ))}
          <details className="card">
            <summary>Pełny protokół badawczy</summary>
            <pre>{JSON.stringify(state.data.protocol, null, 2)}</pre>
          </details>
        </>
      )}
    </>
  );
}

function ProfileResearch({ collection, onBrowse }: { collection: ProfileCollection; onBrowse: (status: string) => void }) {
  const s = collection.summary;
  const checks = [
    { label: "Próba ma finanse", value: s.selected_with_financials > 0, detail: `${fmt(s.selected_with_financials)} firm z wybranej grupy ma dane finansowe` },
    { label: "Kwalifikacja firm", value: false, detail: "Status dewelopera pochodzi z automatycznego opisu i wymaga potwierdzenia" },
    { label: "Porównywalność lat", value: false, detail: "Przed modelem trzeba wybrać wspólny rok bazowy, walutę i zakres sprawozdania" },
  ];
  return <>
    <p className="eyebrow">BADANIA · BIEŻĄCA PRÓBA</p>
    <h1>Przygotuj próbę do analizy</h1>
    <p className="muted">Ten ekran pokazuje gotowość danych do badania. Nie uruchamiamy modelu, dopóki kwalifikacja i porównywalność finansów nie są jawne.</p>
    <div className="stats">
      {[['Kandydaci według opisu', s.counts.developer_candidate], ['Z finansami', s.selected_with_financials], ['Do ręcznej kontroli', s.counts.review], ['Bez opisu', s.counts.missing_summary]].map(([label, value]) => <div className="stat" key={label}><span>{label}</span><strong>{fmt(Number(value))}</strong></div>)}
    </div>
    <section className="card readiness-card"><div className="section-title"><div><p className="eyebrow">KONTROLA JAKOŚCI</p><h2>Co jest gotowe, a czego brakuje?</h2></div><span className="tag">Eksploracyjnie</span></div>
      {checks.map(check => <div className="readiness-row" key={check.label}><span className={`readiness-icon ${check.value ? 'ready' : 'pending'}`}>{check.value ? '✓' : '!'}</span><div><strong>{check.label}</strong><p className="muted">{check.detail}</p></div><span className={`quality-pill ${check.value ? 'quality-ok' : 'quality-partial'}`}>{check.value ? 'Gotowe' : 'Wymaga decyzji'}</span></div>)}
    </section>
    <section className="card"><p className="eyebrow">NASTĘPNY KROK</p><h2>Najpierw weryfikacja, potem model</h2><p>Wybierz firmy do ręcznej kontroli, potwierdź działalność deweloperską na podstawie opisu, PKD i strony WWW, a następnie ustal jeden rok bazowy oraz zestaw wskaźników. Dopiero wtedy wynik porównania będzie interpretowalny.</p><div className="toolbar"><button className="primary" onClick={() => onBrowse('developer_candidate')}>Przejrzyj kandydatów →</button><button onClick={() => onBrowse('review')}>Otwórz kolejkę kontroli</button></div></section>
  </>;
}

const roadmap: Record<string, { title: string; needed: string }> = {
  "Early Warning": {
    title: "Ocena ryzyka wymaga walidacji",
    needed:
      "Definicja zdarzenia pogorszenia, etykiety wyników za 1–2 lata, chronologiczny podział prób, kalibracja oraz test na niewidzianych danych.",
  },
  Strategie: {
    title: "Typy firm wymagają analizy stabilności",
    needed:
      "Walidacja zmiennych, skalowanie i imputacja wyłącznie na próbie uczącej, porównanie metod grupowania i stabilności klastrów.",
  },
  Nieruchomości: {
    title: "Brak wystarczających danych o projektach",
    needed:
      "Potwierdzenie działalności deweloperskiej, lokalizacje inwestycji, ceny i cechy mieszkań, lokalne benchmarki oraz tempo sprzedaży. Sam PKD nie jest potwierdzeniem.",
  },
  "Decision Lab": {
    title: "Scenariusze potrzebują oszacowanego modelu",
    needed:
      "Dane projektowe, przepływy pieniężne, koszty finansowania i sprzedaży oraz walidacja modelu. Obecne dane nie pozwalają podać NPV, ROIC ani ryzyka projektu.",
  },
  Porównanie: {
    title: "Podobieństwo firm wymaga dodatkowych danych",
    needed:
      "Wiarygodna branża, region i wiek firmy oraz walidacja skali finansów. Dobór peer group musi uwzględniać stan firmy w wybranym roku i wspólne pokrycie cech.",
  },
};

function App() {
  const datasets = useApi<Dataset[]>("/api/datasets");
  const collections = useApi<ProfileCollection[]>("/api/profiles/collections");
  const currentCollection = collections.data?.[0];
  const [selected, setSelected] = useState("current");
  const current = selected === "current";
  const [profileStatus, setProfileStatus] = useState("all");
  const [profileKrs, setProfileKrs] = useState("");
  const dataset = selected || datasets.data?.[0]?.id;
  const [page, setPage] = useState("Dashboard"),
    [krs, setKrs] = useState("");
  const select = (k: string) => {
    setKrs(k);
    setPage("Firma");
    window.scrollTo(0, 0);
  };
  const nav = ["Dashboard", "Firmy", "Mapa", "Kredyty", "Badania"];
  const pageLabel = (name: string) =>
    name === "Dashboard"
      ? "Start"
      : name === "Firma"
      ? "Profil firmy"
      : name === "Kredyty"
      ? "Czy warto brać kredyty?"
      : name === "Mapa"
      ? "Finansowa mapa Polski"
      : name;
  const navIcons: Record<string, string> = {
    Dashboard: "M3 10 12 3l9 7v10H3V10Zm6 10v-7h6v7",
    Firmy: "M4 21V3h11v18M15 9h5v12M8 7h3M8 11h3M8 15h3M2 21h20",
    Mapa: "M3 6.5 8 3l8 3.5L21 3v14.5L16 21l-8-3.5L3 21V6.5ZM8 3v14.5M16 6.5V21",
    Kredyty: "M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6",
    Badania: "M4 3v17h17M8 15l4-5 4 2 5-7",
  };
  return (
    <div className="layout">
      <a className="skip-link" href="#main-content">Przejdź do treści</a>
      <aside className="app-sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setPage("Dashboard");
          }}
        >
          <span className="brand-icon">
            c<span>l</span>
          </span>
          <div>
            company lab<small>FIRMY I FINANSE</small>
          </div>
        </a>
        <nav aria-label="Nawigacja główna">
          {nav.map((n) => (
            <button
              className={page === n || (n === "Firmy" && page === "Firma") ? "active" : ""}
              key={n}
              aria-current={page === n || (n === "Firmy" && page === "Firma") ? "page" : undefined}
              onClick={() => { setPage(n); window.scrollTo(0, 0); }}
            >
              <svg className="nav-icon" aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d={navIcons[n]} /></svg>
              {pageLabel(n)}
              {roadmap[n] && <span className="planned">plan</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <span className="status-dot" /> Lokalna baza danych
          <p>
            Surowe źródła zachowane.
            <br />
            Każdy wynik ma swoją historię.
          </p>
        </div>
      </aside>
      <div className="workspace">
        <header>
          <span className="workspace-context">
            <span className="workspace-prefix">Company Lab <span className="slash">/</span></span> <b>{pageLabel(page)}</b>
          </span>
          <Tag>Firmy · finanse · badania</Tag>
        </header>
        <main id="main-content" className={`page-${page.toLowerCase()}`} tabIndex={-1}>
          <div className="workspace-tools">
            <div className="dataset-row">
              <span>Twoja baza</span>
              <span className="dataset-value">
                {currentCollection ? `${currentCollection.summary.profiles.toLocaleString("pl-PL")} firm` : "Wczytywanie…"}
              </span>
            </div>
            <PlainGuide />
          </div>
          <State {...(current ? collections : datasets)} />
          {current && !collections.loading && !collections.error && !currentCollection && <p className="state">Brak zaimportowanych bieżących profili.</p>}
          {!current && datasets.data?.length === 0 && (
            <p className="state">
              Brak opublikowanego panelu. Najpierw zakończ budowę i walidację
              datasetu.
            </p>
          )}
          {current && currentCollection && <div key={currentCollection.id}>
            {page === "Dashboard" ? <ProfileOverview collection={currentCollection} onResearch={() => { setPage("Badania"); window.scrollTo(0, 0); }} onBrowse={status => { setProfileStatus(status); setPage("Firmy"); window.scrollTo(0, 0); }} />
              : page === "Firmy" || (page === "Firma" && !profileKrs) ? <ProfileCatalog key={profileStatus} collection={currentCollection.id} initialStatus={profileStatus} onSelect={k => { setProfileKrs(k); setPage("Firma"); window.scrollTo(0,0); }} />
              : page === "Firma" ? <CurrentProfile collection={currentCollection.id} krs={profileKrs} onBack={() => setPage("Firmy")} />
              : page === "Mapa" ? <FinancialMap collection={currentCollection.id} onSelectCompany={k => { setProfileKrs(k); setPage("Firma"); window.scrollTo(0,0); }} />
              : page === "Kredyty" ? <CreditResearch collection={currentCollection.id} />
              : page === "Badania" ? <><SegmentedResearch collection={currentCollection.id} /><details className="friendly-details" style={{ marginTop: '24px' }}><summary>🔍 Dodatkowe badania: 4 pytania o strategię deweloperską oraz test kosztu kredytu (5%–10%)</summary><div style={{ marginTop: '16px' }}><DeveloperQuestions collection={currentCollection.id} /><LeverageResearch collection={currentCollection.id} /></div></details></>
              : <section className="card"><p className="eyebrow">{page.toUpperCase()} · BIEŻĄCA PRÓBA DEWELOPERÓW</p><h1>Najpierw kwalifikacja firm</h1><p>W bieżącym zbiorze wybrano {currentCollection.summary.counts.developer_candidate} kandydatów według opisu działalności. Analizy statystyczne i modele dla tej próby nie zostały jeszcze obliczone.</p><button onClick={() => setPage("Firmy")}>Przejrzyj wybrane firmy →</button></section>}
          </div>}
          {!current && dataset && (
            <div key={dataset}>
              <p className="notice">Archiwalny panel finansowy — obejmuje starszy zbiór firm. Wyniki nie dotyczą bieżącej listy deweloperów wybranych z opisów.</p>
              {page === "Dashboard" ? (
                <Overview
                  dataset={dataset}
                  onCompanies={() => setPage("Firmy")}
                />
              ) : page === "Firmy" ? (
                <Firms dataset={dataset} onSelect={select} />
              ) : page === "Firma" ? (
                krs ? (
                  <CompanyPage
                    key={krs}
                    dataset={dataset}
                    krs={krs}
                    onBack={() => setPage("Firmy")}
                  />
                ) : (
                  <Firms dataset={dataset} onSelect={select} />
                )
              ) : page === "Badania" ? (
                <ResearchPage dataset={dataset} />
              ) : (
                <>
                  <p className="eyebrow">{page.toUpperCase()} · KOLEJNY ETAP</p>
                  <h1>{roadmap[page].title}</h1>
                  <section className="card">
                    <Tag>Brak wystarczających danych / walidacji</Tag>
                    <h2>Co jest potrzebne?</h2>
                    <p>{roadmap[page].needed}</p>
                    <button onClick={() => setPage("Badania")}>
                      Zobacz dostępne badania →
                    </button>
                  </section>
                </>
              )}
            </div>
          )}
        </main>
        <footer>
          Company Lab{" "}
          <span>Poznaj firmę. Zrozum liczby. Sprawdź wnioski.</span>
        </footer>
      </div>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
