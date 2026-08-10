import { describe, expect, it } from "vitest";
import { mergeBar, mergeSeries } from "./merge";
import type { Bar } from "./types";

function bar(time: number, close: number, forming = false): Bar {
  return { time, open: close, high: close, low: close, close, volume: null, forming };
}

describe("mergeBar", () => {
  it("appends into an empty series", () => {
    expect(mergeBar([], bar(100, 1))).toEqual([bar(100, 1)]);
  });

  it("replaces the last bar when the forming candle updates in place", () => {
    const series = [bar(100, 1), bar(200, 2, true)];
    const updated = mergeBar(series, bar(200, 2.5, true));
    expect(updated).toEqual([bar(100, 1), bar(200, 2.5, true)]);
  });

  it("appends when a new period opens", () => {
    const series = [bar(100, 1), bar(200, 2)];
    const updated = mergeBar(series, bar(300, 3));
    expect(updated).toEqual([bar(100, 1), bar(200, 2), bar(300, 3)]);
  });

  it("closes a forming candle by replacing it with the settled one", () => {
    const series = [bar(100, 1), bar(200, 2, true)];
    const settled = bar(200, 2.2, false);
    expect(mergeBar(series, settled)).toEqual([bar(100, 1), settled]);
  });

  it("never produces two bars with the same timestamp", () => {
    const series = [bar(100, 1), bar(200, 2), bar(300, 3)];
    const updated = mergeBar(series, bar(200, 99));
    const times = updated.map((b) => b.time);
    expect(new Set(times).size).toBe(times.length);
    expect(updated).toEqual([bar(100, 1), bar(200, 99), bar(300, 3)]);
  });

  it("inserts a gap-fill bar in sorted position without disturbing later bars", () => {
    const series = [bar(100, 1), bar(300, 3)];
    const updated = mergeBar(series, bar(200, 2));
    expect(updated).toEqual([bar(100, 1), bar(200, 2), bar(300, 3)]);
  });

  it("does not mutate the input series", () => {
    const series = [bar(100, 1), bar(200, 2)];
    const frozen = Object.freeze(series.slice());
    expect(() => mergeBar(frozen, bar(300, 3))).not.toThrow();
    expect(series).toEqual([bar(100, 1), bar(200, 2)]);
  });
});

describe("mergeSeries", () => {
  it("folds a reconnect gap-fill into the existing series in one call", () => {
    const before = [bar(100, 1), bar(400, 4, true)];
    const gapFill = [bar(200, 2), bar(300, 3), bar(400, 4, false)];
    expect(mergeSeries(before, gapFill)).toEqual([
      bar(100, 1),
      bar(200, 2),
      bar(300, 3),
      bar(400, 4, false),
    ]);
  });

  it("joins ordered history pages with no duplicate boundary candle", () => {
    const older = [bar(100, 1), bar(200, 2)];
    const newer = [bar(200, 2), bar(300, 3)]; // page boundary re-fetched, as history.py does
    expect(mergeSeries(older, newer)).toEqual([bar(100, 1), bar(200, 2), bar(300, 3)]);
  });

  it("joins a page of older candles onto the front", () => {
    const drawn = [bar(300, 3), bar(400, 4)];
    const page = [bar(100, 1), bar(200, 2)];
    expect(mergeSeries(drawn, page)).toEqual([bar(100, 1), bar(200, 2), bar(300, 3), bar(400, 4)]);
  });

  it("puts an out-of-order batch in order rather than trusting it", () => {
    // The merge is linear only while both sides are sorted, and a source that
    // answered out of order would otherwise interleave into nonsense.
    expect(mergeSeries([bar(200, 2)], [bar(300, 3), bar(100, 1)])).toEqual([
      bar(100, 1),
      bar(200, 2),
      bar(300, 3),
    ]);
  });

  it("leaves the base untouched when there is nothing to merge", () => {
    const base = [bar(100, 1)];
    expect(mergeSeries(base, [])).toEqual(base);
  });
});
