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
    strokeRect: vi.fn(),
    fillText: vi.fn(),
    measureText: vi.fn((text: string) => ({ width: text.length * 6 })),
    setLineDash: vi.fn(),
    fillStyle: "",
    strokeStyle: "",
    lineWidth: 0,
    font: "",
    textBaseline: "",
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

function attach(zone: ZonePrimitive) {
  const chart = {
    timeScale: () => ({
      getVisibleRange: () => ({ from: 0, to: 1000 }),
      timeToCoordinate: (t: Time) => t as number,
      timeToIndex: () => null,
      logicalToCoordinate: (x: number | null) => x,
    }),
  } as unknown as IChartApi;
  const series = { priceToCoordinate: (p: number) => p } as unknown as ISeriesApi<SeriesType, Time>;
  zone.attached({ chart, series, requestUpdate: () => {} } as unknown as SeriesAttachedParameter<Time>);
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

describe("ZonePrimitive", () => {
  it("has nothing to draw before it is attached", () => {
    const primitive = new ZonePrimitive(COLORS);
    primitive.setZones([zone()]);
    expect(primitive.renderItems()).toEqual([]);
  });

  it("resolves x/y from the chart and series once attached", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive);
    primitive.setZones([zone()]);

    expect(primitive.renderItems()).toEqual([
      { open: false, xStart: 100, xEnd: 200, yTop: 110, yBottom: 90, color: COLORS.bullish, label: null },
    ]);
  });

  it("fills a rectangle from the zone's own bounds", () => {
    const primitive = new ZonePrimitive(COLORS);
    attach(primitive);
    primitive.setZones([zone({ from: 40 as Time, to: 120 as Time })]);

    const { target, ctx } = fakeTarget(200);
    primitive.paneViews()[0]?.renderer()?.draw(target);

    expect(ctx.fillRect).toHaveBeenCalledWith(40, 90, 80, 20);
  });

  it("is clicked anywhere inside its own rectangle, and nowhere outside it", () => {
    // A shape with an area needs no tolerance margin the way a line does (design.md,
    // "Tolerancja trafienia mieszka w `hitTest` każdego prymitywu").
    const drawn = new ZonePrimitive(COLORS, { weight: "drawing", objectId: "5" });
    attach(drawn);
    drawn.setZones([zone()]);

    expect(drawn.hitTest(150, 100)?.externalId).toBe("5");
    expect(drawn.hitTest(150, 200)).toBeNull();
    expect(drawn.hitTest(300, 100)).toBeNull();
  });

  it("never answers a click for an indicator's own zone", () => {
    const computed = new ZonePrimitive(COLORS);
    attach(computed);
    computed.setZones([zone()]);
    expect(computed.hitTest(150, 100)).toBeNull();
  });
});
