import { describe, expect, it } from "vitest";
import type { PricePoint } from "./polymarketApi";
import { medianSpacing, rangeStart, reachesBeforeCoverage, toLineData } from "./series";

/** The gap rule lives here rather than in the chart, so it is tested here rather than
 *  through a canvas. What the chart does with a whitespace point is the library's. */

function points(spec: [minutesFromStart: number, price: number | null][]): PricePoint[] {
  const base = new Date("2026-08-22T00:00:00Z").getTime();
  return spec.map(([minutes, price]) => ({
    at: new Date(base + minutes * 60_000),
    price,
    lastTrade: null,
  }));
}

describe("toLineData", () => {
  it("draws an evenly sampled series as one unbroken line", () => {
    const data = toLineData(points([
      [0, 0.5],
      [1, 0.51],
      [2, 0.52],
      [3, 0.53],
    ]));

    expect(data).toHaveLength(4);
    expect(data.every((point) => point.value !== undefined)).toBe(true);
  });

  it("breaks the line where the collected history stops and starts again", () => {
    // Four one-minute readings, a day of nothing, then two more. Without the break the
    // chart would draw a straight run across a day nobody measured — a claim about the
    // market made out of the archive's silence.
    const data = toLineData(points([
      [0, 0.5],
      [1, 0.51],
      [2, 0.52],
      [1442, 0.7],
      [1443, 0.71],
    ]));

    const whitespace = data.filter((point) => point.value === undefined);
    expect(whitespace).toHaveLength(1);
    // Placed inside the gap, not on either reading that did happen.
    expect(whitespace[0].time).toBeGreaterThan(data[2].time);
    expect(whitespace[0].time).toBeLessThan(data[4].time);
  });

  it("measures the gap against the series' own spacing, not a fixed number of minutes", () => {
    // Backfilled history arrives hourly, so an hour between points is normal here and
    // must not read as a hole. A fixed threshold would call this series one long gap.
    const hourly = toLineData(points([
      [0, 0.5],
      [60, 0.51],
      [120, 0.52],
      [180, 0.53],
    ]));

    expect(hourly.filter((point) => point.value === undefined)).toHaveLength(0);
  });

  it("keeps a recorded moment with no price as a hole rather than dropping it", () => {
    // Dropped, the line would close over it — the module recorded that it looked and found
    // nothing, which is not the same as never having looked.
    const data = toLineData(points([
      [0, 0.5],
      [1, null],
      [2, 0.52],
    ]));

    expect(data).toHaveLength(3);
    expect(data[1].value).toBeUndefined();
  });

  it("draws a single reading without inventing a neighbour", () => {
    expect(toLineData(points([[0, 0.5]]))).toEqual([
      { time: new Date("2026-08-22T00:00:00Z").getTime() / 1000, value: 0.5 },
    ]);
  });

  it("has nothing to draw for an empty series", () => {
    expect(toLineData([])).toEqual([]);
  });
});

describe("medianSpacing", () => {
  it("is the middle gap, so one long hole cannot hide every other one", () => {
    // A mean here would be 361 minutes and would swallow the real gaps entirely.
    expect(medianSpacing(points([
      [0, 0.5],
      [1, 0.5],
      [2, 0.5],
      [1442, 0.5],
    ]))).toBe(60_000);
  });

  it("has no answer for a series too short to have a spacing", () => {
    expect(medianSpacing(points([[0, 0.5]]))).toBeNull();
    expect(medianSpacing([])).toBeNull();
  });
});

describe("rangeStart", () => {
  const now = new Date("2026-08-22T12:00:00Z");

  it("counts back from now for a bounded range", () => {
    expect(rangeStart("7d", now)).toEqual(new Date("2026-08-15T12:00:00Z"));
    expect(rangeStart("90d", now)).toEqual(new Date("2026-05-24T12:00:00Z"));
  });

  it("asks for no boundary at all when the operator wants everything", () => {
    expect(rangeStart("all", now)).toBeUndefined();
  });
});

describe("reachesBeforeCoverage", () => {
  const now = new Date("2026-08-22T12:00:00Z");

  it("is true when the range reaches back past what was collected", () => {
    expect(reachesBeforeCoverage("90d", new Date("2026-08-01T00:00:00Z"), now)).toBe(true);
    expect(reachesBeforeCoverage("all", new Date("2026-08-01T00:00:00Z"), now)).toBe(true);
  });

  it("is false when everything asked for is inside what was collected", () => {
    expect(reachesBeforeCoverage("7d", new Date("2026-05-01T00:00:00Z"), now)).toBe(false);
  });

  it("has nothing to say when the boundary is unknown", () => {
    expect(reachesBeforeCoverage("all", null, now)).toBe(false);
  });
});
