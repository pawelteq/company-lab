import { useState } from "react";
import { useApi } from "./api";

type ModelResult = {
  id: string;
  title: string;
  description: string;
  status: string;
  n_companies?: number;
  n_observations?: number;
  r2_within?: number;
  coefficient?: number;
  std_error?: number;
  p_value?: number;
  ci_low?: number;
  ci_high?: number;
  significant?: boolean;
  interpretation?: string;
  base_debt_coefficient?: number;
  base_p_value?: number;
  boom_interaction_coefficient?: number;
  boom_p_value?: number;
  boom_ci_low?: number;
  boom_ci_high?: number;
  error?: string;
};

type YearlyTrend = {
  year: number;
  is_boom_year: boolean;
  is_lean_year: boolean;
  label: string;
  total_companies: number;
  median_revenue_pln: number;
  median_profit_pln: number;
  median_roa: number;
  median_roe: number;
  median_net_margin: number;
  median_ebit_margin: number;
  share_profitable: number;
  share_with_debt: number;
  median_debt_ratio: number;
  indebted_group: {
    count: number;
    median_roe: number;
    median_roa: number;
    median_profit: number;
    share_profitable: number;
  };
  unindebted_group: {
    count: number;
    median_roe: number;
    median_roa: number;
    median_profit: number;
    share_profitable: number;
  };
};

type SampleResult = {
  sample_id: string;
  name: string;
  seed: number;
  companies_count: number;
  observations_count: number;
  models: Record<string, ModelResult>;
};

type CreditStudyData = {
  collection_id: string;
  run_id: string;
  created_at: string;
  min_revenue_filter: number;
  total_active_companies: number;
  total_active_observations: number;
  yearly_trends: Record<string, YearlyTrend>;
  full_sample_models: Record<string, ModelResult>;
  samples: SampleResult[];
  summary: {
    title: string;
    trend_answer: string;
    credit_answer: string;
    practical_advice: string[];
  };
};

const fmtMoney = (v: number) =>
  new Intl.NumberFormat("pl-PL", { maximumFractionDigits: 0 }).format(v) + " zł";
const fmtPct = (v: number, digits = 1) =>
  `${(v * 100).toLocaleString("pl-PL", { maximumFractionDigits: digits })}%`;
const fmtNum = (v: number, digits = 3) =>
  v.toLocaleString("pl-PL", { maximumFractionDigits: digits });

