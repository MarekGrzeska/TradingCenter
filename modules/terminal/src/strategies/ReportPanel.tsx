import { useMemo, useState } from "react";
import { Chart, type ChartLevel, type ChartMark } from "../chart/Chart";
import { RESOLUTION_SECONDS } from "../chart/chartWindow";
import { readChartColors } from "../chart/theme";
import { marketData } from "../data/marketData";
import { messageOf, useRead } from "../data/query";
import type { ChartFocusRequest, Resolution } from "../data/types";
import { Button } from "../ui/Button";
import { UnreachableNotice } from "../ui/UnreachableNotice";
import { formatInstant } from "../ui/formatTime";
import { barStart } from "./curve";
import { EquityChart } from "./EquityChart";
import { COSTS_SOURCE_LABEL, EXIT_LABEL, num, pct, r, WITHOUT_COSTS_NOTE } from "./present";
import type { Report, Run, StrategiesApi, Trade } from "./strategiesApi";

const PAGE = 200;
const at = (d: Date) => formatInstant(d.getTime() / 1000);

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded bg-panel px-2 py-1">
      <dt className="text-[10px] uppercase tracking-wide text-ink-muted">{label}</dt>
      <dd className="text-sm text-ink">{value}</dd>
    </div>
  );
}

/** Every number `strategies-reports` lists — and nothing that judges them. Empty is a dash, never zero. */
function Metrics({ report }: { report: Report }) {
  const random = report.benchmarks.random_entry;
  const hold = report.benchmarks.buy_and_hold;
  return (
    <dl className="grid grid-cols-[repeat(auto-fill,minmax(9rem,1fr))] gap-2">
      <Metric label="Transakcje" value={num(report.trades)} />
      <Metric label="Zyskowne" value={pct(report.win_rate)} />
      <Metric label="Oczekiwana" value={r(report.expectancy_r)} />
      <Metric label="Oczekiwana %" value={pct(report.expectancy_pct)} />
      <Metric label="Suma" value={r(report.total_r)} />
      <Metric label="Bez 5 najlepszych" value={r(report.total_r_without_best_5)} />
      <Metric label="Profit factor" value={num(report.profit_factor)} />
      <Metric label="Obsunięcie R" value={r(report.max_drawdown_r)} />
      <Metric label="Obsunięcie %" value={pct(report.max_drawdown_pct)} />
      <Metric label="Najgłębsza strata otwarta" value={pct(report.worst_mae_pct)} />
      <Metric label="Sharpe" value={num(report.sharpe)} />
      <Metric label="Sortino" value={num(report.sortino)} />
      <Metric label="Calmar" value={num(report.calmar)} />
      <Metric label="Zwrot" value={pct(report.return_pct)} />
      <Metric label="Zwrot roczny" value={pct(report.annual_return_pct)} />
      <Metric label="Seria strat" value={num(report.longest_losing_streak)} />
      <Metric label="Świece w pozycji" value={num(report.average_bars_held)} />
      <Metric label="Ekspozycja" value={pct(report.exposure)} />
      <Metric label="Rozstrz. pesymistyczne" value={num(report.pessimistic_resolutions)} />
      <Metric label="Koszt spreadu" value={num(report.costs.spread)} />
      <Metric label="Koszt poślizgu" value={num(report.costs.slippage)} />
      <Metric label="Finansowanie" value={num(report.costs.financing)} />
      <Metric label="Kup i trzymaj" value={pct(hold?.return_pct)} />
      {random && "median_total_r" in random ? (
        <Metric
          label={`Losowe wejście ×${random.repetitions}`}
          value={`${r(random.median_total_r)} (${r(random.p5_total_r)} … ${r(random.p95_total_r)}) · ${pct(random.median_return_pct)} (${pct(random.p5_return_pct)} … ${pct(random.p95_return_pct)})`}
        />
      ) : (
        <Metric label="Losowe wejście" value={random && "skipped" in random ? random.skipped : "—"} />
      )}
    </dl>
  );
}

/** Gained or not by money, which a trade without a stop has as well as one with. */
const gained = (t: Trade) => t.resultMoney >= 0;
const result = (t: Trade) => (t.resultR !== null ? r(t.resultR) : pct(t.resultPct));

