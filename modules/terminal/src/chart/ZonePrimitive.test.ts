import { describe, expect, it, vi } from "vitest";
import type { CanvasRenderingTarget2D } from "fancy-canvas";
import type { IChartApi, ISeriesApi, SeriesAttachedParameter, SeriesType, Time } from "lightweight-charts";
import { ZonePrimitive, type DrawnZone, type ZoneColors } from "./ZonePrimitive";

const COLORS: ZoneColors = { bullish: "#0a0", bearish: "#a00", neutral: "#888" };

/** Same "test what is asked for, not the pixels" boundary `RayPrimitive.
 *  test.ts` draws — a `CanvasRenderingContext2D` cannot be asserted on
 *  either. */
function fakeContext() {
  return {
    save: vi.fn(),
    restore: vi.fn(),
    fillRect: vi.fn(),
    fillStyle: "",
    globalAlpha: 1,
  };
}

function fakeTarget(bitmapWidth: number) {
  const ctx = fakeContext();
  const target = {
    useBitmapCoordinateSpace: <T>(f: (scope: unknown) => T) =>
      f({
        context: ctx,
        mediaSize: { width: bitmapWidth, height: 300 },
        bitmapSize: { width: bitmapWidth, height: 300 },
        horizontalPixelRatio: 1,
        verticalPixelRatio: 1,
      }),
  } as unknown as CanvasRenderingTarget2D;
  return { ctx, target };
}

function attach(
  zone: ZonePrimitive,
  options: {
    visibleRange?: { from: number; to: number } | null;
    timeToCoordinate?: (time: Time) => number | null;
    priceToCoordinate?: (price: number) => number | null;
    /** What the time scale answers for a moment that is not itself a bar — see
     *  `timeCoordinates.ts`. `null` is a chart with no bars to be near. */
    nearestBar?: (time: Time) => number | null;
  } = {},
) {
  const visibleRange = options.visibleRange === undefined ? { from: 0, to: 1000 } : options.visibleRange;
  const timeToCoordinate = options.timeToCoordinate ?? ((t: Time) => t as number);
  const priceToCoordinate = options.priceToCoordinate ?? ((p: number) => p);

  const nearestBar = options.nearestBar ?? (() => null);
  const chart = {
    timeScale: () => ({
      getVisibleRange: () => visibleRange,
      timeToCoordinate,
      timeToIndex: (t: Time) => nearestBar(t),
      logicalToCoordinate: (x: number | null) => x,
    }),
  } as unknown as IChartApi;
  const series = { priceToCoordinate } as unknown as ISeriesApi<SeriesType, Time>;
  const param = { chart, series, requestUpdate: () => {} } as unknown as SeriesAttachedParameter<Time>;
  zone.attached(param);
}

function zone(overrides: Partial<DrawnZone> = {}): DrawnZone {
  return {
    from: 100 as Time,
    to: 200 as Time,
    top: 110,
    bottom: 90,
    direction: "bullish" as const,
    ...overrides,
  };
}

describe("ZonePrimitive — coordinate resolution", () => {
  it("has nothing to draw before it is attached", () => {
    const primitive = new ZonePrimitive(COLORS);
    primitive.setZones([zone()]);
    expect(primitive.renderItems()).toEqual([]);
  });

  it("stops resolving anything once detached", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive);
    primitive.detached();
    primitive.setZones([zone()]);
    expect(primitive.renderItems()).toEqual([]);
  });

  it("resolves x/y from the chart and series once attached", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive);
    primitive.setZones([zone({ from: 100 as Time, to: 200 as Time, top: 110, bottom: 90 })]);

    expect(primitive.renderItems()).toEqual([
      { open: false, xStart: 100, xEnd: 200, yTop: 110, yBottom: 90, color: COLORS.bullish },
    ]);
  });

  it("carries an open zone's null `to` through as open, not as a guessed edge", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive);
    primitive.setZones([zone({ to: null })]);

    const [item] = primitive.renderItems();
    expect(item?.open).toBe(true);
    expect(item?.xEnd).toBeNull();
  });

  // A `session_range`/`opening_range` zone is computed on the archive's fine series, so its
  // boundaries are minute instants that an hourly or daily chart has no bar for. The time
  // scale answers null for those, and both halves of that used to be silent bugs.
  describe("a zone whose boundaries are not bars on this chart", () => {
    it("snaps its start to the nearest bar instead of vanishing", () => {
      const primitive = new ZonePrimitive(COLORS);
      attach(primitive, {
        timeToCoordinate: (time) => ((time as number) === 830 ? null : (time as number)),
        nearestBar: () => 800,
      });
      primitive.setZones([zone({ from: 830 as Time, to: 900 as Time })]);

      const [item] = primitive.renderItems();
      expect(item?.xStart).toBe(800);
      expect(item?.xEnd).toBe(900);
    });

    it("does not turn an end it cannot place into an open zone running off the screen", () => {
      const primitive = new ZonePrimitive(COLORS);
      attach(primitive, {
        timeToCoordinate: (time) => ((time as number) === 1630 ? null : (time as number)),
        nearestBar: () => null,
      });
      primitive.setZones([zone({ from: 800 as Time, to: 1630 as Time })]);

      const [item] = primitive.renderItems();
      expect(item?.open).toBe(false);

      const { ctx, target } = fakeTarget(500);
      primitive.paneViews()[0]?.renderer()?.draw(target);
      // An unplaceable end draws nothing at all — it is not the same claim as "this zone
      // has not closed yet", which is what filling to the right edge says.
      expect(ctx.fillRect).not.toHaveBeenCalled();
    });
  });

  it("colors bearish and direction-less zones from their own slot", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive);
    primitive.setZones([
      zone({ from: 1 as Time, direction: "bearish" }),
      zone({ from: 2 as Time, direction: null }),
    ]);

    const [bearish, neutral] = primitive.renderItems();
    expect(bearish?.color).toBe(COLORS.bearish);
    expect(neutral?.color).toBe(COLORS.neutral);
  });

  it("has nothing to draw when the time scale reports no visible range yet", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive, { visibleRange: null });
    primitive.setZones([zone()]);
    expect(primitive.renderItems()).toEqual([]);
  });
});

