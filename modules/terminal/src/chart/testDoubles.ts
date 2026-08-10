import { vi } from "vitest";
import type { IndicatorSource, MarketDataSource } from "../data/source";
import type {
  Bar,
  IndicatorCatalogue,
  IndicatorCatalogueEntry,
  IndicatorResult,
  IndicatorSelection,
  IndicatorsResult,
  Resolution,
  StreamEvent,
} from "../data/types";

/** A chart's canvas cannot be asserted on, so every chart test runs against
 *  this stub instead of the real library — see design.md, "Testy tam, gdzie da
 *  się coś stwierdzić". */
export interface ChartStub {
  charts: FakeChart[];
  latest(): FakeChart;
  reset(): void;
}

export interface LogicalRange {
  from: number;
  to: number;
}

export interface FakeChart {
  removed: boolean;
  resized: Array<{ width: number; height: number }>;
  crosshairHandlers: Array<(param: unknown) => void>;
  series: FakeSeries[];
  /** Series removed with `chart.removeSeries()` — kept out of `series` above (which
   *  mirrors what is actually drawn) but not discarded, so a test can assert one
   *  was removed rather than only that it is gone. */
  removedSeries: FakeSeries[];
  fitContentCalls: number;
  /** Handlers the chart attached to the time scale, and the range they read.
   *  `pan()` is what a test uses to move the frame the way a drag would. */
  rangeHandlers: Array<(range: LogicalRange | null) => void>;
  visibleRange: LogicalRange | null;
  rangesSet: LogicalRange[];
  pan(range: LogicalRange): void;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

/** A wskaźnik line's own point shape — `value` absent (rather than `null`) is how
 *  `lightweight-charts` spells a whitespace gap, which is what `Chart.tsx` sends for
 *  an index with no computed value. */
export interface LinePoint {
  time: number;
  value?: number;
}

export type SeriesPoint = Candle | LinePoint;

export interface FakePriceLine {
  options: Record<string, unknown>;
  removed: boolean;
  applyOptions(options: Record<string, unknown>): void;
}

export interface FakeSeries {
  /** `"Candlestick"` or `"Line"` — read off the series-definition object the
   *  mocked `lightweight-charts` module exports, the same way the real
   *  `chart.addSeries(LineSeries, …)` call identifies its own kind. */
  type: string;
  /** The options the chart created this series with. */
  options: Record<string, unknown>;
  setDataCalls: SeriesPoint[][];
  updateCalls: SeriesPoint[];
  /** Whatever setData/update has left on screen. */
  data(): SeriesPoint[];
  setData(data: SeriesPoint[]): void;
  update(point: SeriesPoint): void;
  priceLines: FakePriceLine[];
  createPriceLine(options: Record<string, unknown>): FakePriceLine;
  removePriceLine(line: FakePriceLine): void;
  /** The one price line still on the series, if any. */
  priceLine(): FakePriceLine | undefined;
}

export function createChartStub(): ChartStub {
  const charts: FakeChart[] = [];
  return {
    charts,
    latest: () => charts[charts.length - 1],
    reset: () => {
      charts.length = 0;
    },
  };
}

export function makeFakeChart(): FakeChart {
  return {
    removed: false,
    resized: [],
    crosshairHandlers: [],
    series: [],
    removedSeries: [],
    fitContentCalls: 0,
    rangeHandlers: [],
    visibleRange: null,
    rangesSet: [],
    pan(range: LogicalRange) {
      this.visibleRange = range;
      for (const handler of [...this.rangeHandlers]) handler(range);
    },
  };
}

/** The slice of lightweight-charts' API that `Chart` actually calls, over a
 *  `FakeChart` the test can then read and drive. */
export function fakeChartApi(chart: FakeChart) {
  return {
    addSeries: (type: unknown, options: Record<string, unknown> = {}) => {
      // The mocked module exports `{ type: "Candlestick" }` / `{ type: "Line" }` in
      // place of the real series-definition objects — the same shape `Chart.tsx`
      // passes through unmodified, so reading it back here needs no separate map.
      const kind = (type as { type?: string } | undefined)?.type ?? "unknown";
      const series = makeFakeSeries(kind, options);
      chart.series.push(series);
      return series;
    },
    removeSeries: (series: FakeSeries) => {
      chart.series = chart.series.filter((existing) => existing !== series);
      chart.removedSeries.push(series);
    },
    remove: () => {
      chart.removed = true;
    },
    resize: (width: number, height: number) => chart.resized.push({ width, height }),
    timeScale: () => ({
      fitContent: () => chart.fitContentCalls++,
      getVisibleLogicalRange: () => chart.visibleRange,
      setVisibleLogicalRange: (range: LogicalRange) => {
        chart.rangesSet.push(range);
        // The real time scale notifies its subscribers about a range it was
        // told to take, exactly as it does about one the operator dragged to —
        // which is what makes a chart correcting its own frame able to trigger
        // itself. The fake has to do it too, or that loop cannot be tested.
        chart.pan(range);
      },
      subscribeVisibleLogicalRangeChange: (handler: (range: LogicalRange | null) => void) =>
        chart.rangeHandlers.push(handler),
      unsubscribeVisibleLogicalRangeChange: (handler: (range: LogicalRange | null) => void) => {
        chart.rangeHandlers = chart.rangeHandlers.filter((existing) => existing !== handler);
      },
    }),
    subscribeCrosshairMove: (handler: (param: unknown) => void) =>
      chart.crosshairHandlers.push(handler),
    unsubscribeCrosshairMove: (handler: (param: unknown) => void) => {
      chart.crosshairHandlers = chart.crosshairHandlers.filter((existing) => existing !== handler);
    },
  };
}

export function makeFakeSeries(
  type: string = "Candlestick",
  options: Record<string, unknown> = {},
): FakeSeries {
  let current: SeriesPoint[] = [];
  return {
    type,
    options,
    setDataCalls: [],
    updateCalls: [],
    data: () => current,
    setData(data) {
      this.setDataCalls.push(data);
      current = [...data];
    },
    update(point) {
      this.updateCalls.push(point);
      const index = current.findIndex((c) => c.time === point.time);
      if (index >= 0) current[index] = point;
      else current.push(point);
    },
    priceLines: [],
    createPriceLine(options) {
      const line: FakePriceLine = {
        options,
        removed: false,
        applyOptions(next) {
          this.options = { ...this.options, ...next };
        },
      };
      this.priceLines.push(line);
      return line;
    },
    removePriceLine(line) {
      line.removed = true;
    },
    priceLine() {
      return this.priceLines.find((line) => !line.removed);
    },
  };
}

/**
 * A source whose subscription the test drives message by message.
 *
 * The live edge arrives through `subscribe` — the opening snapshot included — so nothing
 * a chart draws today comes from a range read. `historyCalls` records the reads anyway,
 * because there is one legitimate reason for them and one illegitimate one: paging back
 * through older candles is fine, re-fetching the live edge is the seam growing back
 * (design.md, "Archiwum jest dla terminala jedynym źródłem świec i strumienia"). Every
 * range read here carries its bounds, so a test can tell the two apart.
 */
export class ControllableSource implements MarketDataSource {
  readonly parts = [
    {
      id: "archive",
      label: "market-data",
      whenUnreachable: "the candles on screen are stale",
      ping: vi.fn(async () => {}),
    },
  ];

