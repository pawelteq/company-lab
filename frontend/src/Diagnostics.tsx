import { useState } from "react";
import { useApi } from "./api";
import { Lineage, type Trace } from "./Lineage";

type CaseSummary = {
  rank: number;
  krs: string;
  name: string;
  origin_year: number;
  trigger_feature: string;
  trigger_year: number;
  trigger_value: number;
  small_denominators: number;
  coefficient_without_company: number | null;
  change_in_baseline_se: number | null;
};
type Summary = {
  id: string;
  studies: {
    id: string;
    title: string;
    primary_term: string;
    baseline_coefficient: number;
    cases: CaseSummary[];
  }[];
};
type Case = {
  krs: string;
  name: string;
  origin_year: number;
  variables: {
    variable: string;
    feature: string;
    year: number;
    value: number;
    lineage: Trace;
    denominators: {
      feature: string;
      year: number;
      value: number;
      p01: number;
      small_denominator_flag: boolean;
    }[];
  }[];
  sensitivity: unknown;
};
const fmt = (n: number | null | undefined) =>
  n == null
    ? "brak"
    : new Intl.NumberFormat("pl-PL", { maximumSignificantDigits: 5 }).format(n);

export function Diagnostics({ run }: { run: string }) {
  const versions = useApi<{ id: string; created_at: string }[]>(
    `/api/research/${run}/diagnostics`,
  );
  const [open, setOpen] = useState(false),
    [chosen, setChosen] = useState(""),
    [study, setStudy] = useState("R01"),
    [krs, setKrs] = useState("");
  const id = chosen || versions.data?.[0]?.id;
  const data = useApi<Summary>(open && id ? `/api/diagnostics/${id}` : null);
  const detail = useApi<Case>(
    open && id && krs ? `/api/diagnostics/${id}/cases/${study}/${krs}` : null,
  );
  const selected = data.data?.studies.find((s) => s.id === study);
  return (
    <section className="card diagnostic-card">
      <div className="section-title">
        <div>
          <p className="eyebrow">KONTROLA WRAŻLIWOŚCI</p>
          <h2>Czy pojedyncze firmy zmieniają wynik?</h2>
        </div>
        {!!versions.data?.length && (
          <button onClick={() => setOpen(!open)}>
            {open ? "Zwiń diagnostykę" : "Otwórz diagnostykę"}
          </button>
        )}
      </div>
      <p className="muted">
        Przegląd skrajnych wskaźników i małych mianowników. Osobne estymacje po
        pominięciu całej historii wybranej firmy.
      </p>
      {versions.loading && (
        <p role="status">Sprawdzanie dostępności diagnostyki…</p>
      )}
      {versions.error && <p role="alert">{versions.error}</p>}
      {versions.data?.length === 0 && (
        <p>Brak zapisanej diagnostyki dla tej wersji badania.</p>
      )}
      {open && (
        <>
          <div className="notice">
            <strong>Diagnostyka po estymacji.</strong> Pięć firm na badanie
            wybrano według skrajności zmiennych. To ograniczona lista do
            przeglądu, a nie ranking ryzyka ani pełny ranking wpływu. Oryginalne
            dane i wyniki pozostają zachowane.
          </div>
          <div className="toolbar">
            <select
              aria-label="Wersja diagnostyki"
              value={id}
              onChange={(e) => {
                setChosen(e.target.value);
                setKrs("");
              }}
            >
              {versions.data?.map((v) => (
                <option key={v.id} value={v.id}>
                  {new Date(v.created_at).toLocaleString("pl-PL")} ·{" "}
                  {v.id.slice(0, 8)}
                </option>
              ))}
            </select>
            <select
              aria-label="Badanie diagnostyczne"
              value={study}
              onChange={(e) => {
                setStudy(e.target.value);
                setKrs("");
              }}
            >
              {["R01", "R02", "R03", "R04"].map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          {data.loading && <p role="status">Pobieranie diagnostyki…</p>}
          {data.error && <p role="alert">{data.error}</p>}
          {selected && (
            <>
              <h3>{selected.title}</h3>
              <p>
                Parametr główny: <code>{selected.primary_term}</code>. Wartość
                bazowa: <strong>{fmt(selected.baseline_coefficient)}</strong>.
              </p>
              <div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie">
                <table>
                  <thead>
                    <tr>
                      <th>Firma / rok X</th>
                      <th>Skrajna zmienna</th>
                      <th>Małe mianowniki</th>
                      <th>Parametr bez firmy</th>
                      <th>Zmiana / bazowy SE</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {selected.cases.map((c) => (
                      <tr key={c.krs}>
                        <td>
                          {c.name}
                          <small>
                            KRS {c.krs} · {c.origin_year}
                          </small>
                        </td>
                        <td>
                          {c.trigger_feature}
                          <small>
                            {c.trigger_year}: {fmt(c.trigger_value)}
                          </small>
                        </td>
                        <td>{c.small_denominators}</td>
                        <td>{fmt(c.coefficient_without_company)}</td>
                        <td>{fmt(c.change_in_baseline_se)}</td>
                        <td>
                          <button onClick={() => setKrs(c.krs)}>
                            Przejrzyj {c.krs}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="muted">
                Zmiana / bazowy SE jest opisową skalą porównania, nie testem
                istotności. Mały mianownik oznacza dolny 1% dodatnich wartości
                odpowiedniego składnika w próbie. To wskazanie do weryfikacji,
                nie potwierdzony błąd.
              </p>
            </>
          )}
          {detail.loading && <p role="status">Pobieranie źródeł przypadku…</p>}
          {detail.error && <p role="alert">{detail.error}</p>}
          {detail.data && (
            <div className="diagnostic-detail">
              <div className="section-title">
                <h3>
                  Przypadek: {detail.data.name} · {detail.data.origin_year}
                </h3>
                <button onClick={() => setKrs("")}>Zamknij przypadek</button>
              </div>
              {detail.data.variables.map((v) => (
                <details key={v.variable}>
                  <summary>
                    {v.feature} ({v.year}): {fmt(v.value)}
                    {v.denominators.some((d) => d.small_denominator_flag)
                      ? " · mały mianownik"
                      : ""}
                  </summary>
                  {v.denominators.map((d) => (
                    <p key={d.feature + d.year}>
                      Mianownik {d.feature} ({d.year}):{" "}
                      <strong>{fmt(d.value)}</strong>. Próg p1: {fmt(d.p01)}.{" "}
                      {d.small_denominator_flag ? "Dolny 1% próby." : ""}
                    </p>
                  ))}
                  <Lineage trace={v.lineage} />
                </details>
              ))}
              <details>
                <summary>Pełna estymacja po pominięciu firmy</summary>
                <pre>{JSON.stringify(detail.data.sensitivity, null, 2)}</pre>
              </details>
            </div>
          )}
        </>
      )}
    </section>
  );
}
