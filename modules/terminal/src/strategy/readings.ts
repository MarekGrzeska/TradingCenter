/**
 * The two blobs the platform keeps as JSON — the facts a decision stood on and a backtest's report — read into shapes a
 * view can lay out. Defensive on purpose: neither is in the contract's schema, and a snapshot written by last month's
 * image must still open today.
 */

export interface CandleReading {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
}

/** One declared fact, every line of it, oldest first — the order the platform stored. */
export interface FactReading {
  key: string;
  resolution: string;
  times: string[];
  lines: Record<string, (number | null)[]>;
}

export interface Snapshot {
  candles: CandleReading[];
  values: FactReading[];
}

/** One bar of one fact. `offset` counts back from the bar decided on, the way the rule
 *  language does: 0 is what a guard called "now", 1 the other half of a crossing. */
export interface ReadingRow {
  offset: number;
  time: string;
  values: Record<string, number | null>;
}

export interface ReportMetrics {
  trades: number;
  wins: number;
  winRate: number;
  expectancyR: number;
  totalR: number;
  profitFactor: number | null;
  maxDrawdownR: number;
  longestLosingStreak: number;
  averageBarsHeld: number;
  unresolved: number;
}

export interface Report {
  metrics: ReportMetrics | null;
  /** Why the bars that produced no trade were refused, counted by reason. */
  refusals: Record<string, number>;
  bars: number | null;
  strategyRevision: number | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function numberOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function numberOr(value: unknown, fallback: number): number {
  return numberOrNull(value) ?? fallback;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((one): one is string => typeof one === "string") : [];
}

export function readSnapshot(facts: Record<string, unknown>): Snapshot {
  const candles: CandleReading[] = [];
  if (Array.isArray(facts.candles)) {
    for (const raw of facts.candles) {
      if (!isRecord(raw) || typeof raw.time !== "string") continue;
      candles.push({
        time: raw.time,
        open: numberOr(raw.open, Number.NaN),
        high: numberOr(raw.high, Number.NaN),
        low: numberOr(raw.low, Number.NaN),
        close: numberOr(raw.close, Number.NaN),
      });
    }
  }

  const values: FactReading[] = [];
  if (isRecord(facts.values)) {
    for (const [key, raw] of Object.entries(facts.values)) {
      if (!isRecord(raw)) continue;
      const lines: Record<string, (number | null)[]> = {};
      if (isRecord(raw.lines)) {
        for (const [name, series] of Object.entries(raw.lines)) {
          if (Array.isArray(series)) lines[name] = series.map(numberOrNull);
        }
      }
      values.push({
        key: typeof raw.key === "string" ? raw.key : key,
        resolution: typeof raw.resolution === "string" ? raw.resolution : "",
        times: stringList(raw.times),
        lines,
      });
    }
  }

  return { candles, values };
}

/** The newest `count` bars of one fact, newest first. A line shorter than the times — an
 *  indicator still warming up — reads as `null` there, not as a number from another bar. */
export function latestReadings(fact: FactReading, count: number): ReadingRow[] {
  const rows: ReadingRow[] = [];
  const last = fact.times.length - 1;
  for (let offset = 0; offset < count && last - offset >= 0; offset += 1) {
    const index = last - offset;
    const values: Record<string, number | null> = {};
    for (const [name, series] of Object.entries(fact.lines)) {
      values[name] = series[index] ?? null;
    }
    rows.push({ offset, time: fact.times[index], values });
  }
  return rows;
}

/** The newest `count` candles, newest first, so they line up with the readings beside them. */
export function latestCandles(candles: CandleReading[], count: number): CandleReading[] {
  return candles.slice(Math.max(0, candles.length - count)).reverse();
}

export function readReport(report: Record<string, unknown>): Report {
  const raw = isRecord(report.metrics) ? report.metrics : null;
  const metrics: ReportMetrics | null =
    raw === null
      ? null
      : {
          trades: numberOr(raw.trades, 0),
          wins: numberOr(raw.wins, 0),
          winRate: numberOr(raw.win_rate, 0),
          expectancyR: numberOr(raw.expectancy_r, 0),
          totalR: numberOr(raw.total_r, 0),
          profitFactor: numberOrNull(raw.profit_factor),
          maxDrawdownR: numberOr(raw.max_drawdown_r, 0),
          longestLosingStreak: numberOr(raw.longest_losing_streak, 0),
          averageBarsHeld: numberOr(raw.average_bars_held, 0),
          unresolved: numberOr(raw.unresolved, 0),
        };

  const refusals: Record<string, number> = {};
  if (isRecord(report.refusals)) {
    for (const [reason, count] of Object.entries(report.refusals)) {
      const number = numberOrNull(count);
      if (number !== null) refusals[reason] = number;
    }
  }

  return {
    metrics,
    refusals,
    bars: numberOrNull(report.bars),
    strategyRevision: numberOrNull(report.strategy_revision),
  };
}
