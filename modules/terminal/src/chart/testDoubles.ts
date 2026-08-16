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
  /** Handlers `chart.subscribeClick` attached. `click()` is what a test uses to aim a
   *  pointer at an object the way the real chart does — with whatever its own `hitTest`
   *  answered already resolved into `hoveredObjectId`. */
  clickHandlers: Array<(param: unknown) => void>;
  click(param: { hoveredObjectId?: unknown; point?: { x: number; y: number } }): void;
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
  /** What `timeScale().setVisibleRange({from, to})` was called with — the time-based
   *  sibling of `rangesSet`, used for a `from`/`to` focus rather than an `around`/`bars`
   *  or `lastBars` one (both of which go through the logical-range call above). */
  timeRangesSet: Array<{ from: number; to: number }>;
  pan(range: LogicalRange): void;
  /** Index 0 always exists — the price pane `createChart` makes implicitly, the
   *  same one the real library never asks anyone to create by hand. Every later
   *  entry is one `chart.addPane()` call; a removed pane is spliced out, same as
   *  the real chart re-indexing the ones after it. */
  panesList: FakePane[];
}

export interface FakePane {
  stretchFactor: number;
  setStretchFactor(factor: number): void;
  /** A live lookup, never a stored number — `removePane` re-indexes every pane
   *  after the one it removes, and a cached index would go stale exactly the way
   *  `Chart.tsx` must not let its own `paneIndex()` calls go stale. */
  paneIndex(): number;
  /** What `chart.addPane()`'s own argument set — mirrors the real
   *  `IPaneApi.preserveEmptyPane()`. `false` (the real library's own default)
   *  is what makes `removeSeries` below delete a pane whose last series just
   *  left, the exact behaviour that raced `Chart.tsx`'s own explicit
   *  `removePane` and threw until `addPane(true)` opted out of it. */
  preserveEmptyPane: boolean;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

/** An indicator line's own point shape — `value` absent (rather than `null`) is how
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

/** What `createSeriesMarkers(series, …)` hands back — task 3.8. One per series;
 *  `Chart.tsx` keeps its own map from (indicator, params) to the plugin instead
 *  of asking the series for it, so this only needs to record the last call. */
export interface FakeMarkerPlugin {
  series: FakeSeries;
  markers: unknown[];
  detached: boolean;
  setMarkers(markers: unknown[]): void;
  detach(): void;
}

export interface FakeSeries {
  /** `"Candlestick"`, `"Line"` or `"Histogram"` — read off the series-definition
   *  object the mocked `lightweight-charts` module exports, the same way the
   *  real `chart.addSeries(LineSeries, …)` call identifies its own kind. */
  type: string;
  /** The options the chart created this series with, plus whatever
   *  `applyOptions` has changed since — recolouring an instance goes that way. */
  options: Record<string, unknown>;
  applyOptions(options: Record<string, unknown>): void;
  /** The pane `addSeries`'s third argument put this series in, resolved once
   *  at creation — never restored to a bare number, so a later pane removal
   *  (this series' own or another's) is reflected the same live way the real
   *  `series.getPane().paneIndex()` would be. */
  pane: FakePane;
  /** Read live off `pane`, for a test that only cares about the number. */
  readonly paneIndex: number;
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
  /** Task 3.9's ray primitive attaches here — `RayPrimitive` itself is the real
   *  class, never mocked, so this only has to record what got attached. */
  primitives: unknown[];
  attachPrimitive(primitive: unknown): void;
  detachPrimitive(primitive: unknown): void;
  /** Every `createSeriesMarkers(series, …)` call made against this series —
   *  `Chart.tsx` keeps at most one live per (indicator, params), so a test
   *  reads the last one to see what is actually still on screen. */
  markerPlugins: FakeMarkerPlugin[];
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

function makeFakePane(panesList: FakePane[], preserveEmptyPane = false): FakePane {
  const pane: FakePane = {
    stretchFactor: 1,
    setStretchFactor(factor) {
      this.stretchFactor = factor;
    },
    paneIndex: () => panesList.indexOf(pane),
    preserveEmptyPane,
  };
  return pane;
}

export function makeFakeChart(): FakeChart {
  const panesList: FakePane[] = [];
  const chart: FakeChart = {
    removed: false,
    resized: [],
    crosshairHandlers: [],
    clickHandlers: [],
    click(param) {
      for (const handler of [...this.clickHandlers]) handler(param);
    },
    series: [],
    removedSeries: [],
    fitContentCalls: 0,
    rangeHandlers: [],
    visibleRange: null,
    rangesSet: [],
    timeRangesSet: [],
    pan(range: LogicalRange) {
      this.visibleRange = range;
      for (const handler of [...this.rangeHandlers]) handler(range);
    },
    panesList,
  };
  panesList.push(makeFakePane(panesList)); // the implicit price pane, index 0
  return chart;
}

/** The slice of lightweight-charts' API that `Chart` actually calls, over a
 *  `FakeChart` the test can then read and drive. */
export function fakeChartApi(chart: FakeChart) {
  return {
    addSeries: (type: unknown, options: Record<string, unknown> = {}, paneIndex = 0) => {
      // The mocked module exports `{ type: "Candlestick" }` / `{ type: "Line" }` in
      // place of the real series-definition objects — the same shape `Chart.tsx`
      // passes through unmodified, so reading it back here needs no separate map.
      const kind = (type as { type?: string } | undefined)?.type ?? "unknown";
      const pane = chart.panesList[paneIndex] ?? chart.panesList[0];
      const series = makeFakeSeries(kind, options, pane);
      chart.series.push(series);
      return series;
    },
    removeSeries: (series: FakeSeries) => {
      chart.series = chart.series.filter((existing) => existing !== series);
      chart.removedSeries.push(series);
      // The real chart's own default: a pane with no series left in it goes
      // too, unless it was created with `preserveEmptyPane: true`. Pane 0
      // (the price pane) is exempt in practice — the candlestick series
      // always occupies it — and exempt here explicitly, so a test can never
      // end up asserting against a chart with no price pane at all.
      const vacated = series.pane;
      if (vacated !== chart.panesList[0] && !vacated.preserveEmptyPane) {
        const stillOccupied = chart.series.some((s) => s.pane === vacated);
        if (!stillOccupied) {
          const index = chart.panesList.indexOf(vacated);
          if (index !== -1) chart.panesList.splice(index, 1);
        }
      }
    },
    addPane: (preserveEmptyPane = false) => {
      const pane = makeFakePane(chart.panesList, preserveEmptyPane);
      chart.panesList.push(pane);
      return pane;
    },
    removePane: (index: number) => {
      chart.panesList.splice(index, 1);
    },
    panes: () => chart.panesList,
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
      setVisibleRange: (range: { from: number; to: number }) => {
        chart.timeRangesSet.push(range);
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
    subscribeClick: (handler: (param: unknown) => void) => chart.clickHandlers.push(handler),
    unsubscribeClick: (handler: (param: unknown) => void) => {
      chart.clickHandlers = chart.clickHandlers.filter((existing) => existing !== handler);
    },
  };
}

export function makeFakeSeries(
  type: string = "Candlestick",
  options: Record<string, unknown> = {},
  pane: FakePane = makeFakePane([]),
): FakeSeries {
  let current: SeriesPoint[] = [];
  return {
    type,
    options,
    pane,
    get paneIndex() {
      return this.pane.paneIndex();
    },
    applyOptions(next) {
      this.options = { ...this.options, ...next };
    },
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
    primitives: [],
    attachPrimitive(primitive) {
      this.primitives.push(primitive);
    },
    detachPrimitive(primitive) {
      this.primitives = this.primitives.filter((existing) => existing !== primitive);
    },
    markerPlugins: [],
  };
}

/** The mocked module's `createSeriesMarkers` — one `FakeMarkerPlugin` per call,
 *  the same "new object each time, `Chart.tsx` keeps the reference" shape the
 *  real plugin API has. Recorded on the series too, so a test can find it
 *  without `Chart.tsx` having to hand the reference back. */
export function fakeCreateSeriesMarkers(series: FakeSeries, markers: unknown[] = []): FakeMarkerPlugin {
  const plugin: FakeMarkerPlugin = {
    series,
    markers: [...markers],
    detached: false,
    setMarkers(next) {
      this.markers = [...next];
    },
    detach() {
      this.detached = true;
    },
  };
  series.markerPlugins.push(plugin);
  return plugin;
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
    error: null,
    lines: { ema: [] },
    markers: null,
    zones: null,
    levels: null,
    ...overrides,
  };
}

/**
 * An indicator source the test drives directly — no HTTP, no fake server. `computeQueue`
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
