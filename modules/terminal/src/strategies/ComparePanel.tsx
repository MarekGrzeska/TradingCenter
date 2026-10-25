import { num, pct, r } from "./present";
import type { ComparedRun } from "./strategiesApi";

type Metric = keyof Omit<ComparedRun, "run_id" | "strategy_id" | "revision" | "params">;

/** The report's own labels, in the report's order; no row marks a better value (`terminal-strategies`). */
const ROWS: readonly [string, Metric, (value: number | null | undefined) => string][] = [
  ["Transakcje", "trades", num],
  ["Zyskowne", "win_rate", pct],
  ["Oczekiwana", "expectancy_r", r],
  ["Suma", "total_r", r],
  ["Bez 5 najlepszych", "total_r_without_best_5", r],
  ["Profit factor", "profit_factor", num],
  ["Obsunięcie R", "max_drawdown_r", r],
  ["Obsunięcie %", "max_drawdown_pct", pct],
  ["Sharpe", "sharpe", num],
  ["Sortino", "sortino", num],
  ["Calmar", "calmar", num],
  ["Seria strat", "longest_losing_streak", num],
  ["Rozstrz. pesymistyczne", "pessimistic_resolutions", num],
];

const paramsOf = (run: ComparedRun) =>
  Object.entries(run.params)
    .map(([name, value]) => `${name}=${num(value)}`)
    .join(", ");

/** Runs side by side — a column each, a row per metric — or, when the package refused, every difference it named. */
export function ComparePanel({
  runs,
  refusal,
  strategyNames,
}: {
  runs: readonly ComparedRun[] | null;
  refusal: readonly string[] | null;
  strategyNames: ReadonlyMap<number, string>;
}) {
  if (refusal !== null) {
    return (
      <div role="alert" className="text-sm text-critical">
        <p>Tych uruchomień nie da się porównać:</p>
        <ul className="list-disc pl-5">
          {refusal.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      </div>
    );
  }
  if (runs === null) return null;
  return (
    <table aria-label="Porównanie" className="w-full text-xs">
      <thead className="text-left text-ink-muted">
        <tr>
          <th className="py-1" />
          {runs.map((run) => (
            <th key={run.run_id} className="text-right font-normal">
              <div className="text-ink">
                #{run.run_id} · {strategyNames.get(run.strategy_id) ?? `#${run.strategy_id}`}
              </div>
              <div>rew. {run.revision}</div>
              <div>{paramsOf(run)}</div>
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {ROWS.map(([label, key, format]) => (
          <tr key={key} className="border-t border-border">
            <td className="py-1 text-ink-secondary">{label}</td>
            {runs.map((run) => (
              <td key={run.run_id} className="text-right">
                {format(run[key])}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
