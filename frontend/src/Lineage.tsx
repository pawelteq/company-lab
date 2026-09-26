type Node = {
  feature: string;
  year: number;
  value: number | null;
  reason: string | null;
  source?: {
    original_path: string;
    source_pointer: string;
    object_sha256: string;
    original_value: number | null;
  } | null;
  inputs?: Node[];
};
export type Trace = { lineage: Node; code_hash: string; dataset_id: string };
export function Lineage({ trace }: { trace: Trace }) {
  const leaves: Node[] = [];
  function visit(node: Node) {
    if (node.source || !node.inputs?.length) leaves.push(node);
    else node.inputs.forEach(visit);
  }
  visit(trace.lineage);
  return (
    <>
      <p>
        Wartość wynika z poniższych danych źródłowych. Każdy składnik odnosi się
        do konkretnego roku i pola w zachowanym pliku.
      </p>
      <div className="table-scroll" tabIndex={0} role="region" aria-label="Tabela danych — przewijanie w poziomie">
        <table>
          <thead>
            <tr>
              <th>Rok</th>
              <th>Składnik</th>
              <th>Wartość w źródle</th>
              <th>Plik i pole</th>
            </tr>
          </thead>
          <tbody>
            {leaves.map((n, i) => (
              <tr key={i}>
                <td>{n.year}</td>
                <td>{n.feature}</td>
                <td>{n.source?.original_value ?? n.reason ?? "Brak danych"}</td>
                <td>
                  {n.source ? (
                    <>
                      <span>{n.source.original_path}</span>
                      <small>{n.source.source_pointer}</small>
                    </>
                  ) : (
                    (n.reason ?? "Brak źródła")
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <details>
        <summary>Pełna definicja i identyfikatory źródeł</summary>
        <pre>{JSON.stringify(trace, null, 2)}</pre>
      </details>
    </>
  );
}
