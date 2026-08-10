import { vi } from "vitest";
import type { MarketDataSource } from "../data/source";
import type { Bar, Resolution, StreamEvent } from "../data/types";

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

export interface FakePriceLine {
  options: Record<string, unknown>;
  removed: boolean;
  applyOptions(options: Record<string, unknown>): void;
}

export interface FakeSeries {
  /** The options the chart created this series with. */
  options: Record<string, unknown>;
  setDataCalls: Candle[][];
  updateCalls: Candle[];
  /** Whatever setData/update has left on screen. */
  data(): Candle[];
  setData(data: Candle[]): void;
  update(candle: Candle): void;
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
    addSeries: (_type: unknown, options: Record<string, unknown> = {}) => {
      const series = makeFakeSeries(options);
      chart.series.push(series);
      return series;
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

export function makeFakeSeries(options: Record<string, unknown> = {}): FakeSeries {
  let current: Candle[] = [];
  return {
    options,
    setDataCalls: [],
    updateCalls: [],
    data: () => current,
    setData(data) {
      this.setDataCalls.push(data);
      current = [...data];
    },
    update(candle) {
      this.updateCalls.push(candle);
      const index = current.findIndex((c) => c.time === candle.time);
      if (index >= 0) current[index] = candle;
      else current.push(candle);
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
