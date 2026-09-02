import { useRead } from "../data/query";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { formatBar } from "./decisionFormat";
import { readReport } from "./readings";
import type { BacktestRun, StrategyApi } from "./strategyApi";

/**
 * Saved reports, read and never started: a run over years of candles is minutes of work, and a button would make that
 * something to trigger by accident. **The cost model is a column** — a number without it is not a result.
 */

const NO_RUNS: BacktestRun[] = [];

function formatDay(at: Date): string {
  return at.toLocaleDateString(undefined, { year: "numeric", month: "2-digit", day: "2-digit" });
}

function formatParams(params: Record<string, number>): string {
  const entries = Object.entries(params);
  return entries.length === 0 ? "domyślne" : entries.map(([name, value]) => `${name}=${value}`).join(", ");
}

/** The three the module knows, named the way an operator looks them up; anything else it
 *  stored travels too, so a cost model this screen has not heard of is still shown. */
function formatCosts(costs: Record<string, number>): string {
  const known: Record<string, string> = {
    spread: "spread",
    slippage: "poślizg",
    commission_r: "prowizja",
  };
  const parts = Object.entries(costs).map(([name, value]) =>
    name === "commission_r" ? `${known[name]} ${value}R` : `${known[name] ?? name} ${value}`,
  );
  return parts.length === 0 ? "bez modelu kosztów" : parts.join(" · ");
}

export function BacktestsPanel({
  client,
  strategyId,
}: {
  client: StrategyApi;
  /** The chip chosen above; `null` is every strategy. */
  strategyId: string | null;
}) {
  const runs = useRead<BacktestRun[]>({
    key: ["strategy", "backtests", strategyId],
    read: (signal) => client.listBacktests(signal, strategyId ?? undefined),
    initial: NO_RUNS,
    fallbackMessage: "nie udało się odczytać raportów",
  });

  return (
    <section className="flex flex-col gap-2" data-testid="backtests">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-xs font-semibold text-ink-secondary">Raporty backtestu</h2>
        <span className="text-xs text-ink-faint">
          przebieg jest komendą w module, nie przyciskiem tutaj · wyniki w R, z modelem kosztów
        </span>
      </header>

      {runs.error !== null && (
        <UnreachableNotice onRetry={runs.reload}>{runs.error}</UnreachableNotice>
      )}

      {runs.status === "ready" && runs.value.length === 0 && (
        <p className="text-xs text-ink-muted" data-testid="no-backtests">
          Jeszcze żadnego raportu. Po przebiegu uruchomionym komendą w module strategii raport
          pojawi się tutaj — z kosztami, parametrami i zakresem, na których powstał.
        </p>
      )}

      {runs.value.length > 0 && (
        <div className="overflow-auto">
          <table className="decisions">
            <thead>
              <tr>
                <th>uruchomiono</th>
                <th>strategia</th>
                <th>instrument</th>
                <th>zakres</th>
                <th>parametry</th>
                <th>koszty</th>
                <th>transakcje</th>
                <th>trafność</th>
                <th>oczekiwana</th>
                <th>suma</th>
                <th>obsunięcie</th>
                <th>nierozstrzygnięte</th>
              </tr>
            </thead>
            <tbody>
              {runs.value.map((run) => {
                const report = readReport(run.report);
                const metrics = report.metrics;
                return (
                  <tr key={run.id} className="decision" data-testid="backtest-row">
                    <td className="decision-bar">{formatBar(run.ranAt)}</td>
                    <td className="decision-symbol">
                      {run.strategyId}
                      {report.strategyRevision !== null && (
                        <span className="ml-1 text-ink-faint">@{report.strategyRevision}</span>
                      )}
                    </td>
                    <td className="decision-bar">
                      {run.symbol} <span className="text-ink-faint">{run.resolution}</span>
                    </td>
                    <td className="decision-bar">
                      {formatDay(run.rangeFrom)} – {formatDay(run.rangeTo)}
                      {report.bars !== null && (
                        <span className="ml-1 text-ink-faint">{report.bars} świec</span>
                      )}
                    </td>
                    <td title={formatParams(run.params)}>{formatParams(run.params)}</td>
                    <td className="decision-bar">{formatCosts(run.costs)}</td>
                    {metrics === null ? (
                      <td colSpan={6} className="text-ink-faint">
                        raport bez metryk
                      </td>
                    ) : (
                      <>
                        <td>
                          {metrics.trades}
                          <span className="ml-1 text-ink-faint">({metrics.wins} zysk.)</span>
                        </td>
                        <td>{(metrics.winRate * 100).toFixed(0)}%</td>
                        <td>{metrics.expectancyR.toFixed(2)}R</td>
                        <td>{metrics.totalR.toFixed(2)}R</td>
                        <td>{metrics.maxDrawdownR.toFixed(2)}R</td>
                        <td>{metrics.unresolved}</td>
                      </>
                    )}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