  historyCalls: Array<{ symbol: string; resolution: Resolution; from: number; to: number }> = [];
  subscribeCalls: Array<{ symbol: string; resolution: Resolution }> = [];
  unsubscribeCount = 0;

  /** What successive range reads answer with; an exhausted queue answers with
   *  no candles, which is how "the archive has nothing older" looks. */
  historyPages: Bar[][] = [];
  /** Set to make every range read fail. */
  historyFailure: Error | null = null;
  /** While true, a range read hangs until `releaseHistory` — the only way to
   *  observe what a chart does *during* a read. */
  holdHistory = false;
  private pendingHistory: Array<(bars: Bar[]) => void> = [];

  /** Every subscription ever opened, in order, live or long since dropped —
   *  which is what lets a test aim a late message at a superseded one. */
  private subscriptions: Array<{
    sink: (event: StreamEvent) => void;
    live: boolean;
  }> = [];

  searchInstruments = vi.fn(async () => []);
  listInstruments = vi.fn(async () => ({ instruments: [], count: 0, truncated: false }));

  async history(request: {
    symbol: string;
    resolution: Resolution;
    from: number;
    to: number;
  }): Promise<Bar[]> {
    this.historyCalls.push({ ...request });
    if (this.historyFailure) throw this.historyFailure;
    if (this.holdHistory) {
      return new Promise<Bar[]>((resolve) => this.pendingHistory.push(resolve));
    }
    return this.historyPages.shift() ?? [];
  }

