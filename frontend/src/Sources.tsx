import { useApi } from "./api";
type SourcesInfo = {
  provider: string;
  documentation_url: string;
  collection: { code: string; version: string }[];
  reference_audit: null | {
    files: number;
    companies: number;
    financial_records: number;
    representations: number;
    numeric_conflicts: number;
  };
};
export function Sources() {
  const state = useApi<SourcesInfo>("/api/sources");
  if (state.error)
    return (
      <div className="notice" role="alert">
        Informacja o źródłach: {state.error}
      </div>
    );
  if (!state.data) return null;
  const s = state.data;
  return (
    <section className="card">
      <div className="section-title">
        <div>
          <p className="eyebrow">ŹRÓDŁO I ZAKRES ZBIERANIA</p>
          <h2>Korzystamy z {s.provider}</h2>
        </div>
        <a
          className="text-button"
          href={s.documentation_url}
          target="_blank"
          rel="noreferrer"
        >
          Dokumentacja API ↗
        </a>
      </div>
      <p className="muted">
        Zbierane są firmy według głównej działalności w czterech grupach. Kod i
        wersja PKD są przechowywane razem; PKD samo nie potwierdza działalności
        deweloperskiej.
      </p>
      <div className="quality-list">
        {s.collection.map((c) => (
          <span className="tag" key={c.code}>
            {c.code} · PKD {c.version}
          </span>
        ))}
      </div>
      {s.reference_audit && (
        <p className="muted">
          Nowe pliki poglądowe: {s.reference_audit.files} pliki ·{" "}
          {s.reference_audit.companies} firma ·{" "}
          {s.reference_audit.financial_records} różnych rekordów finansowych. To
          próbka schematu, nie dodatkowe obserwacje w obecnym panelu.
        </p>
      )}
    </section>
  );
}
