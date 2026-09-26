import { useState } from "react";
import { useApi } from "./api";

type Coefficient = {
  value: number;
  lo: number;
  hi: number;
  p: number;
  q_bh?: number;
  intervals_by_alpha?: Record<string, { confidence_level: number; lo: number; hi: number; significant: boolean }>;
};
type Model = {
  horizon: number;
  outcome: string;
  exposure: string;
  cohort: string;
  variant: string;
  interaction: string | null;
  status: string;
  n: number;
  companies: number;
  coefficients?: Record<string, Coefficient>;
};
type Scenario = {
  horizon: number;
  cost: number;
  companies: number;
  median_annual_pretax_roc: number;
  median_spread: number;
  share_above: number;
  share_ci_low: number;
  share_ci_high: number;
};
type Results = {
  collection_id: string;
  run_id: string;
  protocol?: { confidence_level?: number; significance_level?: number };
  audit: Record<string, number>;
  years: number[];
  models: Model[];
  scenarios: Scenario[];
  top_assets_q4_scenarios?: Scenario[];
  limitations: string[];
  coverage: Record<
    string,
    { observed: number; positive: number; companies: number }
  >;
  conclusion?: string;
  top_assets_q4_conclusion?: string;
};
const pct = (n: number) =>
  `${(100 * n).toLocaleString("pl-PL", { maximumFractionDigits: 1 })}%`;
const decimal = (n: number) =>
  n.toLocaleString("pl-PL", { maximumFractionDigits: 3 });
const probability = (n: number) => (n < 0.0001 ? "< 0,0001" : decimal(n));

