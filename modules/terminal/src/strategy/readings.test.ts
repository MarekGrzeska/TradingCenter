import { describe, expect, it } from "vitest";
import { latestCandles, latestReadings, readReport, readSnapshot } from "./readings";

/**
 * A snapshot is JSON the platform wrote for its own replay, not a contract; the view reads it the way it would read a
 * file from last month. The offsets are the rule language's, so a reader can check a crossing by eye.
 */

const SNAPSHOT = {
  symbol: "US100",
  as_of: "2026-08-22T10:00:00+00:00",
  candles: [
    { time: "2026-08-22T08:00:00+00:00", open: 1, high: 2, low: 0.5, close: 1.5 },
    { time: "2026-08-22T09:00:00+00:00", open: 1.5, high: 2.5, low: 1, close: 2 },
    { time: "2026-08-22T10:00:00+00:00", open: 2, high: 3, low: 1.5, close: 2.5 },
  ],
  values: {
    fast: {
      key: "fast",
      resolution: "HOUR",
      times: ["2026-08-22T08:00:00+00:00", "2026-08-22T09:00:00+00:00", "2026-08-22T10:00:00+00:00"],
      lines: { value: [1.1, 1.2, 1.3] },
      markers: [],
      zones: [],
    },
    slow: {
      key: "slow",
      resolution: "HOUR",
      times: ["2026-08-22T08:00:00+00:00", "2026-08-22T09:00:00+00:00", "2026-08-22T10:00:00+00:00"],
      // Still warming up on the first bar: the platform writes what it had, not a number.
      lines: { value: [null, 1.25, 1.25] },
      markers: [],
      zones: [],
    },
  },
};

describe("reading a snapshot", () => {
  it("counts offsets back from the bar decided on", () => {
    const fact = readSnapshot(SNAPSHOT).values.find((one) => one.key === "fast");

    expect(latestReadings(fact!, 2)).toEqual([
      { offset: 0, time: "2026-08-22T10:00:00+00:00", values: { value: 1.3 } },
      { offset: 1, time: "2026-08-22T09:00:00+00:00", values: { value: 1.2 } },
    ]);
  });

  it("keeps a warming-up line as no reading rather than a neighbour's number", () => {
    const fact = readSnapshot(SNAPSHOT).values.find((one) => one.key === "slow");

    expect(latestReadings(fact!, 3).map((row) => row.values.value)).toEqual([1.25, 1.25, null]);
  });

  it("orders the candles newest first, like the readings beside them", () => {
    expect(latestCandles(readSnapshot(SNAPSHOT).candles, 2).map((one) => one.close)).toEqual([
      2.5, 2,
    ]);
  });

  it("opens a snapshot with nothing in it", () => {
    // A decision refused for coverage may have been stored with the facts that could not be read.
    expect(readSnapshot({ symbol: "US100" })).toEqual({ candles: [], values: [] });
    expect(readSnapshot({ candles: "not a list", values: [1, 2] })).toEqual({
      candles: [],
      values: [],
    });
  });
});

describe("reading a report", () => {
  it("names the metrics and the refusals it counted", () => {
    const report = readReport({
      metrics: {
        trades: 12,
        wins: 7,
        win_rate: 0.5833,
        expectancy_r: 0.42,
        total_r: 5.04,
        profit_factor: null,
        max_drawdown_r: 2.1,
        longest_losing_streak: 3,
        average_bars_held: 6.5,
        unresolved: 1,
      },
      refusals: { "no cross on this bar": 800, "flat market": 120 },
      bars: 1000,
      strategy_revision: 3,
    });

    expect(report.metrics).toMatchObject({ trades: 12, winRate: 0.5833, profitFactor: null });
    expect(report.refusals).toEqual({ "no cross on this bar": 800, "flat market": 120 });
    expect(report.bars).toBe(1000);
    expect(report.strategyRevision).toBe(3);
  });

  it("reads a report without metrics as one that has none", () => {
    expect(readReport({}).metrics).toBeNull();
    expect(readReport({ metrics: "gone" }).refusals).toEqual({});
  });
});