  /** Answers the oldest range read still hanging. */
  releaseHistory(bars: Bar[] = []): void {
    this.pendingHistory.shift()?.(bars);
  }

  subscribe(symbol: string, resolution: Resolution, sink: (event: StreamEvent) => void): () => void {
    this.subscribeCalls.push({ symbol, resolution });
    const subscription = { sink, live: true };
    this.subscriptions.push(subscription);
    return () => {
      this.unsubscribeCount++;
      subscription.live = false;
    };
  }

  /** To every live subscription — what the real hub does. */
  emit(event: StreamEvent): void {
    for (const subscription of [...this.subscriptions]) {
      if (subscription.live) subscription.sink(event);
    }
  }

  /** To one subscription by age (0 = the oldest), live or not. */
  emitTo(index: number, event: StreamEvent): void {
    this.subscriptions[index]?.sink(event);
  }

  /** The opening message of a subscription: the series, plus whichever period
   *  is still being built. */
  snapshot(bars: Bar[], forming: Bar | null = null): void {
    this.emit({ kind: "snapshot", bars, forming });
  }

  snapshotTo(index: number, bars: Bar[], forming: Bar | null = null): void {
    this.emitTo(index, { kind: "snapshot", bars, forming });
  }

  /** A subscription that failed instead of opening — a pair nobody chose to
   *  collect, or an archive that is not there. */
  refuse(message: string): void {
    this.emit({ kind: "error", message });
    this.emit({ kind: "status", state: "closed" });
  }
}

export function bar(time: number, close: number, forming = false, volume: number | null = null): Bar {
  return { time, open: close, high: close + 1, low: close - 1, close, volume, forming };
}

/** A catalogue entry with sane price-pane-line defaults — override only what a test
 *  actually cares about. */
export function indicatorEntry(
  overrides: Partial<IndicatorCatalogueEntry> = {},
): IndicatorCatalogueEntry {
  return {
    id: "ema",
    name: "Exponential Moving Average",
    aliases: [],
    group: "averages",
    output: "lines",
    params: [{ name: "period", type: "int", default: 20, min: 2, max: 5000 }],
    lines: [{ key: "ema", label: "EMA {period}", style: null }],
    render: { pane: "price", style: "line", scale: "price", autoscale: true, range: null, levels: [] },
    warmupKind: "decay",
    ...overrides,
  };
}

export function indicatorResult(overrides: Partial<IndicatorResult> = {}): IndicatorResult {
  return {
    id: "ema",
    params: { period: 20 },
    warmupBars: 210,
    anchoredAt: null,
    settled: true,
    lines: { ema: [] },
    markers: null,
    zones: null,
    levels: null,
    ...overrides,
  };
}

/**
 * A wskaźnik source the test drives directly — no HTTP, no fake server. `computeQueue`
 * answers successive `computeIndicators` calls in order; an exhausted queue answers with
 * an empty result, which is how "nothing computed yet" looks without a test having to
 * seed one for every call it does not care about.
 */
export class FakeIndicatorSource implements IndicatorSource {
  catalogueEntries: IndicatorCatalogueEntry[] = [];
  catalogueFailure: Error | null = null;

  computeCalls: Array<{
    symbol: string;
    resolution: Resolution;
    from: number;
    to: number;
    specs: IndicatorSelection[];
  }> = [];
  computeQueue: IndicatorsResult[] = [];
  computeFailure: Error | null = null;

  async indicatorCatalogue(): Promise<IndicatorCatalogue> {
    if (this.catalogueFailure) throw this.catalogueFailure;
    return { algorithmVersion: 1, indicators: this.catalogueEntries };
  }

  async computeIndicators(
    symbol: string,
    resolution: Resolution,
    from: number,
    to: number,
    specs: IndicatorSelection[],
  ): Promise<IndicatorsResult> {
    this.computeCalls.push({ symbol, resolution, from, to, specs });
    if (this.computeFailure) throw this.computeFailure;
    return (
      this.computeQueue.shift() ?? {
        symbol,
        resolution,
        derived: false,
        algorithmVersion: 1,
        times: [],
        results: [],
      }
    );
  }
}
