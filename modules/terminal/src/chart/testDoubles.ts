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

/** A source whose history resolution and stream events the test drives. */
export class ControllableSource implements MarketDataSource {
  readonly id = "mock" as const;

  historyCalls: Array<{ symbol: string; resolution: Resolution }> = [];
  subscribeCalls: Array<{ symbol: string; resolution: Resolution }> = [];
  unsubscribeCount = 0;

  private pending: Array<{
    symbol: string;
    resolution: Resolution;
    resolve(bars: Bar[]): void;
    reject(error: Error): void;
  }> = [];

  private sinks: Array<(event: StreamEvent) => void> = [];

  searchInstruments = vi.fn(async () => []);
  listInstruments = vi.fn(async () => ({ instruments: [], count: 0, truncated: false }));
  ping = vi.fn(async () => {});

  history(request: { symbol: string; resolution: Resolution }): Promise<Bar[]> {
    this.historyCalls.push({ symbol: request.symbol, resolution: request.resolution });
    return new Promise<Bar[]>((resolve, reject) => {
      this.pending.push({ symbol: request.symbol, resolution: request.resolution, resolve, reject });
    });
  }

  subscribe(symbol: string, resolution: Resolution, sink: (event: StreamEvent) => void): () => void {
    this.subscribeCalls.push({ symbol, resolution });
    this.sinks.push(sink);
    return () => {
      this.unsubscribeCount++;
      this.sinks = this.sinks.filter((s) => s !== sink);
    };
  }

  /** Resolve the Nth outstanding history call (0 = the oldest). */
  resolveHistory(index: number, bars: Bar[]): void {
    this.pending[index]?.resolve(bars);
  }

  rejectHistory(index: number, message: string): void {
    this.pending[index]?.reject(new Error(message));
  }

  pendingCount(): number {
    return this.pending.length;
  }

  emit(event: StreamEvent): void {
    for (const sink of [...this.sinks]) sink(event);
  }
}

export function bar(time: number, close: number, forming = false, volume: number | null = null): Bar {
  return { time, open: close, high: close + 1, low: close - 1, close, volume, forming };
}
