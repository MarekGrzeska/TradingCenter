import type { Summary } from "./strategiesApi";

/**
 * The document read back from the document alone (`strategies-documents`), under the editor — the check that the agent
 * understood the description, made before a backtest rather than after. Never shown as current when it is not.
 */
export function SummaryPanel({
  summary,
  valid,
  stale,
}: {
  summary: Summary | null;
  valid: boolean | null;
  stale: boolean;
}) {
  if (valid === false) {
    return (
      <Frame>
        <p className="text-sm text-ink-muted">Dokument ma problemy — streszczenie czeka na poprawny dokument.</p>
      </Frame>
    );
  }
  if (summary === null) {
    return (
      <Frame>
        <p className="text-sm text-ink-muted">{stale ? "Sprawdzam dokument…" : "Brak streszczenia."}</p>
      </Frame>
    );
  }
  return (
    <Frame>
      {stale && (
        <p className="mb-2 rounded bg-warning-soft px-2 py-1 text-xs text-warning">
          Streszczenie dotyczy poprzedniej wersji tekstu — bieżąca czeka na sprawdzenie.
        </p>
      )}
      <div className={stale ? "opacity-50" : undefined}>
        <h3 className="text-sm font-semibold text-ink">{summary.name}</h3>
        {(summary.hypothesis || summary.notes) && (
          <div className="mt-2 rounded border border-primary-line bg-primary-soft px-2 py-1 text-xs text-ink">
            <p className="font-semibold">Założenia autora</p>
            {summary.hypothesis && <p className="mt-1 whitespace-pre-wrap">Hipoteza: {summary.hypothesis}</p>}
            {summary.notes && <p className="mt-1 whitespace-pre-wrap">{summary.notes}</p>}
          </div>
        )}
        <div className="grid grid-cols-[repeat(auto-fill,minmax(16rem,1fr))] gap-x-4">
          {summary.sections.map((section) => (
            <section key={section.title} className="mt-3">
              <h4 className="text-xs font-semibold uppercase tracking-wide text-ink-muted">{section.title}</h4>
              <ul className="mt-1 space-y-1 text-sm text-ink-secondary">
                {section.lines.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      </div>
    </Frame>
  );
}

function Frame({ children }: { children: React.ReactNode }) {
  return (
    <aside aria-label="Streszczenie" className="max-h-72 shrink-0 overflow-y-auto rounded border border-border bg-panel p-3">
      {children}
    </aside>
  );
}
