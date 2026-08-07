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

export interface FakeChart {
  removed: boolean;
  resized: Array<{ width: number; height: number }>;
  crosshairHandlers: Array<(param: unknown) => void>;
  series: FakeSeries[];
  fitContentCalls: number;
}

export interface Candle {
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface FakeSeries {
  setDataCalls: Candle[][];
  updateCalls: Candle[];
  /** Whatever setData/update has left on screen. */
  data(): Candle[];
  setData(data: Candle[]): void;
  update(candle: Candle): void;
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

export function makeFakeSeries(): FakeSeries {
  let current: Candle[] = [];
  return {
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
  };
}

/**
 * A source whose subscription the test drives message by message.
 *
 * Everything a chart draws now arrives through `subscribe` — the opening
 * snapshot included — so this double has no history to resolve. `historyCalls`
 * stays, counting the range reads nobody is expected to make: a feed that went
 * back to fetching one would be the seam growing back (design.md, "Archiwum
 * jest dla terminala jedynym źródłem świec i strumienia").
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

  historyCalls: Array<{ symbol: string; resolution: Resolution }> = [];
  subscribeCalls: Array<{ symbol: string; resolution: Resolution }> = [];
  unsubscribeCount = 0;

  /** Every subscription ever opened, in order, live or long since dropped —
   *  which is what lets a test aim a late message at a superseded one. */
  private subscriptions: Array<{
    sink: (event: StreamEvent) => void;
    live: boolean;
  }> = [];

  searchInstruments = vi.fn(async () => []);
  listInstruments = vi.fn(async () => ({ instruments: [], count: 0, truncated: false }));

  async history(request: { symbol: string; resolution: Resolution }): Promise<Bar[]> {
    this.historyCalls.push({ symbol: request.symbol, resolution: request.resolution });
    return [];
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
