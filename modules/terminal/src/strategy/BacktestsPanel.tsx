import { useRead } from "../data/query";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import type { BacktestRun, StrategyApi } from "./strategyApi";

/**
 * Reports, read and never started: a run over years of candles is minutes of work, and it is a command precisely so it
 * cannot be fired by a stray click. A report is shown with its costs and range beside the numbers, or not at all.
 */

const NO_RUNS: BacktestRun[] = [];

/** The metrics a run stores, in the order a reader asks about them, with how each is written. */
const METRICS: [key: string, label: string, format: (v: number) => string][] = [
  ["trades", "transakcje", (v) => String(v)],
  ["win_rate", "trafność", (v) => `${(v * 100).toFixed(0)}%`],
  ["expectancy_r", "oczekiwana", (v) => `${v >= 0 ? "+" : ""}${v.toFixed(3)}R`],
  ["total_r", "łącznie", (v) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}R`],
  ["profit_factor", "profit factor", (v) => v.toFixed(2)],
  ["max_drawdown_r", "maks. obsunięcie", (v) => `${v.toFixed(1)}R`],
  ["longest_losing_streak", "najdłuższa seria strat", (v) => String(v)],
  ["unresolved", "nierozstrzygnięte", (v) => String(v)],
];

function day(at: Date): string {
  return at.toISOString().slice(0, 10);
}

function listed(values: Record<string, unknown>): string {
  const entries = Object.entries(values);
  return entries.length === 0 ? "—" : entries.map(([k, v]) => `${k}=${String(v)}`).join(" · ");
}

function Report({ run }: { run: BacktestRun }) {
  const metrics = (run.report.metrics ?? {}) as Record<string, number | null>;
  const refusals = (run.report.refusals ?? {}) as Record<string, number>;
  const bars = run.report.bars as number | undefined;

  return (
    <li className="flex flex-col gap-2 rounded border border-border p-3" data-testid="backtest-report">
      <header className="flex flex-wrap items-baseline gap-2 text-xs">
        <span className="font-semibold text-ink">
          {run.strategyId} · {run.symbol} {run.resolution}
        </span>
        <span className="text-ink-muted">
          {day(run.rangeFrom)} → {day(run.rangeTo)}
        </span>
        <span className="ml-auto text-ink-faint">policzony {day(run.ranAt)}</span>
      </header>
      <p className="text-xs">
        <span className="text-ink-muted">koszty: </span>
        {listed(run.costs)}
      </p>
      <p className="text-xs">
        <span className="text-ink-muted">parametry: </span>
        {listed(run.params)}
      </p>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-0.5 text-xs">
        {METRICS.map(([key, label, format]) => {
          const value = metrics[key];
          return (
            <div key={key} className="contents">
              <dt className="text-ink-muted">{label}</dt>
              <dd className="font-mono">{typeof value === "number" ? format(value) : "—"}</dd>
            </div>
          );
        })}
      </dl>
      {bars !== undefined && (
        <p className="text-xs text-ink-faint">
          {bars} świec w zakresie · odmowy: {listed(refusals)}
        </p>
      )}
    </li>
  );
}

export function BacktestsPanel({
  client,
  strategyId,
}: {
  client: StrategyApi;
  strategyId: string | null;
}) {
  const runs = useRead<BacktestRun[]>({
    key: ["strategy", "backtests", strategyId],
    read: (signal) => client.listBacktests(signal, strategyId ?? undefined),
    initial: NO_RUNS,
    fallbackMessage: "nie udało się odczytać raportów backtestu",
  });

  return (
    <section className="flex flex-col gap-2" data-testid="backtests">
      <h2 className="text-sm font-semibold text-ink">Raporty backtestu</h2>
      {runs.error !== null && (
        <UnreachableNotice onRetry={runs.reload}>{runs.error}</UnreachableNotice>
      )}
      {runs.status === "ready" && runs.value.length === 0 && (
        <p className="text-xs text-ink-muted">
          Żadnego zachowanego raportu. Backtest uruchamia się komendą w module strategii
          (<code>python -m strategy.backtest --keep</code>), nie z tego ekranu.
        </p>
      )}
      {runs.value.length > 0 && (
        <ul className="flex flex-col gap-2">
          {runs.value.map((run) => (
            <Report key={run.id} run={run} />
          ))}
        </ul>
      )}
    </section>
  );
}