describe("ZonePrimitive — visible-range selection (task 4.7, task 4.10)", () => {
  it("skips a zone entirely to the left of what is visible", () => {
    const primitive = new ZonePrimitive(COLORS);
    const timeToCoordinate = vi.fn((t: Time) => t as number);
    attach(primitive, { visibleRange: { from: 500, to: 1000 }, timeToCoordinate });
    primitive.setZones([zone({ from: 10 as Time, to: 20 as Time })]);

    expect(primitive.renderItems()).toEqual([]);
    expect(timeToCoordinate).not.toHaveBeenCalled();
  });

  it("skips a zone entirely to the right of what is visible", () => {
    const primitive = new ZonePrimitive(COLORS);
    const timeToCoordinate = vi.fn((t: Time) => t as number);
    attach(primitive, { visibleRange: { from: 0, to: 100 }, timeToCoordinate });
    primitive.setZones([zone({ from: 500 as Time, to: 600 as Time })]);

    expect(primitive.renderItems()).toEqual([]);
    expect(timeToCoordinate).not.toHaveBeenCalled();
  });

  it("keeps a zone that only partially overlaps the visible range", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive, { visibleRange: { from: 150, to: 300 } });
    primitive.setZones([zone({ from: 100 as Time, to: 200 as Time })]);

    expect(primitive.renderItems()).toHaveLength(1);
  });

  it("never lets an open zone's null `to` be mistaken for 'before the visible range'", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive, { visibleRange: { from: 900, to: 1000 } });
    primitive.setZones([zone({ from: 100 as Time, to: null })]);

    expect(primitive.renderItems()).toHaveLength(1);
  });

  it("keeps per-frame cost bounded by the visible window, not the total zone count (task 4.10)", () => {
    // ~300 zones spread across a wide daily-chart-sized read, mirroring the
    // task's own number — only a narrow band of them is ever inside the
    // scrolled-to window, the situation panning repeats every frame.
    const primitive = new ZonePrimitive(COLORS);
    const timeToCoordinate = vi.fn((t: Time) => t as number);
    attach(primitive, { visibleRange: { from: 10_000, to: 10_500 }, timeToCoordinate });
    const zones = Array.from({ length: 300 }, (_, i) =>
      zone({ from: (i * 100) as Time, to: (i * 100 + 50) as Time }),
    );
    primitive.setZones(zones);

    const startedAt = performance.now();
    const items = primitive.renderItems();
    const elapsedMs = performance.now() - startedAt;

    // Only zones overlapping [10000, 10500) survive the filter — a handful,
    // not 300 — and every `timeToCoordinate` call spent is one of those, not
    // one per zone this primitive holds.
    expect(items.length).toBeLessThan(10);
    expect(timeToCoordinate).toHaveBeenCalledTimes(items.length * 2);
    expect(elapsedMs).toBeLessThan(5);
  });
});

describe("ZonePrimitive — drawing", () => {
  it("fills a rectangle from the zone's own bounds", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive);
    primitive.setZones([zone({ from: 40 as Time, to: 120 as Time, top: 110, bottom: 90 })]);

    const { target, ctx } = fakeTarget(200);
    primitive.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.fillRect).toHaveBeenCalledWith(40, 90, 80, 20);
  });

  it("draws an open zone all the way to the pane's bitmap edge", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive);
    primitive.setZones([zone({ from: 40 as Time, to: null, top: 110, bottom: 90 })]);

    const { target, ctx } = fakeTarget(200);
    primitive.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.fillRect).toHaveBeenCalledWith(40, 90, 160, 20);
  });

  it("clamps a zone whose start sits left of the visible area to the pane's edge", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive, {
      timeToCoordinate: (t) => (t === 100 ? -500 : 40),
    });
    primitive.setZones([zone({ from: 100 as Time, to: 200 as Time })]);

    const { target, ctx } = fakeTarget(200);
    primitive.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.fillRect).toHaveBeenCalledWith(0, 90, 40, 20);
  });

  it("draws nothing for a zone the time scale could not place", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive, { timeToCoordinate: () => null });
    primitive.setZones([zone()]);

    const { target, ctx } = fakeTarget(200);
    primitive.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.fillRect).not.toHaveBeenCalled();
  });
});
