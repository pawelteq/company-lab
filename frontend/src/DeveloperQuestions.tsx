import { useState } from "react";
import { useApi } from "./api";

type Coefficient = { value: number; lo: number; hi: number; p: number; q_bh?: number };
type Question = {
  id: string;
  question: string;
  exposure: string;
  variant: string;
  status: string;
  companies: number;
  n: number;
  coefficients?: Record<string, Coefficient>;
};
type Result = {
  protocol?: { confidence_level?: number };
  collection_id: string;
  run_id: string;
  audit: Record<string, number>;
  years: number[];
  questions: Question[];
  limitations: string[];
  stability: Record<
    string,
    { companies: number; median_roa_volatility: number; median_ebit_margin_volatility: number }
  >;
};

const number = (v: number) => v.toLocaleString("pl-PL", { maximumFractionDigits: 3 });
const pct = (v: number) => `${(v * 100).toLocaleString("pl-PL", { maximumFractionDigits: 1 })}%`;
const p = (v: number) => (v < 0.0001 ? "< 0,0001" : number(v));

const questionMeta: Record<
  string,
  {
    icon: string;
    humanTitle: string;
    verdict: "yes" | "no" | "depends";
    verdictLabel: string;
    simpleAnswer: string;
    businessAdvice: string;
  }
> = {
  inventory_revenue: {
    icon: "🏗️",
    humanTitle: "Czy duży bank ziemi i zapas lokali przyspiesza wzrost sprzedaży?",
    verdict: "yes",
    verdictLabel: "TAK (ZDECYDOWANIE)",
    simpleAnswer:
      "Firmy posiadające większy udział zapasów (gruntów i mieszkań w budowie) notują w kolejnym roku o kilkanaście procent szybszy wzrost przychodów. Mają co sprzedawać, gdy pojawiają się klienci.",
    businessAdvice:
      "Gromadzenie gruntów daje silnik do wzrostu, ale pamiętaj: ziemia nie przynosi zysku, dopóki nie zaczniesz na niej budować.",
  },
  inventory_margin: {
    icon: "🏷️",
    humanTitle: "Czy duży bank ziemi automatycznie gwarantuje wyższą rentowność marży?",
    verdict: "no",
    verdictLabel: "NIE WPROST",
    simpleAnswer:
      "Posiadanie wielu działek nie podnosi automatycznie marży operacyjnej. O zysku decydują koszty wykonawstwa i ceny, jakie zaakceptuje rynek, a nie sama ilość zamrożonego gruntu.",
    businessAdvice:
      "Za drogo kupiona działka leżąca w banku ziemi generuje koszty finansowania i może obniżyć rentowność całej firmy.",
  },
  cash_roa: {
    icon: "💵",
    humanTitle: "Czy trzymanie milionów w gotówce na koncie zwiększa rentowność firmy?",
    verdict: "no",
    verdictLabel: "NIE (TO PODUSZKA, NIE ZYSK)",
    simpleAnswer:
      "Gotówka na koncie daje poczucie bezpieczeństwa, ale wiąże się z nieco niższym wskaźnikiem ROA. Pieniądze na lokacie bankowej zarabiają mniej niż kapitał zainwestowany w budowę mieszkań.",
    businessAdvice:
      "Utrzymuj gotówkę na czarną godzinę (bezpieczny bufor na 6–12 miesięcy), ale nadwyżki inwestuj w projekty o wyższej stopie zwrotu.",
  },
  receivables_roa: {
    icon: "🧾",
    humanTitle: "Czy duże należności (pieniądze, które są Ci winni inni) niszczą zysk?",
    verdict: "depends",
    verdictLabel: "OBCIĄŻENIE PŁYNNOŚCI",
    simpleAnswer:
      "Duże zamrożone należności mają tendencję do osłabiania wyników kolejnego roku. Niezapłacone na czas faktury zmuszają firmę do zaciągania drogich kredytów obrotowych.",
    businessAdvice:
      "Pilnuj terminów płatności od klientów i kontrahentów — pieniądze na papierze to nie pieniądze na koncie.",
  },
};

function impact(q: Question, value: number) {
  if (q.id === "inventory_revenue") return `+${pct(Math.expm1(value * 0.1))} szybsze tempo przychodu`;
  return `${value > 0 ? "+" : ""}${number(value * 10)} p.p. zmiany zysku`;
}