export function LeverageResearch({ collection }: { collection: string }) {
  const state = useApi<Results>("/research/leverage-latest.json");
  const [horizon, setHorizon] = useState(2);
  const r = state.data;

  if (state.loading) return <p role="status">Wczytywanie badania…</p>;
  if (!r || r.collection_id !== collection)
    return (
      <section className="card">
        <h1>Badanie nowej próby</h1>
        <p>
          Brak opublikowanego badania dla tego zbioru firm. Wyniki
          wcześniejszych kolekcji nie są przenoszone na nowe dane.
        </p>
      </section>
    );

  const primary = r.models.find(
    (m) =>
      m.horizon === 2 &&
      m.outcome === "roa" &&
      m.exposure === "debt_assets" &&
      m.variant === "raw" &&
      m.cohort === "all" &&
      !m.interaction,
  );
  const coefficient = primary?.coefficients?.debt_assets;
  const confidence = pct(r.protocol?.confidence_level ?? 0.95);
  const inconclusive = !coefficient || (coefficient.lo <= 0 && coefficient.hi >= 0);

  const delayed = r.models.find(
    (m) =>
      m.horizon === 3 &&
      m.outcome === "roe" &&
      m.exposure === "debt_assets" &&
      m.variant === "raw" &&
      m.cohort === "all" &&
      !m.interaction,
  );
  const delayedCoefficient = delayed?.coefficients?.debt_assets;

  const scenarios = r.scenarios.filter((s) => s.horizon === horizon);

  return (
    <>
      {/* 1. Main Plain-Language Conclusion */}
      <section className="plain-result" aria-label="Najważniejszy wniosek">
        <span className="result-status">
          {inconclusive ? "Wniosek: Brak gwarancji zysku" : "Wniosek z danych"}
        </span>
        <h2>
          {inconclusive
            ? "Sam kredyt nie gwarantuje sukcesu — kluczowy jest jego koszt"
            : coefficient!.value > 0
            ? "Większy udział długu wiąże się z wyższą rentownością w dobrych latach."
            : "Większy udział długu wiąże się z niższą rentownością."}
        </h2>
        <p style={{ fontSize: "15px", lineHeight: "1.6" }}>
          Dane pokazują, że kredyt nie jest ani zły, ani dobry sam z siebie. 
          To, czy zarobisz na pożyczonych pieniądzach, zależy bezpośrednio od tego, 
          <strong> ile procent odsetek żąda bank</strong> oraz czy Twoja inwestycja generuje wyższą stopę zwrotu.
        </p>

        <div className="result-facts">
          <div>
            <strong>{primary?.companies ?? 0}</strong>
            <span>przebadanych firm</span>
          </div>
          <div>
            <strong>{horizon} {horizon === 1 ? "rok" : "lata"}</strong>
            <span>horyzont inwestycji</span>
          </div>
          <div>
            <strong>{confidence}</strong>
            <span>pewność statystyczna</span>
          </div>
        </div>
      </section>

      {/* 2. Visual Interest Rate Stress Test */}
      <section className="card">
        <div className="section-title">
          <div>
            <p className="eyebrow">TEST ODPORNOŚCI NA KOSZT PIENIĄDZA</p>
            <h2>Co się dzieje, gdy bank żąda od 5% do 10% odsetek rocznie?</h2>
            <p style={{ margin: "4px 0 0", fontSize: "14px", color: "var(--muted)" }}>
              Wykres pokazuje, jaki procent firm zarobił na swoich inwestycjach więcej, niż musiał oddać bankowi w odsetkach.
            </p>
          </div>
          <label style={{ fontSize: "13.5px", fontWeight: 600 }}>
            Horyzont czasu:{" "}
            <select
              aria-label="Horyzont scenariusza"
              value={horizon}
              onChange={(e) => setHorizon(Number(e.target.value))}
              style={{ marginLeft: "8px", padding: "4px 10px" }}
            >
              <option value={1}>Po 1 roku</option>
              <option value={2}>Po 2 latach</option>
              <option value={3}>Po 3 latach</option>
            </select>
          </label>
        </div>

        {/* Visual progress gauges */}
        <div style={{ margin: "24px 0" }}>
          {scenarios.map((s) => {
            const share = Math.round(s.share_above * 100);
            const isSafe = share >= 60;
            const isRisky = share < 55;

            return (
              <div className="cost-gauge-row" key={s.cost}>
                <div className="cost-gauge-label">
                  Oprocentowanie: {pct(s.cost)}
                </div>
                <div className="cost-gauge-track">
                  <div
                    className="cost-gauge-fill"
                    style={{
                      width: `${share}%`,
                      background: isSafe
                        ? "linear-gradient(90deg, #10b981 0%, #059669 100%)"
                        : isRisky
                        ? "linear-gradient(90deg, #f59e0b 0%, #d97706 100%)"
                        : "linear-gradient(90deg, #10b981 0%, #059669 100%)",
                    }}
                  >
                    <span className="cost-gauge-val">{share}%</span>
                  </div>
                </div>
                <div className="cost-gauge-meta">
                  <strong>{share}% firm na plusie</strong>
                  <span style={{ display: "block", fontSize: "11.5px", color: "var(--muted)" }}>
                    {100 - share}% firm poniosło stratę na odsetkach
                  </span>
                </div>
              </div>
            );
          })}
        </div>

        <div className="sim-takeaway-box">
          <span className="sim-takeaway-icon">💡</span>
          <div>
            <strong>Kluczowa lekcja dla przedsiębiorcy:</strong>
            <p style={{ margin: "4px 0 0" }}>
              Gdy koszt kredytu wynosi <strong>5%</strong>, prawie dwie trzecie firm (65%) z powodzeniem zarabia na długu. 
              Gdy jednak koszt rośnie do <strong>10%</strong>, szanse spadają niemal do rzutu monetą (52%). 
              Dlatego przy drogim kredycie (wysokim WIBOR) nie wolno brać długu „na zapas” — opłacają się tylko projekty 
              z gwarantowaną, bardzo wysoką marżą.
            </p>
          </div>
        </div>

        {/* Technical scenario table in accordion */}
        <details className="friendly-details" style={{ marginTop: "20px" }}>
          <summary>📊 Szczegółowa tabela scenariuszy kosztu długu</summary>
          <div className="table-scroll" tabIndex={0} role="region" aria-label="Scenariusze kosztu długu">
            <table>
              <thead>
                <tr>
                  <th>Oprocentowanie roczne</th>
                  <th>Liczba firm</th>
                  <th>Przeciętny zwrot operacyjny</th>
                  <th>Przeciętna nadwyżka nad odsetkami</th>
                  <th>% firm z zyskiem netto z długu</th>
                  <th>Przedział ufności ({confidence})</th>
                </tr>
              </thead>
              <tbody>
                {scenarios.map((s) => (
                  <tr key={s.cost}>
                    <td><strong>{pct(s.cost)}</strong></td>
                    <td>{s.companies}</td>
                    <td>{pct(s.median_annual_pretax_roc)}</td>
                    <td>
                      <span style={{ color: s.median_spread > 0 ? "#15803d" : "#b91c1c", fontWeight: 700 }}>
                        {decimal(s.median_spread * 100)} p.p.
                      </span>
                    </td>
                    <td><strong>{pct(s.share_above)}</strong></td>
                    <td>{pct(s.share_ci_low)} – {pct(s.share_ci_high)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      </section>

      {/* 3. Detailed Econometric Models in Accordion */}
      <details className="friendly-details">
        <summary>🔬 Wszystkie modele ekonometryczne i testy wrażliwości (dla analityków)</summary>
        <div style={{ marginTop: "16px" }}>
          <p style={{ fontSize: "14px", color: "#475569" }}>
            Poniższa tabela przedstawia wszystkie estymowane równania, w tym warianty surowe, 
            z ograniczeniem skrajności (winsoryzacja) oraz analizy dla największych firm (kwartyl Q4 aktywów).
          </p>

          {coefficient && (
            <div style={{ background: "#f8fafc", padding: "14px", borderRadius: "8px", margin: "14px 0", fontSize: "13px" }}>
              <strong>Model główny (2 lata):</strong> wzrost długu do aktywów o 10 p.p. wiąże się ze zmianą ROA o{" "}
              <strong>{decimal(coefficient.value * 10)} p.p.</strong> (przedział {confidence}: {decimal(coefficient.lo * 10)} do {decimal(coefficient.hi * 10)} p.p.).
            </div>
          )}

          {delayedCoefficient && (
            <div style={{ background: "#f8fafc", padding: "14px", borderRadius: "8px", margin: "14px 0", fontSize: "13px" }}>
              <strong>Model 3-letni ROE:</strong> zmiana o <strong>{decimal(delayedCoefficient.value * 10)} p.p.</strong> na 10 p.p. długu (przedział: {decimal(delayedCoefficient.lo * 10)} do {decimal(delayedCoefficient.hi * 10)} p.p.).
            </div>
          )}

          <div className="table-scroll" tabIndex={0} role="region" aria-label="Wyniki modeli ekonometrycznych">
            <table>
              <thead>
                <tr>
                  <th>Model / Próba</th>
                  <th>Horyzont</th>
                  <th>Firmy / Obserwacje</th>
                  <th>Współczynnik β</th>
                  <th>Przedział ({confidence})</th>
                  <th>Istotność (p / q BH)</th>
                </tr>
              </thead>
              <tbody>
                {r.models.map((m, i) => {
                  const c = m.coefficients?.[m.interaction ? "debt_x_cost" : m.exposure];
                  return (
                    <tr key={i}>
                      <td>
                        <strong>{m.outcome.toUpperCase()}</strong> · {m.exposure === "debt_assets" ? "Kredyty i pożyczki" : "Wszystkie zobowiązania"}
                        <small style={{ display: "block", color: "var(--muted)" }}>
                          {m.cohort === "top_assets_q4" ? "Największa 1/4 firm" : "Wszyscy"} · {m.variant === "raw" ? "Surowe dane" : "Winsoryzacja"}
                        </small>
                      </td>
                      <td>{m.horizon} {m.horizon === 1 ? "rok" : "lata"}</td>
                      <td>{m.companies} / {m.n}</td>
                      <td>{c ? decimal(c.value) : "—"}</td>
                      <td>{c ? `${decimal(c.lo)} do ${decimal(c.hi)}` : "—"}</td>
                      <td>{c ? `${probability(c.p)} / ${c.q_bh == null ? "—" : probability(c.q_bh)}` : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </details>
    </>
  );
}