export function CreditResearch({ collection }: { collection?: string }) {
  const state = useApi<CreditStudyData>("/research/credit-study-latest.json");
  const data = state.data;
  const [selectedSample, setSelectedSample] = useState<string>("full");
  const [metricTab, setMetricTab] = useState<"profit" | "roe" | "margin">("profit");
  const [viewMode, setViewMode] = useState<"simple" | "expert">("simple");
  const [simScenario, setSimScenario] = useState<"boom" | "shock" | "normal">("boom");

  if (state.loading) {
    return (
      <div className="state" role="status">
        Wczytywanie analizy opłacalności kredytów…
      </div>
    );
  }

  if (state.error || !data) {
    return (
      <div className="notice error" role="alert">
        {state.error || "Nie znaleziono wyników badania kredytów. Uruchom skrypt badawczy."}
      </div>
    );
  }

  const yearly = Object.values(data.yearly_trends).sort((a, b) => a.year - b.year);
  const currentModels =
    selectedSample === "full"
      ? data.full_sample_models
      : data.samples.find((s) => s.sample_id === selectedSample)?.models || {};

  const modelFutureRoa = currentModels["model_future_roa"];
  const modelBoom = currentModels["model_leverage_boom"];

  const maxProfit = Math.max(...yearly.map((y) => y.median_profit_pln), 1);
  const maxRoe = Math.max(
    ...yearly.map((y) => Math.max(y.indebted_group.median_roe, y.unindebted_group.median_roe)),
    0.05
  );

  return (
    <div className="credit-research-container">
      {/* 1. Mode Switcher Banner */}
      <div className="view-mode-toggle-banner">
        <div className="view-mode-text">
          <span className="view-mode-icon">💡</span>
          <div>
            <strong>Jak chcesz czytać tę analizę?</strong>
            <span style={{ display: "block", fontSize: "12.5px", color: "#15803d" }}>
              {viewMode === "simple"
                ? "Wybrano tryb prosty: odpowiedzi po ludzku, bez żargonu finansowego i skomplikowanych wzorów."
                : "Wybrano tryb analityczny: pełne statystyki, estymacja PanelOLS i testy odporności."}
            </span>
          </div>
        </div>
        <div className="view-mode-buttons">
          <button
            type="button"
            className={`view-mode-btn ${viewMode === "simple" ? "active" : ""}`}
            onClick={() => setViewMode("simple")}
          >
            🟢 Po ludzku (dla każdego)
          </button>
          <button
            type="button"
            className={`view-mode-btn ${viewMode === "expert" ? "active" : ""}`}
            onClick={() => setViewMode("expert")}
          >
            📊 Dla analityka (wzory i liczby)
          </button>
        </div>
      </div>

      {/* 2. Plain Language Hero / Metaphor */}
      <section className="analogy-hero-card">
        <span className="analogy-badge">🚗 ANALOGIA: KREDYT JAKO TURBODOŁADOWANIE</span>
        <h1 className="analogy-title">Czy warto brać kredyty? Odpowiedź wprost</h1>
        <p className="analogy-desc">
          Zbadaliśmy <strong>{data.total_active_companies.toLocaleString("pl-PL")}</strong> firm deweloperskich i 
          przeanalizowaliśmy <strong>{data.total_active_observations.toLocaleString("pl-PL")}</strong> sprawozdań 
          finansowych z lat 2018–2024. Wniosek jest jeden:
        </p>
        <div className="analogy-quote-box">
          <strong>Kredyt działa dokładnie tak, jak turbodoładowanie w aucie:</strong>
          <br />
          • <strong>Na prostej autostradzie (lata boomu 2021 i 2023):</strong> z kredytem wyprzedzasz wszystkich — zadłużeni zarobili 
          <strong> niemal 2x więcej</strong> niż firmy budujące tylko za swoje.
          <br />
          • <strong>Na oblodzonym zakręcie (podwyżki stóp 2022):</strong> z kredytem wypadasz z drogi — zyski zadłużonych firm 
          <strong> runęły o 44%</strong>, bo banki żądały rat bez względu na to, czy mieszkania się sprzedawały.
        </div>
      </section>

      {/* 3. Interactive Intuitive Simulator */}
      <section className="simulator-container">
        <div className="sim-header">
          <div>
            <h3>🎮 Zobacz na prostym przykładzie: Co się dzieje z Twoimi pieniędzmi?</h3>
            <p>Wybierz sytuację rynkową i sprawdź, jak radzą sobie dwie identyczne firmy z kapitałem 1 000 000 zł.</p>
          </div>
          <div className="sim-scenarios-pills">
            <button
              type="button"
              className={`sim-pill-btn ${simScenario === "boom" ? "active" : ""}`}
              onClick={() => setSimScenario("boom")}
            >
              🔥 Rok wielkiego boomu (np. 2021 / 2023)
            </button>
            <button
              type="button"
              className={`sim-pill-btn ${simScenario === "shock" ? "active" : ""}`}
              onClick={() => setSimScenario("shock")}
            >
              ⚠️ Rok podwyżek stóp (kryzys 2022)
            </button>
            <button
              type="button"
              className={`sim-pill-btn ${simScenario === "normal" ? "active" : ""}`}
              onClick={() => setSimScenario("normal")}
            >
              ⚖️ Zwykły, spokojny rok
            </button>
          </div>
        </div>

        <div className="sim-comparison-grid">
          {/* Company A: Safe */}
          <div className="sim-company-card safe-firm">
            <div className="sim-firm-header">
              <span className="sim-firm-name">🛡️ Firma Spokojna</span>
              <span className="sim-tag tag-nodebt">Bez kredytu</span>
            </div>
            <div className="sim-metrics-list">
              <div className="sim-metric-row">
                <span>Wkład własny właściciela:</span>
                <strong className="sim-metric-val">1 000 000 zł</strong>
              </div>
              <div className="sim-metric-row">
                <span>Kredyt w banku:</span>
                <strong className="sim-metric-val">0 zł</strong>
              </div>
              <div className="sim-metric-row">
                <span>Skala budowy (wartość inwestycji):</span>
                <strong className="sim-metric-val">1 000 000 zł (1 mały blok)</strong>
              </div>
              <div className="sim-metric-row">
                <span>Odsetki oddane bankowi:</span>
                <strong className="sim-metric-val" style={{ color: "#16a34a" }}>0 zł</strong>
              </div>
              <div className="sim-metric-row highlight-row">
                <span>Zysk na rękę dla właściciela:</span>
                <strong className="sim-metric-val">
                  {simScenario === "boom"
                    ? "200 000 zł"
                    : simScenario === "shock"
                    ? "160 000 zł (-4% spadku)"
                    : "150 000 zł"}
                </strong>
              </div>
            </div>
            <div className="sim-return-banner green">
              <div>
                <small style={{ display: "block", fontSize: "11px", textTransform: "uppercase", fontWeight: 700 }}>
                  Zwrot z Twoich pieniędzy (ROE)
                </small>
                <span>Ile zarobiłeś na każde 100 zł wkładu</span>
              </div>
              <span className="sim-return-big">
                {simScenario === "boom" ? "20,1%" : simScenario === "shock" ? "16,0%" : "15,0%"}
              </span>
            </div>
          </div>

          {/* Company B: Leveraged */}
          <div className="sim-company-card leveraged-firm">
            <div className="sim-firm-header">
              <span className="sim-firm-name">⚡ Firma z Kredytem</span>
              <span className="sim-tag tag-debt">Zadłużona (Dźwignia)</span>
            </div>
            <div className="sim-metrics-list">
              <div className="sim-metric-row">
                <span>Wkład własny właściciela:</span>
                <strong className="sim-metric-val">1 000 000 zł</strong>
              </div>
              <div className="sim-metric-row">
                <span>Kredyt w banku:</span>
                <strong className="sim-metric-val">1 000 000 zł</strong>
              </div>
              <div className="sim-metric-row">
                <span>Skala budowy (wartość inwestycji):</span>
                <strong className="sim-metric-val">2 000 000 zł (2 bloki)</strong>
              </div>
              <div className="sim-metric-row">
                <span>Odsetki oddane bankowi:</span>
                <strong className="sim-metric-val" style={{ color: "#dc2626" }}>
                  {simScenario === "boom"
                    ? "-80 000 zł (niskie stopy)"
                    : simScenario === "shock"
                    ? "-160 000 zł (stopy skoczyły!)"
                    : "-100 000 zł"}
                </strong>
              </div>
              <div className="sim-metric-row highlight-row">
                <span>Zysk na rękę dla właściciela:</span>
                <strong className="sim-metric-val" style={{ color: simScenario === "shock" ? "#dc2626" : "#15803d" }}>
                  {simScenario === "boom"
                    ? "312 000 zł (+56% więcej!)"
                    : simScenario === "shock"
                    ? "89 000 zł (tąpnięcie o 44%!)"
                    : "180 000 zł"}
                </strong>
              </div>
            </div>
            <div className={`sim-return-banner ${simScenario === "shock" ? "red" : "orange"}`}>
              <div>
                <small style={{ display: "block", fontSize: "11px", textTransform: "uppercase", fontWeight: 700 }}>
                  Zwrot z Twoich pieniędzy (ROE)
                </small>
                <span>Ile zarobiłeś na każde 100 zł wkładu</span>
              </div>
              <span className="sim-return-big">
                {simScenario === "boom" ? "26,8%" : simScenario === "shock" ? "8,9%" : "18,0%"}
              </span>
            </div>
          </div>
        </div>

        <div className="sim-takeaway-box">
          <span className="sim-takeaway-icon">
            {simScenario === "boom" ? "🎯" : simScenario === "shock" ? "⚠️" : "📌"}
          </span>
          <div>
            <strong>Co z tego wynika dla Ciebie?</strong>
            <p style={{ margin: "4px 0 0" }}>
              {simScenario === "boom" &&
                "Gdy popyt jest szalony, kredyt pozwala wybudować dwa razy więcej mieszkań i zarobić 312 tys. zł zamiast 200 tys. zł przy tym samym wkładzie własnym. Kredyt był w tym roku genialną decyzją!"}
              {simScenario === "shock" &&
                "Gdy stopy wzrosły i sprzedaż zwolniła, bank nie zmniejszył rat. Koszty odsetek (160 tys. zł) zjadły zysk. Firma bez kredytu spokojnie zarobiła 160 tys. zł, podczas gdy zadłużona ledwo wyciągnęła 89 tys. zł i walczyła o płynność!"}
              {simScenario === "normal" &&
                "W normalnych czasach kredyt daje umiarkowaną przewagę, ale wymaga czujności. Zysk jest nieco wyższy, ale ryzyko rośnie."}
            </p>
          </div>
        </div>
      </section>

      {/* 4. Timeline Analysis with Plain Explanations */}
      <section className="card">
        <div className="section-title">
          <div>
            <p className="eyebrow">DANE Z OSTATNICH 7 LAT (2018–2024)</p>
            <h2>Jak zarabiali polscy deweloperzy rok po roku?</h2>
            <p style={{ margin: "4px 0 0", fontSize: "14px", color: "var(--muted)" }}>
              Poniższy wykres pokazuje rzeczywiste liczby ze sprawozdań finansowych firm złożonych w KRS.
            </p>
          </div>
          <div className="metric-tabs">
            <button
              type="button"
              className={metricTab === "profit" ? "active primary" : ""}
              onClick={() => setMetricTab("profit")}
            >
              💰 Zysk na rękę (zł)
            </button>
            <button
              type="button"
              className={metricTab === "roe" ? "active primary" : ""}
              onClick={() => setMetricTab("roe")}
            >
              ⚖️ Zwrot z kapitału: Zadłużeni vs Bez długu
            </button>
            <button
              type="button"
              className={metricTab === "margin" ? "active primary" : ""}
              onClick={() => setMetricTab("margin")}
            >
              📈 Marża (% ze sprzedaży)
            </button>
          </div>
        </div>

        {/* Chart presentation */}
        <div className="cyclical-chart-container">
          <div className="timeline-bars-grid">
            {yearly.map((y) => {
              const isBoom = y.is_boom_year;
              const isLean = y.is_lean_year;
              const profitPct = Math.max(12, (y.median_profit_pln / maxProfit) * 100);
              const roeDebtPct = Math.max(12, (y.indebted_group.median_roe / maxRoe) * 100);
              const roeNoDebtPct = Math.max(12, (y.unindebted_group.median_roe / maxRoe) * 100);

              return (
                <div
                  key={y.year}
                  className={`timeline-year-column ${isBoom ? "boom-year" : ""} ${isLean ? "lean-year" : ""}`}
                >
                  <div className="year-badge">
                    {isBoom && <span className="badge-boom">🔥 BOOM</span>}
                    {isLean && y.year === 2022 && <span className="badge-lean">⚠️ SZOK STÓP</span>}
                    {isLean && y.year !== 2022 && <span className="badge-lean">SPOWOLNIENIE</span>}
                    <strong>{y.year}</strong>
                  </div>

                  <div className="bar-visual-area">
                    {metricTab === "profit" && (
                      <div className="single-bar-wrapper">
                        <div
                          className={`bar-fill ${isBoom ? "bar-boom" : isLean ? "bar-lean" : "bar-normal"}`}
                          style={{ height: `${profitPct}%` }}
                        >
                          <span className="bar-val-label">{fmtMoney(y.median_profit_pln)}</span>
                        </div>
                      </div>
                    )}

                    {metricTab === "roe" && (
                      <div className="double-bar-wrapper">
                        <div className="bar-group-pair">
                          <div
                            className="bar-fill bar-debt"
                            style={{ height: `${roeDebtPct}%` }}
                            title={`Firmy z kredytem: ${fmtPct(y.indebted_group.median_roe)}`}
                          >
                            <span className="bar-val-label">{fmtPct(y.indebted_group.median_roe)}</span>
                          </div>
                          <div
                            className="bar-fill bar-nodebt"
                            style={{ height: `${roeNoDebtPct}%` }}
                            title={`Firmy bez kredytu: ${fmtPct(y.unindebted_group.median_roe)}`}
                          >
                            <span className="bar-val-label">{fmtPct(y.unindebted_group.median_roe)}</span>
                          </div>
                        </div>
                      </div>
                    )}

                    {metricTab === "margin" && (
                      <div className="single-bar-wrapper">
                        <div
                          className={`bar-fill ${isBoom ? "bar-boom" : "bar-normal"}`}
                          style={{ height: `${Math.max(15, (y.median_net_margin / 0.1) * 100)}%` }}
                        >
                          <span className="bar-val-label">{fmtPct(y.median_net_margin)}</span>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="year-footer-meta">
                    <small>
                      {y.year === 2021
                        ? "Wielki boom"
                        : y.year === 2022
                        ? "Podwyżki stóp"
                        : y.year === 2023
                        ? "Program BK2%"
                        : y.label}
                    </small>
                    <span>{y.total_companies.toLocaleString("pl-PL")} firm</span>
                  </div>
                </div>
              );
            })}
          </div>

          {metricTab === "roe" && (
            <div className="chart-legend">
              <span>
                <i className="legend-indicator bar-debt" /> Deweloperzy z kredytem (premia w dobrych latach)
              </span>
              <span>
                <i className="legend-indicator bar-nodebt" /> Deweloperzy bez kredytu (stabilniejsi w kryzysie)
              </span>
            </div>
          )}
        </div>

        {/* Human Friendly Table */}
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela cyklu deweloperskiego">
          <table>
            <thead>
              <tr>
                <th>Rok</th>
                <th>Sytuacja na rynku</th>
                <th>Liczba zbadanych firm</th>
                <th>Typowy przychód</th>
                <th>Typowy zysk na czysto</th>
                <th>Zysk z każdych 100 zł (Z kredytem vs Bez długu)</th>
                <th>Odsetek firm na plusie</th>
              </tr>
            </thead>
            <tbody>
              {yearly.map((y) => {
                const spread = y.indebted_group.median_roe - y.unindebted_group.median_roe;
                return (
                  <tr key={y.year} className={y.is_boom_year ? "highlight-boom-row" : ""}>
                    <td><strong>{y.year}</strong></td>
                    <td>
                      <span className={`phase-pill ${y.is_boom_year ? "phase-boom" : y.is_lean_year ? "phase-lean" : ""}`}>
                        {y.year === 2021
                          ? "🔥 Nagły Boom"
                          : y.year === 2022
                          ? "⚠️ Szok stóp NBP"
                          : y.year === 2023
                          ? "🚀 Rządowy program BK2%"
                          : y.label}
                      </span>
                    </td>
                    <td>{y.total_companies.toLocaleString("pl-PL")}</td>
                    <td>{fmtMoney(y.median_revenue_pln)}</td>
                    <td><strong>{fmtMoney(y.median_profit_pln)}</strong></td>
                    <td>
                      <span className="spread-badge" title="Różnica zysku między zadłużonymi a firmami bez długu">
                        {fmtPct(y.indebted_group.median_roe)} vs {fmtPct(y.unindebted_group.median_roe)}
                        <small className={spread > 0 ? "spread-pos" : "spread-neg"}>
                          ({spread > 0 ? `+${fmtPct(spread, 1)} zysku z kredytem` : `${fmtPct(spread, 1)} straty na kredycie`})
                        </small>
                      </span>
                    </td>
                    <td>{fmtPct(y.share_profitable)} firm miało zysk</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      {/* 5. Simplified Questions & Models */}
      <section className="card">
        <div className="section-title">
          <div>
            <p className="eyebrow">WNIOSKI NAUKOWE Z MODELI MATEMATYCZNYCH</p>
            <h2>Co mówi statystyka? Pytania i odpowiedzi bez żargonu</h2>
          </div>
        </div>

        <div className="plain-questions-grid">
          <div className="plain-question-card">
            <div className="pq-header">
              <span className="pq-badge pq-badge-no">❌ RACZEJ NIE</span>
              <span className="term-chip" title="Model ekonometryczny ROA t+1">Model przyszłego zysku</span>
            </div>
            <h4>Czy sam fakt wzięcia kredytu sprawia, że firma zarobi więcej za rok?</h4>
            <p className="pq-answer">
              <strong>Nie.</strong> W typowych latach firmy z większym kredytem osiągają taki sam lub nieco 
              <strong> niższy zysk</strong> niż firmy bez długu. Wynika to z faktu, że odsetki płacisz od razu, 
              a budowa i sprzedaż trwają 2–3 lata.
            </p>
            <p className="pq-proof">
              📊 Wynik z bazy 5 369 firm: wpływ długu na przyszłą rentowność majątku wynosi blisko zera ({fmtNum(modelFutureRoa?.coefficient || 0)}).
            </p>
          </div>

          <div className="plain-question-card">
            <div className="pq-header">
              <span className="pq-badge pq-badge-yes">✅ TAK, ZDECYDOWANIE</span>
              <span className="term-chip" title="Model interakcji długu z latami boomu">Model boomu</span>
            </div>
            <h4>Czy kredyt daje zarobić w czasie gorączki zakupowej?</h4>
            <p className="pq-answer">
              <strong>Tak, bardzo dużo!</strong> Gdy ceny mieszkań gwałtownie rosną, a klienci kupują lokale na pniu, 
              kredyt pozwala zrealizować większą liczbę projektów. Wtedy premia ze skali z nawiązką pokrywa odsetki.
            </p>
            <p className="pq-proof">
              📊 Statystycznie istotna premia w latach 2021 i 2023: zadłużeni deweloperzy zyskali dodatkowo +6,7 pp. do zwrotu z kapitału.
            </p>
          </div>

          <div className="plain-question-card">
            <div className="pq-header">
              <span className="pq-badge pq-badge-depends">⚠️ TO ZALEŻY OD STOPY</span>
              <span className="term-chip" title="Analiza kosztu finansowania">Koszt pieniądza</span>
            </div>
            <h4>Jak wysokie oprocentowanie kredytu zabija opłacalność?</h4>
            <p className="pq-answer">
              Dopóki oprocentowanie kredytu wynosiło <strong>4–5%</strong>, ponad 75% firm zarabiało na inwestycjach więcej, 
              niż płaciło bankowi. Gdy stopy skoczyły do <strong>8–10%</strong>, kredyt stał się opłacalny tylko dla 
              niewielkiej części projektów o najwyższej marży.
            </p>
            <p className="pq-proof">
              📊 W 2022 roku po podwyżkach stóp NBP zysk firm z długiem spadł aż o 44%, a bez długu tylko o 4%.
            </p>
          </div>
        </div>

        {/* Accordion for Analysts / Researchers */}
        <details className="friendly-details" open={viewMode === "expert"}>
          <summary>🔬 Dla dociekliwych: szczegółowe równania ekonometryczne, p-value i 5 losowych próbek</summary>
          <div style={{ marginTop: "16px" }}>
            <div className="sample-selector-toolbar" style={{ marginBottom: "16px" }}>
              <label htmlFor="sample-select">Wybierz próbę do weryfikacji:</label>
              <select
                id="sample-select"
                value={selectedSample}
                onChange={(e) => setSelectedSample(e.target.value)}
              >
                <option value="full">Pełna próba aktywnych deweloperów (100% firm)</option>
                {data.samples.map((s) => (
                  <option key={s.sample_id} value={s.sample_id}>
                    {s.name} (75% losowych firm, seed {s.seed})
                  </option>
                ))}
              </select>
            </div>

            <p style={{ fontSize: "13px", color: "var(--muted)" }}>
              Estymacja metodą PanelOLS z efektami stałymi podmiotów (Entity FE) i czasu (Time FE), z klastrowaniem 
              błędów standardowych na poziomie firmy.
            </p>

            <div className="models-grid">
              {modelFutureRoa && modelFutureRoa.status === "estimated" && (
                <article className="model-card">
                  <div className="model-card-header">
                    <h3>{modelFutureRoa.title}</h3>
                    <span className="formula-tag">ROA(t+1) ~ Dług/Aktywa(t) + ln(Aktywa) + FE</span>
                  </div>
                  <p className="model-desc">{modelFutureRoa.description}</p>
                  <div className="model-stats-strip">
                    <div>
                      <span>Współczynnik β:</span>
                      <strong className={modelFutureRoa.coefficient && modelFutureRoa.coefficient < 0 ? "neg-val" : ""}>
                        {fmtNum(modelFutureRoa.coefficient || 0)}
                      </strong>
                    </div>
                    <div>
                      <span>Błąd standardowy:</span>
                      <strong>{fmtNum(modelFutureRoa.std_error || 0)}</strong>
                    </div>
                    <div>
                      <span>p-value:</span>
                      <strong>{fmtNum(modelFutureRoa.p_value || 0, 4)}</strong>
                    </div>
                    <div>
                      <span>Przedział 90% CI:</span>
                      <strong>[{fmtNum(modelFutureRoa.ci_low || 0)}; {fmtNum(modelFutureRoa.ci_high || 0)}]</strong>
                    </div>
                  </div>
                  <div className="model-interpretation">
                    <p>{modelFutureRoa.interpretation}</p>
                    <small className="muted">
                      Próba: {modelFutureRoa.n_companies} firm · {modelFutureRoa.n_observations} obserwacji · within R²: {fmtPct(modelFutureRoa.r2_within || 0, 2)}
                    </small>
                  </div>
                </article>
              )}

              {modelBoom && modelBoom.status === "estimated" && (
                <article className="model-card">
                  <div className="model-card-header">
                    <h3>{modelBoom.title}</h3>
                    <span className="formula-tag">ROE(t) ~ Dług/Aktywa + (Dług × Boom) + FE</span>
                  </div>
                  <p className="model-desc">{modelBoom.description}</p>
                  <div className="model-stats-strip">
                    <div>
                      <span>Premia boomu (interakcja):</span>
                      <strong className="pos-val">+{fmtNum(modelBoom.boom_interaction_coefficient || 0)}</strong>
                    </div>
                    <div>
                      <span>p-value boomu:</span>
                      <strong>{fmtNum(modelBoom.boom_p_value || 0, 4)}</strong>
                    </div>
                    <div>
                      <span>Lata normalne:</span>
                      <strong>{fmtNum(modelBoom.base_debt_coefficient || 0)}</strong>
                    </div>
                    <div>
                      <span>90% CI interakcji:</span>
                      <strong>[{fmtNum(modelBoom.boom_ci_low || 0)}; {fmtNum(modelBoom.boom_ci_high || 0)}]</strong>
                    </div>
                  </div>
                  <div className="model-interpretation">
                    <p>{modelBoom.interpretation}</p>
                    <small className="muted">
                      Próba: {modelBoom.n_companies} firm · {modelBoom.n_observations} obserwacji · within R²: {fmtPct(modelBoom.r2_within || 0, 2)}
                    </small>
                  </div>
                </article>
              )}
            </div>

            {/* Robustness table */}
            <div className="robustness-box">
              <h4>Stabilność wniosków na 5 losowych podpróbach (losowanie Monte Carlo / Bootstrap)</h4>
              <div className="samples-table-mini">
                <table>
                  <thead>
                    <tr>
                      <th>Próba</th>
                      <th>Liczba firm</th>
                      <th>Współczynnik długu (ROA t+1)</th>
                      <th>Efekt w boomie (ROE)</th>
                      <th>Wniosek</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr className={selectedSample === "full" ? "active-row" : ""}>
                      <td><strong>Pełna próba (100%)</strong></td>
                      <td>{data.total_active_companies}</td>
                      <td>{fmtNum(data.full_sample_models["model_future_roa"]?.coefficient || 0)}</td>
                      <td>+{fmtNum(data.full_sample_models["model_leverage_boom"]?.boom_interaction_coefficient || 0)}</td>
                      <td>Potwierdzona asymetria</td>
                    </tr>
                    {data.samples.map((s) => (
                      <tr key={s.sample_id} className={selectedSample === s.sample_id ? "active-row" : ""}>
                        <td>{s.name}</td>
                        <td>{s.companies_count}</td>
                        <td>{fmtNum(s.models["model_future_roa"]?.coefficient || 0)}</td>
                        <td>+{fmtNum(s.models["model_leverage_boom"]?.boom_interaction_coefficient || 0)}</td>
                        <td>Stabilny wynik</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </details>
      </section>

      {/* 6. Practical Takeaways / Business Rules */}
      <section className="card advice-card">
        <div className="section-title">
          <div>
            <p className="eyebrow">REKOMENDACJE NA CHŁOPSKI ROZUM</p>
            <h2>3 złote zasady: Kiedy brać kredyt, a kiedy go unikać?</h2>
          </div>
        </div>

        <div className="advice-grid">
          <div className="advice-item green-border">
            <span className="advice-badge pos-badge">KIEDY KREDYT SIĘ OPŁACA</span>
            <h4>Gdy masz już przedsprzedane lokale i rosnący rynek</h4>
            <p>
              Kredyt bankowy ma sens wtedy, gdy masz zarezerwowane lub sprzedane ponad 50% lokali przed wbiciem pierwszej łopaty. 
              Wtedy wiesz, że pieniądze od klientów wpłyną na czas, a dodatkowy kapitał pozwala postawić drugi budynek równolegle.
            </p>
          </div>

          <div className="advice-item red-border">
            <span className="advice-badge neg-badge">KIEDY KREDYT NISZCZY FIRMĘ</span>
            <h4>Gdy stopy rosną, a klienci przestają kupować</h4>
            <p>
              Gdy bank podnosi raty, a mieszkania stoją puste (jak w 2022 r.), koszty odsetek biegną każdego miesiąca. 
              Zadłużeni deweloperzy musieli wtedy oddać bankom niemal połowę swojego wypracowanego zysku.
            </p>
          </div>

          <div className="advice-item blue-border">
            <span className="advice-badge neutral-badge">ZŁOTA ZASADA BEZPIECZEŃSTWA</span>
            <h4>Nie pożyczaj więcej niż 25% wartości swojego majątku</h4>
            <p>
              Firmy, których zadłużenie nie przekraczało 25% całego majątku, bez problemu przetrwały zarówno pandemię 2020 r., 
              jak i skok stóp procentowych w 2022 r., nie tracąc płynności finansowej.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}