export function DeveloperQuestions({ collection }: { collection: string }) {
  const state = useApi<Result>("/research/developer-questions-latest.json");
  const [showTechnical, setShowTechnical] = useState(false);
  const r = state.data;

  if (state.loading) return <p role="status">Wczytywanie pytań badawczych…</p>;
  if (!r || r.collection_id !== collection) return null;

  const confidence = pct(r.protocol?.confidence_level ?? 0.95);
  const primary = r.questions.filter((q) => q.variant === "raw");
  const robust = r.questions.filter((q) => q.variant === "winsor_01_99");

  return (
    <>
      <section className="card">
        <div className="section-title">
          <div>
            <p className="eyebrow">DYLEMATY PRZEDSIĘBIORCY · WYNIKI Z DANYCH KRS</p>
            <h2>4 kluczowe pytania o strategię deweloperską</h2>
            <p style={{ margin: "4px 0 0", fontSize: "14px", color: "var(--muted)" }}>
              Odpowiedzi na podstawie wieloletnich sprawozdań {r.audit.selected_companies} aktywnych deweloperów.
            </p>
          </div>
        </div>

        {/* Plain Language Grid */}
        <div className="plain-questions-grid">
          {primary.map((q) => {
            const meta = questionMeta[q.id] || {
              icon: "❓",
              humanTitle: q.question,
              verdict: "depends" as const,
              verdictLabel: "ZALEŻNOŚĆ STATYSTYCZNA",
              simpleAnswer: "Model pokazuje zależność w danych; nie jest to bezwzględny dowód przyczynowy.",
              businessAdvice: "Sprawdź wpływ na specyfikę swojej firmy.",
            };

            const c = q.coefficients?.[q.exposure];
            const alternate = robust.find((x) => x.id === q.id)?.coefficients?.[q.exposure];

            return (
              <div key={q.id} className="plain-question-card">
                <div className="pq-header">
                  <span
                    className={`pq-badge ${
                      meta.verdict === "yes"
                        ? "pq-badge-yes"
                        : meta.verdict === "no"
                        ? "pq-badge-no"
                        : "pq-badge-depends"
                    }`}
                  >
                    {meta.verdictLabel}
                  </span>
                  <span className="term-chip">{q.exposure.replace("_", " ")}</span>
                </div>

                <h4>
                  {meta.icon} {meta.humanTitle}
                </h4>

                <p className="pq-answer">{meta.simpleAnswer}</p>

                <div className="pq-proof">
                  <strong>💡 Wskazówka biznesowa:</strong> {meta.businessAdvice}
                </div>

                {c && (
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", marginTop: "auto", paddingTop: "10px", borderTop: "1px solid #f1f5f9" }}>
                    <small style={{ color: "var(--muted)" }}>Efekt w danych KRS:</small>
                    <strong style={{ color: c.value > 0 ? "#15803d" : "#b91c1c" }}>
                      {impact(q, c.value)}
                    </strong>
                  </div>
                )}

                {showTechnical && c && (
                  <div style={{ background: "#f8fafc", padding: "10px", borderRadius: "8px", fontSize: "12px", color: "#64748b", marginTop: "8px" }}>
                    <p style={{ margin: "0 0 4px" }}>
                      Przedział {confidence}: {impact(q, c.lo)} do {impact(q, c.hi)} · {q.companies} firm · p: {p(c.p)}
                    </p>
                    {alternate && (
                      <p style={{ margin: 0 }}>
                        Po ograniczeniu skrajności (1–99%): {impact(q, alternate.value)}
                      </p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        <button
          type="button"
          className="text-button"
          style={{ fontSize: "13px", fontWeight: 600, color: "#235b4c", cursor: "pointer", marginTop: "12px" }}
          onClick={() => setShowTechnical(!showTechnical)}
        >
          {showTechnical ? "▲ Ukryj parametry modeli i p-value" : "▼ Pokaż współczynniki ekonometryczne i przedziały ufności"}
        </button>
      </section>

      {/* Stability comparison */}
      <section className="card">
        <div className="section-title">
          <div>
            <p className="eyebrow">SKALA A BEZPIECZEŃSTWO</p>
            <h2>Czy większe firmy deweloperskie są stabilniejsze?</h2>
            <p style={{ margin: "4px 0 0", fontSize: "14px", color: "var(--muted)" }}>
              Porównanie rocznych wahań zysku w zależności od wielkości majątku firmy.
            </p>
          </div>
        </div>

        <div className="stats">
          {Object.entries(r.stability).map(([name, s]) => (
            <div className="stat" key={name}>
              <span>{name} ({s.companies} firm)</span>
              <strong>{pct(s.median_roa_volatility)}</strong>
              <small>
                przeciętne roczne wahanie zysku (ROA)<br />
                zmienność marży operacyjnej: {pct(s.median_ebit_margin_volatility)}
              </small>
            </div>
          ))}
        </div>

        <div className="sim-takeaway-box" style={{ marginTop: "16px" }}>
          <span className="sim-takeaway-icon">🛡️</span>
          <div>
            <strong>Co oznacza ten wynik?</strong>
            <p style={{ margin: "4px 0 0" }}>
              Największe firmy deweloperskie mają mniejsze roczne skoki zysków niż małe spółki celowe. 
              Wynika to z dywersyfikacji — budują po kilka osiedli równolegle w różnych miastach, co uodparnia 
              je na lokalne przestoje i wahania popytu.
            </p>
          </div>
        </div>
      </section>

      {/* Limitations in accordion */}
      <details className="friendly-details">
        <summary>ℹ️ Założenia i ograniczenia statystyczne tego badania</summary>
        <div style={{ marginTop: "12px", fontSize: "13.5px", lineHeight: "1.6", color: "#475569" }}>
          {r.limitations.map((item) => (
            <p key={item}>• {item}</p>
          ))}
        </div>
      </details>
    </>
  );
}
