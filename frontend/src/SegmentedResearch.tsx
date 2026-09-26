import { useState } from 'react';
import { useApi } from './api';

type Model = {
  group: string;
  horizon: number;
  exposure: string;
  outcome: string;
  variant: string;
  status: string;
  n: number;
  companies: number;
  q?: number;
  coefficients?: Record<string, { value: number; p: number; lo: number; hi: number }>;
};

type Report = {
  collection_id: string;
  id: string;
  panels: { group: string; companies: number; company_years: number }[];
  models: Model[];
  audit: Record<string, number>;
  exclusions: Record<string, number>;
};

const groups: Record<string, string> = {
  developer: 'Deweloperzy i spółki celowe (SPV)',
  contractor: 'Wykonawcy budowlani i usługi',
};

const number = (x: number | undefined, digits = 3) =>
  x == null
    ? '—'
    : x !== 0 && Math.abs(x) < 0.001
    ? x.toExponential(2)
    : x.toLocaleString('pl-PL', { maximumFractionDigits: digits });

const probability = (x: number | undefined) =>
  x == null ? '—' : x < 0.0001 ? '< 0,0001' : number(x, 4);

export function SegmentedResearch({ collection }: { collection: string }) {
  const state = useApi<Report>('/api/profiles/segmented-research');
  const [showAnalystTables, setShowAnalystTables] = useState(false);

  if (state.loading) return <p role="status">Wczytuję badania według nowej klasyfikacji…</p>;
  if (state.error) return <p className="notice" role="alert">{state.error}</p>;
  const data = state.data;
  if (!data || data.collection_id !== collection)
    return <p className="notice">Badanie nie obejmuje wybranego zbioru.</p>;

  const totalCompanies = data.panels.reduce((n, p) => n + p.companies, 0);

  return (
    <section className="research-report">
      {/* 1. Header with clear business questions */}
      <div className="research-heading">
        <div>
          <p className="eyebrow">BADANIA NAUKOWE · PANEL WIELOLETNI</p>
          <h1>Czy dług pomaga firmom zarabiać więcej w kolejnych latach?</h1>
          <p style={{ margin: '8px 0 0', fontSize: '16px', color: 'var(--muted)' }}>
            Przeanalizowaliśmy historię finansową <strong>{number(totalCompanies, 0)} firm</strong> podzielonych na 
            deweloperów oraz wykonawców budowlanych, sprawdzając ich wyniki po 1, 2 i 3 latach od zaciągnięcia długu.
          </p>
        </div>
        <div className="research-sample">
          <strong>{number(totalCompanies, 0)}</strong>
          <span>firm w panelu</span>
          <small>2 odrębne branże · zbadane po 1–3 latach</small>
        </div>
      </div>

      {/* 2. Executive Plain-Language Summary Grid */}
      <div className="plain-questions-grid" style={{ margin: '24px 0' }}>
        {/* Card 1: Deweloperzy */}
        <div className="plain-question-card" style={{ borderLeft: '4px solid #10b981' }}>
          <div className="pq-header">
            <span className="pq-badge pq-badge-depends">⚠️ TYLKO W BOOMIE</span>
            <span className="term-chip">Deweloperzy & SPV</span>
          </div>
          <h4>Czy deweloper zyskuje na kredycie?</h4>
          <p className="pq-answer">
            <strong>Zależy od fazy rynku.</strong> Dług pomaga deweloperom zarabiać więcej <strong>wyłącznie wtedy</strong>, 
            gdy popyt jest silny, a mieszkania szybko się sprzedają. W latach przestoju koszty odsetek obniżają zyski 
            w kolejnych 2–3 latach.
          </p>
          <p className="pq-proof">
            🎯 Wniosek: Kredyt nie jest „magiczną maszynką do zysku” — działa jak dźwignia, która mnoży zysk w dobrej koniunkturze, ale obciąża firmę w złej.
          </p>
        </div>

        {/* Card 2: Wykonawcy */}
        <div className="plain-question-card" style={{ borderLeft: '4px solid #ef4444' }}>
          <div className="pq-header">
            <span className="pq-badge pq-badge-no">❌ ZDECYDOWANIE NIE</span>
            <span className="term-chip">Wykonawcy & Usługi</span>
          </div>
          <h4>Czy firmy budowlane/wykonawcze powinny brać kredyty?</h4>
          <p className="pq-answer">
            <strong>Dane nie pokazują żadnych korzyści.</strong> U wykonawców budowlanych wyższy dług oprocentowany 
            <strong> nie przekłada się</strong> na wyższy zysk w kolejnych latach. Marże na pracach budowlanych są 
            zbyt niskie, by pokryć wysokie oprocentowanie bankowe.
          </p>
          <p className="pq-proof">
            🎯 Wniosek: Wykonawca na kredycie łatwo wpada w spiralę kosztów finansowych. Pożyczki powinny być tylko ostatecznością na płynność.
          </p>
        </div>

        {/* Card 3: Czas inwestycji */}
        <div className="plain-question-card" style={{ borderLeft: '4px solid #3b82f6' }}>
          <div className="pq-header">
            <span className="pq-badge pq-badge-depends">⏳ EFEKT OPÓŹNIENIA</span>
            <span className="term-chip">Horyzont 1–3 lata</span>
          </div>
          <h4>Co się dzieje po 1 roku, a co po 2–3 latach?</h4>
          <p className="pq-answer">
            W pierwszym roku (t+1) od wzięcia kredytu zyski firmy często <strong>spadają</strong> (ponosisz koszty 
            uruchomienia budowy i odsetki, a przychodów jeszcze nie ma). Dopiero po 2–3 latach (t+2, t+3), gdy budynek 
            zostaje oddany do użytku, pojawia się ewentualny zysk.
          </p>
          <p className="pq-proof">
            🎯 Wniosek: Pieniądze z kredytu deweloperskiego wymagają cierpliwości i bezpiecznej rezerwy na przetrwanie pierwszych 24 miesięcy.
          </p>
        </div>
      </div>

      {/* 3. Jargon Buster Section */}
      <div className="sim-takeaway-box" style={{ background: '#f0fdf4', borderColor: '#bbf7d0', margin: '20px 0' }}>
        <span className="sim-takeaway-icon">📖</span>
        <div>
          <strong style={{ color: '#166534' }}>Szybki słowniczek pojęć (bez skomplikowanych terminów):</strong>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '10px', marginTop: '8px' }}>
            <div>
              <strong>Dług oprocentowany / kapitał (D/E):</strong>
              <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#15803d' }}>
                Ile zł pożyczono z banku w stosunku do każdego 1 zł wkładu właścicieli.
              </p>
            </div>
            <div>
              <strong>Opóźnienie (t+1, t+2, t+3):</strong>
              <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#15803d' }}>
                Stan długu badamy dzisiaj, a zysk liczymy po roku, po 2 latach lub po 3 latach.
              </p>
            </div>
            <div>
              <strong>Punkty procentowe (p.p.):</strong>
              <p style={{ margin: '2px 0 0', fontSize: '13px', color: '#15803d' }}>
                Jeśli zysk wzrósł z 5% do 7%, to wzrósł o 2 punkty procentowe (p.p.).
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* 4. Detailed Findings for Each Panel Group */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', margin: '28px 0' }}>
        {data.panels.map((panel) => {
          const isDev = panel.group === 'developer';
          const modelsRaw = data.models.filter((m) => m.group === panel.group && m.variant === 'raw');

          return (
            <section className="card" key={panel.group}>
              <div className="section-title">
                <div>
                  <p className="eyebrow">{isDev ? 'SEGMENT 1' : 'SEGMENT 2'}</p>
                  <h2>{groups[panel.group]}</h2>
                  <p style={{ margin: '4px 0 0', fontSize: '14px', color: 'var(--muted)' }}>
                    Zbadano <strong>{number(panel.companies, 0)} firm</strong> i {number(panel.company_years, 0)} rocznych sprawozdań.
                  </p>
                </div>
                <span className="tag">{isDev ? 'Spółki deweloperskie' : 'Usługi & wykonawstwo'}</span>
              </div>

              {/* Simplified takeaway for this specific panel */}
              <div style={{ background: '#f8fafc', padding: '16px 20px', borderRadius: '10px', border: '1px solid #e2e8f0', marginBottom: '20px' }}>
                <strong>Główny wniosek dla tej grupy:</strong>
                <p style={{ margin: '4px 0 0', fontSize: '14px', color: '#334155' }}>
                  {isDev
                    ? 'Dla deweloperów pożyczki bankowe mogą zwiększać rentowność kapitału własnego (ROE) w horyzoncie 2–3 lat, ale tylko przy stabilnym popycie. Brak jest natomiast pewności, że dług podnosi rentowność całego majątku (ROA) — po odjęciu odsetek zysk często nie jest wyższy niż przy finansowaniu bez kredytu.'
                    : 'Dla wykonawców i usług budowlanych dane jednoznacznie pokazują, że kredyty oprocentowane nie przynoszą korzyści zyskowościowych w kolejnych latach. Branża budowlana działa na niskich marżach, przez co raty bankowe stają się bezpośrednim obciążeniem zmniejszającym rentowność.'}
                </p>
              </div>

              {/* Intuitive overview of horizons */}
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px', marginBottom: '20px' }}>
                {[1, 2, 3].map((h) => {
                  const mDebt = modelsRaw.find((m) => m.horizon === h && m.exposure === 'debt_equity');
                  const cDebt = mDebt?.coefficients?.debt_equity;
                  return (
                    <div key={h} style={{ background: '#fff', border: '1px solid #cbd5e1', borderRadius: '10px', padding: '14px' }}>
                      <span style={{ fontSize: '12px', fontWeight: 700, color: 'var(--muted)', textTransform: 'uppercase' }}>
                        Po {h} {h === 1 ? 'roku' : 'latach'} (t+{h})
                      </span>
                      <h4 style={{ margin: '6px 0 8px', fontSize: '15px' }}>
                        Wpływ długu na zysk
                      </h4>
                      <p style={{ margin: 0, fontSize: '13px', color: '#475569' }}>
                        {cDebt && cDebt.value > 0
                          ? `Dodatnia zależność (+${number(cDebt.value * 10)} p.p. na każde 10 p.p. długu)`
                          : cDebt && cDebt.value < 0
                          ? `Ujemna zależność (${number(cDebt.value * 10)} p.p. - spadek zysku)`
                          : 'Brak istotnego statystycznie wpływu'}
                      </p>
                    </div>
                  );
                })}
              </div>

              {/* Toggle to show full technical table for this group */}
              <button
                type="button"
                className="text-button"
                style={{ fontSize: '13px', fontWeight: 600, color: '#235b4c', cursor: 'pointer', textAlign: 'left', padding: 0 }}
                onClick={() => setShowAnalystTables(!showAnalystTables)}
              >
                {showAnalystTables ? '▲ Ukryj tabele ekonometryczne' : '▼ Pokaż szczegółową tabelę modeli OLS i p-value dla analityków'}
              </button>

              {showAnalystTables && (
                <div style={{ marginTop: '16px' }}>
                  <div className="table-scroll" tabIndex={0} role="region" aria-label={`Wyniki badania: ${groups[panel.group]}`}>
                    <table>
                      <thead>
                        <tr>
                          <th>Badany wskaźnik</th>
                          <th>Opóźnienie</th>
                          <th>Rodzaj zadłużenia</th>
                          <th>Liczba firm / par lat</th>
                          <th>Wpływ na zysk (+10 p.p. długu)</th>
                          <th>Przedział 90% ufności</th>
                          <th>Wartość p / q (korekta)</th>
                        </tr>
                      </thead>
                      <tbody>
                        {modelsRaw.map((m) => {
                          const c = m.coefficients?.[m.exposure];
                          return (
                            <tr key={[m.horizon, m.exposure, m.outcome].join('-')}>
                              <td><strong>{m.outcome.toUpperCase()}</strong></td>
                              <td>t+{m.horizon} ({m.horizon} {m.horizon === 1 ? 'rok' : 'lata'})</td>
                              <td>{m.exposure === 'debt_equity' ? 'Dług w banku / kapitał' : 'Wszystkie zobowiązania / aktywa'}</td>
                              <td>{number(m.companies, 0)} / {number(m.n, 0)}</td>
                              <td>
                                {c ? (
                                  <strong style={{ color: c.value > 0 ? '#15803d' : '#b91c1c' }}>
                                    {c.value > 0 ? '+' : ''}{number(c.value * 10)} p.p.
                                  </strong>
                                ) : (
                                  'Za mało danych'
                                )}
                              </td>
                              <td>{c ? `${number(c.lo * 10)} do ${number(c.hi * 10)} p.p.` : '—'}</td>
                              <td>{c ? `${probability(c.p)} / ${probability(m.q)}` : '—'}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <p className="muted" style={{ fontSize: '12px', marginTop: '8px' }}>
                    ROA i ROE obliczane są względem średnich aktywów lub kapitału. Model kontroluje wielkość aktywów oraz stałe różnice między firmami i latami.
                  </p>
                </div>
              )}
            </section>
          );
        })}
      </div>

      {/* 5. Methodological Notes in Accordion */}
      <details className="friendly-details">
        <summary>🔬 Metodologia naukowa, testy odporności i zasady doboru firm</summary>
        <div style={{ marginTop: '14px', fontSize: '13.5px', lineHeight: '1.6', color: '#475569' }}>
          <p>
            Badanie obejmuje firmy z co najmniej 3 pełnymi latami sprawozdawczymi w KRS. 
            Wskaźnik <strong>q</strong> oznacza korektę Benjamini–Hochberga uwzględniającą ryzyko przypadkowego 
            wykrycia zależności przy testowaniu wielu modeli jednocześnie. Próg istotności statystycznej ustalono na poziomie 10%.
          </p>
          <p>
            Wyniki zostały zweryfikowane również w wariancie z ograniczeniem wartości skrajnych (tzw. winsoryzacja 1–99 percentyl), 
            aby upewnić się, że pojedyncze gigantyczne firmy lub błędy w sprawozdaniach nie zniekształcają ogólnego wniosku.
          </p>
          <p style={{ marginTop: '12px' }}>
            Identyfikator wersji badania: <code>{data.id}</code>. 
            Możesz również <a href="/api/profiles/segmented-research" target="_blank" rel="noreferrer">pobrać surowy raport JSON ze wszystkimi parametrami</a>.
          </p>
        </div>
      </details>
    </section>
  );
}
