import { useRead } from "../data/query";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import type { DecisionDetail as Detail, ParameterSet, StrategyApi } from "./strategyApi";

/**
 * What the decision stood on, read back as the platform stored it: the readings are the ones taken on that bar, not
 * today's. The parameter set is looked up by id rather than assumed to be the watch's current one.
 */

const NO_SETS: ParameterSet[] = [];

function formatValue(value: unknown): string {
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : value.toFixed(4);
  if (value === null || value === undefined) return "—";
  return typeof value === "string" ? value : JSON.stringify(value);
}

function Pairs({ entries, testId }: { entries: [string, unknown][]; testId: string }) {
  if (entries.length === 0) return <p className="text-xs text-ink-faint">brak</p>;
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-0.5 text-xs" data-testid={testId}>
      {entries.map(([key, value]) => (
        <div key={key} className="contents">
          <dt className="text-ink-muted">{key}</dt>
          <dd className="font-mono break-all">{formatValue(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

export function DecisionDetail({
  client,
  decisionId,
  strategyId,
  onClose,
}: {
  client: StrategyApi;
  decisionId: number;
  strategyId: string;
  onClose: () => void;
}) {
  const detail = useRead<Detail | null>({
    key: ["strategy", "decision", decisionId],
    read: (signal) => client.readDecision(decisionId, signal),
    initial: null,
    fallbackMessage: "nie udało się odczytać decyzji",
  });
  const sets = useRead<ParameterSet[]>({
    key: ["strategy", "parameter-sets", strategyId],
    read: (signal) => client.listParameterSets(signal, strategyId),
    initial: NO_SETS,
    fallbackMessage: "nie udało się odczytać zestawów parametrów",
  });

  const decision = detail.value;
  const set = decision === null ? undefined : sets.value.find((s) => s.id === decision.parameterSetId);
  const isTrade = decision?.action === "trade";

  return (
    <aside className="flex flex-col gap-3 rounded border border-border p-3" data-testid="decision-detail">
      <header className="flex items-center gap-2">
        <h2 className="text-sm font-semibold text-ink">Decyzja #{decisionId}</h2>
        <Button size="xs" tone="muted" className="ml-auto" onClick={onClose}>
          zamknij
        </Button>
      </header>

      {detail.error !== null && (
        <UnreachableNotice onRetry={detail.reload}>{detail.error}</UnreachableNotice>
      )}
      {detail.status === "loading" && <p className="text-xs text-ink-faint">Czytam decyzję…</p>}

      {decision !== null && (
        <>
          <p className="text-xs">
            <span className="text-ink-muted">powód: </span>
            {decision.reason ?? "—"}
          </p>

          {isTrade && (
            <Pairs
              testId="decision-levels"
              entries={[
                ["kierunek", decision.direction],
                ["wejście", decision.entry],
                ["obrona", decision.stop],
                ["cel", decision.target],
                ["zysk / ryzyko", decision.rr === null ? null : `${decision.rr.toFixed(2)}R`],
                ["ocena", decision.score],
              ]}
            />
          )}

          <section className="flex flex-col gap-1">
            <h3 className="text-xs font-semibold text-ink">
              Parametry · zestaw #{decision.parameterSetId}
              {set !== undefined && <span className="text-ink-faint"> · wersja {set.version}</span>}
              {decision.strategyRevision !== null && (
                <span className="text-ink-faint"> · rewizja reguły @{decision.strategyRevision}</span>
              )}
            </h3>
            {set === undefined ? (
              <p className="text-xs text-ink-faint">
                {sets.status === "loading" ? "czytam…" : "zestawu nie ma na liście tej strategii"}
              </p>
            ) : (
              <Pairs testId="decision-params" entries={Object.entries(set.params)} />
            )}
          </section>

          <section className="flex flex-col gap-1">
            <h3 className="text-xs font-semibold text-ink">Odczyty z tej świecy</h3>
            <Pairs testId="decision-facts" entries={Object.entries(decision.facts)} />
          </section>

          {Object.keys(decision.features).length > 0 && (
            <section className="flex flex-col gap-1">
              <h3 className="text-xs font-semibold text-ink">Cechy setupu</h3>
              <Pairs testId="decision-features" entries={Object.entries(decision.features)} />
            </section>
          )}
        </>
      )}
    </aside>
  );
}
