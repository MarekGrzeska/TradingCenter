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
  } = {},
) {
  const visibleRange = options.visibleRange === undefined ? { from: 0, to: 1000 } : options.visibleRange;
  const timeToCoordinate = options.timeToCoordinate ?? ((t: Time) => t as number);
  const priceToCoordinate = options.priceToCoordinate ?? ((p: number) => p);

  const chart = {
    timeScale: () => ({
      getVisibleRange: () => visibleRange,
      timeToCoordinate,
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
      { xStart: 100, xEnd: 200, yTop: 110, yBottom: 90, color: COLORS.bullish },
    ]);
  });

  it("carries an open zone's null `to` through as a null xEnd, not a guessed edge", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive);
    primitive.setZones([zone({ to: null })]);

    const [item] = primitive.renderItems();
    expect(item?.xEnd).toBeNull();
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