function marksOf(trades: readonly Trade[], barSeconds: number, up: string, down: string): ChartMark[] {
  const marks = trades.flatMap((t): ChartMark[] => [
    {
      time: barStart(t.entryTime.getTime() / 1000, barSeconds),
      position: t.side === "long" ? "belowBar" : "aboveBar",
      shape: t.side === "long" ? "arrowUp" : "arrowDown",
      color: t.side === "long" ? up : down,
      text: `#${t.seq}`,
    },
    {
      time: barStart(t.exitTime.getTime() / 1000, barSeconds),
      position: t.side === "long" ? "aboveBar" : "belowBar",
      shape: "circle",
      color: gained(t) ? up : down,
      text: result(t),
    },
  ]);
  // The library draws marks in time order and drops a list that is not.
  return marks.sort((a, b) => a.time - b.time);
}

/** A run's report: its numbers, the curve its drawdown was measured on, its trades, and those trades on the price chart. */
export function ReportPanel({ api, runId, symbol, timeframe }: { api: StrategiesApi; runId: number; symbol: string; timeframe: string }) {
  const [offset, setOffset] = useState(0);
  const [picked, setPicked] = useState<Trade | null>(null);
  const [focus, setFocus] = useState<ChartFocusRequest | null>(null);
  const [downloadFailure, setDownloadFailure] = useState<string | null>(null);
  const resolution = timeframe as Resolution;
  const barSeconds = RESOLUTION_SECONDS[resolution] ?? 3600;

  const run = useRead<Run | null>({
    key: ["strategies", "run", runId],
    read: (s) => api.run(runId, s),
    initial: null,
    fallbackMessage: "nie udało się wczytać raportu",
  });
  const page = useRead<{ total: number; trades: Trade[] }>({
    key: ["strategies", "run", runId, "trades", offset],
    read: (s) => api.trades(runId, offset, PAGE, s),
    initial: { total: 0, trades: [] },
    fallbackMessage: "nie udało się wczytać transakcji",
  });

  const colors = useMemo(() => readChartColors(), []);
  const marks = useMemo(() => marksOf(page.value.trades, barSeconds, colors.up, colors.down), [page.value.trades, barSeconds, colors]);
  const levels = useMemo<ChartLevel[]>(
    () =>
      picked === null
        ? []
        : [
            { price: picked.entryPrice, color: colors.ink, title: `wejście #${picked.seq}` },
            { price: picked.exitPrice, color: gained(picked) ? colors.up : colors.down, title: "wyjście" },
            ...(picked.initialStop === null ? [] : [{ price: picked.initialStop, color: colors.down, title: "stop" }]),
          ],
    [picked, colors],
  );

  async function download() {
    setDownloadFailure(null);
    try {
      const file = await api.downloadTrades(runId, new AbortController().signal);
      const link = document.createElement("a");
      link.href = URL.createObjectURL(file);
      link.download = `run-${runId}-trades.csv`;
      link.click();
      URL.revokeObjectURL(link.href);
    } catch (cause: unknown) {
      setDownloadFailure(messageOf(cause, "nie udało się pobrać transakcji"));
    }
  }

  function pick(trade: Trade) {
    setPicked(trade);
    const pad = barSeconds * 20;
    setFocus({
      from: barStart(trade.entryTime.getTime() / 1000, barSeconds) - pad,
      to: barStart(trade.exitTime.getTime() / 1000, barSeconds) + pad,
      around: null,
      bars: null,
      lastBars: null,
    });
  }

  if (run.error !== null) return <UnreachableNotice onRetry={run.reload}>{run.error}</UnreachableNotice>;
  const found = run.value;
  if (found === null || found.report === null) return <p className="text-sm text-ink-muted">Wczytuję raport…</p>;
  const report = found.report;
  const provenance = found.provenance ?? {};
  const capital = Number((found.request as { capital?: number }).capital ?? 10_000);

  return (
    <div className="flex flex-col gap-3">
      <p className="text-xs text-ink-faint">
        Uruchomienie {found.id} · rewizja {found.revision} ({String(provenance.content_hash ?? "").slice(0, 12)}) · silnik{" "}
        {found.engineVersion ?? "—"} · ziarno {String((found.request as { seed?: number }).seed ?? "—")} · {at(found.from)} –{" "}
        {at(found.to)} · koszty {COSTS_SOURCE_LABEL[report.costs_source]}
        {report.costs_fetched_at ? `, pobrane ${at(new Date(report.costs_fetched_at))}` : ""}{" "}
        {JSON.stringify((found.request as { costs?: unknown }).costs)}
        {report.margin_factor != null ? ` · depozyt ${pct(report.margin_factor)}` : ""} · {report.annualisation}
      </p>
      {report.without_costs && (
        <p role="note" className="rounded bg-warning-soft px-3 py-1 text-sm text-warning">
          Uruchomienie {WITHOUT_COSTS_NOTE}.
        </p>
      )}
      {report.no_trades && <p className="text-sm text-ink-secondary">W tym zakresie strategia nie otworzyła żadnej pozycji.</p>}
      <Metrics report={report} />

      <section>
        <h3 className="mb-1 text-sm font-semibold text-ink">Kapitał dzienny i obsunięcie</h3>
        {report.equity ? (
          <EquityChart equity={report.equity} capital={capital} />
        ) : (
          <p className="text-sm text-ink-muted">
            To uruchomienie pochodzi z wersji silnika, która nie zapisywała krzywej kapitału — liczby powyżej są pełne.
          </p>
        )}
      </section>

      {page.value.total > 0 && (
        <section className="flex flex-col gap-2">
          <h3 className="text-sm font-semibold text-ink">Transakcje na wykresie {symbol}</h3>
          <div className="h-80">
            <Chart
              source={marketData}
              symbol={symbol}
              resolution={resolution}
              onResolutionChange={() => {}}
              resolutions={[resolution]}
              focusRequest={focus}
              onFocusRequestSettled={() => setFocus(null)}
              marks={marks}
              levels={levels}
            />
          </div>
          <div className="flex items-center gap-2 text-xs text-ink-muted">
            Transakcje {offset + 1}–{Math.min(offset + PAGE, page.value.total)} z {page.value.total}
            <Button size="2xs" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
              ‹
            </Button>
            <Button size="2xs" disabled={offset + PAGE >= page.value.total} onClick={() => setOffset(offset + PAGE)}>
              ›
            </Button>
            <Button size="2xs" tone="muted" onClick={() => void download()}>
              Pobierz transakcje (CSV)
            </Button>
          </div>
          {downloadFailure !== null && (
            <p role="alert" className="text-xs text-critical">
              {downloadFailure}
            </p>
          )}
          <table aria-label="Transakcje" className="w-full text-xs">
            <thead className="text-left text-ink-muted">
              <tr>
                <th>#</th>
                <th>Strona</th>
                <th>Wejście</th>
                <th>Wyjście</th>
                <th className="text-right">Wynik</th>
                <th className="text-right">Wynik %</th>
                <th className="text-right">Najgłębsza strata</th>
                <th>Przyczyna wyjścia</th>
                <th>Koszty</th>
              </tr>
            </thead>
            <tbody>
              {page.value.trades.map((t) => (
                <tr
                  key={t.seq}
                  onClick={() => pick(t)}
                  className={`cursor-pointer border-t border-border hover:bg-panel ${picked?.seq === t.seq ? "bg-panel-strong" : ""}`}
                >
                  <td className="py-1">{t.seq}</td>
                  <td>{t.side}</td>
                  <td>
                    {at(t.entryTime)} @ {num(t.entryPrice)}
                  </td>
                  <td>
                    {at(t.exitTime)} @ {num(t.exitPrice)}
                  </td>
                  <td className={`text-right ${gained(t) ? "text-up" : "text-down"}`}>{r(t.resultR)}</td>
                  <td className={`text-right ${gained(t) ? "text-up" : "text-down"}`}>{pct(t.resultPct)}</td>
                  <td className="text-right">{pct(t.maePct)}</td>
                  <td>
                    {EXIT_LABEL[t.exitReason] ?? t.exitReason}
                    {t.pessimistic && <span title="minuta mieściła dwa zdarzenia; rozstrzygnięto przeciw strategii"> · pesymistycznie</span>}
                  </td>
                  <td>
                    {Object.entries(t.costs)
                      .map(([k, v]) => `${k} ${num(v)}`)
                      .join(", ")}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
