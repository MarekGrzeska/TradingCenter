import { Button } from "../ui/Button";
import { formatInstant } from "../ui/formatTime";
import { num, r, STATUS_LABEL, WITHOUT_COSTS_NOTE } from "./present";
import type { RunItem } from "./strategiesApi";

const day = (d: Date) => formatInstant(d.getTime() / 1000).slice(0, 10);

/** Runs, newest first — which of them the agent asked for included. With `strategyNames`, of several strategies. */
export function RunsPanel({
  runs,
  error,
  picked,
  onPick,
  onCancel,
  strategyNames,
}: {
  runs: readonly RunItem[];
  error: string | null;
  picked: number | null;
  onPick(id: number): void;
  /** Given, the list is of every strategy and names each run's. */
  strategyNames?: ReadonlyMap<number, string>;
  /** Says its own failure; the list only asks. */
  onCancel(id: number): Promise<void>;
}) {
  if (runs.length === 0) {
    return (
      <p className="text-sm text-ink-muted">
        {error ?? (strategyNames ? "Nie było jeszcze uruchomień." : "Ta strategia nie miała jeszcze uruchomień.")}
      </p>
    );
  }
  return (
    <table aria-label="Uruchomienia" className="w-full text-xs">
      <thead className="text-left text-ink-muted">
        <tr>
          <th className="py-1">#</th>
          {strategyNames && <th>Strategia</th>}
          <th>Stan</th>
          <th>Rew.</th>
          <th>Zakres</th>
          <th>Zlecił</th>
          <th className="text-right">Transakcje</th>
          <th className="text-right">Suma</th>
          <th className="text-right">Oczekiwana</th>
          <th className="text-right">Obsunięcie</th>
          <th className="text-right">Sharpe</th>
          <th />
        </tr>
      </thead>
      <tbody>
        {runs.map((run) => (
          <tr
            key={run.id}
            onClick={() => run.status === "done" && onPick(run.id)}
            className={`border-t border-border ${run.status === "done" ? "cursor-pointer hover:bg-panel" : ""} ${picked === run.id ? "bg-panel-strong" : ""}`}
          >
            <td className="py-1 text-ink">{run.id}</td>
            {strategyNames && <td className="text-ink">{strategyNames.get(run.strategyId) ?? `#${run.strategyId}`}</td>}
            <td className={run.status === "failed" ? "text-critical" : "text-ink-secondary"} title={run.reason ?? undefined}>
              {STATUS_LABEL[run.status] ?? run.status}
              {run.status === "failed" && run.reason ? ` — ${run.reason}` : ""}
              {run.headline?.withoutCosts && (
                <span title={WITHOUT_COSTS_NOTE} className="ml-1 rounded bg-warning-soft px-1 text-warning">
                  bez kosztów
                </span>
              )}
            </td>
            <td>{run.revision}</td>
            <td>
              {day(run.from)} – {day(run.to)}
            </td>
            <td>{run.requestedBy === "agent" ? "agent" : "operator"}</td>
            <td className="text-right">{num(run.headline?.trades)}</td>
            <td className="text-right">{r(run.headline?.totalR)}</td>
            <td className="text-right">{r(run.headline?.expectancyR)}</td>
            <td className="text-right">{r(run.headline?.maxDrawdownR)}</td>
            <td className="text-right">{num(run.headline?.sharpe)}</td>
            <td className="text-right">
              {(run.status === "queued" || run.status === "running") && (
                <Button
                  size="2xs"
                  tone="muted"
                  onClick={(e) => {
                    e.stopPropagation();
                    void onCancel(run.id);
                  }}
                >
                  Anuluj
                </Button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
